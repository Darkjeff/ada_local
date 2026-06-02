"""
skills_injector.py — Construction du system prompt enrichi par les skills
"""
import logging
from typing import Optional

from .skills_manager import search_skills, MAX_SKILLS_IN_CONTEXT

logger = logging.getLogger(__name__)


def build_system_prompt(
    base_prompt: str,
    query: str,
    active_domain: Optional[str] = None,
    enable_archive_fallback: bool = False,
    max_skills: int = MAX_SKILLS_IN_CONTEXT,
) -> tuple[str, dict]:
    """
    Construit le system prompt final en injectant les skills pertinentes.

    Retourne :
        (final_prompt: str, metadata: dict)

    metadata contient :
        - skills_injected: list[str]  (ids des skills injectées)
        - skills_count: int
        - domain: str | None
    """
    try:
        matched = search_skills(query, active_domain=active_domain, limit=max_skills)
    except Exception as e:
        logger.error("[Skills Injector] Erreur recherche skills : %s", e)
        matched = []

    if not matched:
        return base_prompt, {"skills_injected": [], "skills_count": 0, "domain": active_domain}

    # Assembler les blocs skills
    skill_blocks: list[str] = []
    injected_ids: list[str] = []

    for skill in matched:
        content = skill.get("content", "").strip()
        if not content:
            continue
        name = skill.get("name", skill["id"])
        skill_blocks.append(f"### {name}\n{content}")
        injected_ids.append(skill["id"])

    if not skill_blocks:
        return base_prompt, {"skills_injected": [], "skills_count": 0, "domain": active_domain}

    skills_section = "\n\n".join(skill_blocks)
    final_prompt = f"{base_prompt}\n\n---\n## Connaissances actives\n\n{skills_section}"

    metadata = {
        "skills_injected": injected_ids,
        "skills_count": len(injected_ids),
        "domain": active_domain,
    }

    logger.debug("[Skills Injector] %d skill(s) injectée(s) pour domaine=%s", len(injected_ids), active_domain)
    return final_prompt, metadata
