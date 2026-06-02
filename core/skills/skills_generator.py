"""
skills_generator.py — Génération automatique de skills depuis les conversations
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Seuil minimum de messages pour déclencher une génération
MIN_TURNS = 4
# Longueur minimum du contenu pour sauvegarder
MIN_CONTENT_LEN = 100


def should_generate_skill(conversation: list[dict]) -> bool:
    """
    Analyse si la conversation mérite une skill auto-générée.
    Critères :
    - Au moins MIN_TURNS échanges user/assistant
    - Contient des mots-clés de procédures/recettes/explications
    """
    if len(conversation) < MIN_TURNS * 2:
        return False

    text = " ".join(m.get("content", "") for m in conversation).lower()
    signals = [
        "comment ", "étape", "procédure", "configurer", "installer", "paramétrer",
        "solution", "résoudre", "corriger", "optimiser", "recette", "méthode",
    ]
    return sum(1 for s in signals if s in text) >= 2


async def generate_skill_from_conversation(
    skill_id: str,
    history: list[dict],
    llm_client,
    domain: str = "auto",
) -> Optional[dict]:
    """
    Génère une skill depuis une conversation en interrogeant le LLM.
    Retourne un dict skill ou None si génération impossible.
    """
    if not history:
        return None

    # Résumer la conversation en une skill exploitable
    summary_prompt = (
        "Analyse cette conversation et extrait une skill/connaissance réutilisable.\n"
        "Réponds UNIQUEMENT avec ce format JSON strict, sans markdown :\n"
        '{"name":"<titre court>","summary":"<1 phrase>","content":"<instructions complètes>"}\n\n'
        "Conversation :\n"
    )

    convo_text = "\n".join(
        f"{m['role'].upper()}: {m.get('content', '')}"
        for m in history[-20:]
        if m.get("role") in ("user", "assistant")
    )

    try:
        response = await llm_client.chat([
            {"role": "system", "content": "Tu es un extracteur de connaissances. Sois concis et précis."},
            {"role": "user", "content": summary_prompt + convo_text},
        ])

        # Parser le JSON de la réponse
        text = response.strip()
        # Extraire le JSON même s'il y a du texte autour
        m = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if not m:
            return None

        import json
        data = json.loads(m.group(0))
        name = data.get("name", "").strip()
        content = data.get("content", "").strip()
        summary = data.get("summary", "").strip()

        if not name or len(content) < MIN_CONTENT_LEN:
            return None

        return {
            "id": skill_id,
            "name": name,
            "domain": domain,
            "source": "auto",
            "content": content,
            "summary": summary,
            "priority": 5,
        }

    except Exception as e:
        logger.error("[Skills Generator] Erreur génération skill : %s", e)
        return None
