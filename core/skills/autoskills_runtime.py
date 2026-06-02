"""
autoskills_runtime.py — Runtime bridge : injection + génération AutoSkills adaptatifs
Deux fonctions principales :
  - inject_autoskills()      : avant LLM, injecte les AutoSkills pertinentes
  - maybe_update_autoskill() : après LLM, crée/enrichit une AutoSkill si nécessaire
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Patterns secrets à masquer avant sauvegarde ───────────────────────────────
_SECRET_PAT = re.compile(
    r'(?i)(password|passwd|token|secret|api_key|apikey|authorization|cookie|private_key)\s*[:=]\s*\S+',
)
_BEARER_PAT = re.compile(r'(?i)(Bearer|Basic)\s+[A-Za-z0-9\-_\.+/=]{8,}')


def sanitize_autoskill_text(text: str) -> str:
    """Masque les secrets évidents avant sauvegarde d'une AutoSkill."""
    text = _SECRET_PAT.sub(r'\1=***MASQUÉ***', text)
    text = _BEARER_PAT.sub(r'\1 ***MASQUÉ***', text)
    return text


def normalize_autoskill_domain(domain: Optional[str]) -> str:
    """Normalise le domaine : 'core' auto-write désactivé par défaut."""
    try:
        from core.settings_store import settings
        default = settings.get("autoskills.default_domain", "auto")
        allow_core = settings.get("autoskills.allow_core_domain_auto_write", False)
    except Exception:
        default, allow_core = "auto", False
    if not domain:
        return default
    if domain == "core" and not allow_core:
        return default
    return domain


# ── Injection ─────────────────────────────────────────────────────────────────

def inject_autoskills(
    messages: list[dict],
    query: str,
    domain: Optional[str] = None,
    request_id: str = "",
    session_id: str = "",
) -> tuple[list[dict], dict]:
    """
    Injecte les AutoSkills SQLite pertinentes dans le system prompt.
    Retourne (messages modifiés, metadata). Ne lève jamais d'exception.
    """
    empty = {"skills_injected": [], "skills_count": 0}
    try:
        from core.settings_store import settings
        if not settings.get("autoskills.enabled", True):
            return messages, empty
        if not settings.get("autoskills.inject_enabled", True):
            return messages, empty
        max_skills = settings.get("autoskills.max_injected", 5)
    except Exception:
        max_skills = 5

    try:
        from core.skills.skills_injector import build_system_prompt

        domain = normalize_autoskill_domain(domain)

        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": ""})

        final_prompt, meta = build_system_prompt(
            base_prompt=messages[0]["content"],
            query=query,
            active_domain=domain,
            max_skills=max_skills,
        )
        messages[0] = {"role": "system", "content": final_prompt}
        meta["domain"] = domain

        if meta.get("skills_count", 0) > 0:
            _radar(
                "autoskills.injected", "info",
                request_id=request_id, session_id=session_id,
                metadata={
                    "skills_count": meta["skills_count"],
                    "skill_ids": meta.get("skills_injected", []),
                    "domain": domain,
                    "query_preview": query[:80],
                },
            )
        else:
            _radar(
                "autoskills.context.empty", "info",
                request_id=request_id, session_id=session_id,
                metadata={"domain": domain},
            )

        return messages, meta

    except Exception as exc:
        logger.warning("[AutoSkills] inject error: %s", exc)
        return messages, empty


# ── Génération post-réponse ───────────────────────────────────────────────────

def find_existing_autoskill(topic_text: str, domain: str) -> Optional[dict]:
    """Cherche une AutoSkill 'auto' existante similaire au topic."""
    try:
        from core.skills.skills_manager import search_skills
        rows = search_skills(topic_text, active_domain=domain, limit=5)
        candidates = [r for r in rows if r.get("source") == "auto"]
        return candidates[0] if candidates else None
    except Exception:
        return None


async def maybe_update_autoskill(
    history: list[dict],
    user_text: str,
    assistant_text: str,
    domain: Optional[str],
    request_id: str,
    session_id: str,
    call_llm,
) -> Optional[str]:
    """
    Analyse la conversation et crée ou enrichit une AutoSkill si pertinent.
    Tâche de fond — ne bloque et ne lève jamais d'exception vers l'appelant.
    """
    try:
        from core.settings_store import settings
        if not settings.get("autoskills.enabled", True):
            return None
        if not settings.get("autoskills.generate_enabled", True):
            return None
        max_hist = settings.get("autoskills.max_generation_history", 20)
    except Exception:
        max_hist = 20

    try:
        from core.skills.skills_generator import should_generate_skill, generate_skill_from_conversation
        from core.skills.skills_manager import save_skill

        domain = normalize_autoskill_domain(domain)

        # Fenêtre de conversation à analyser
        window = [m for m in (history or [])[-max_hist:] if m.get("role") in ("user", "assistant")]
        window.append({"role": "user",      "content": user_text})
        window.append({"role": "assistant", "content": assistant_text})

        if not should_generate_skill(window):
            return None

        _radar("autoskills.generation.started", "info",
               request_id=request_id, session_id=session_id,
               metadata={"domain": domain, "turns": len(window)})

        # Chercher une AutoSkill existante sur ce sujet
        existing = find_existing_autoskill(user_text[:200], domain)

        # ID stable
        raw = domain + "\n" + "\n".join(m.get("content", "")[:300] for m in window[-6:])
        skill_id = "auto_" + hashlib.sha1(raw.encode()).hexdigest()[:10]
        if existing:
            skill_id = existing["id"]

        class _LLM:
            def __init__(self, fn):
                self._fn = fn
            async def chat(self, msgs):
                return await self._fn(msgs, thinking=False)

        generated = await generate_skill_from_conversation(
            skill_id=skill_id,
            history=window,
            llm_client=_LLM(call_llm),
            domain=domain,
        )

        if not generated:
            _radar("autoskills.generation.skipped", "info",
                   request_id=request_id, session_id=session_id,
                   metadata={"domain": domain})
            return None

        # Sanitize
        generated["content"] = sanitize_autoskill_text(generated.get("content", ""))

        action = "updated" if existing else "created"
        final_id = save_skill(
            skill_id=generated["id"],
            name=generated.get("name", "AutoSkill"),
            content=generated["content"],
            summary=generated.get("summary", ""),
            domain=generated.get("domain", domain),
            source="auto",
            priority=existing["priority"] if existing else 5,
        )

        _radar(f"autoskills.generation.{action}", "info",
               request_id=request_id, session_id=session_id,
               metadata={"skill_id": final_id, "action": action, "domain": domain})

        logger.info("[AutoSkills] %s → %s (domain=%s)", action, final_id, domain)
        return final_id

    except Exception as exc:
        logger.warning("[AutoSkills] maybe_update_autoskill error: %s", exc)
        _radar("autoskills.generation.error", "error",
               request_id=request_id,
               metadata={"error": str(exc)})
        return None


# ── Helper Radar ──────────────────────────────────────────────────────────────

def _radar(event_type: str, level: str = "info", **kwargs) -> None:
    try:
        from web.radar.events import emit_event
        emit_event(type=event_type, level=level, module="autoskills_runtime", **kwargs)
    except Exception:
        pass
