"""
MargeProPlugin — Plugin marketing / MargePro pour ADA.
Univers : margep. Skill existant : skills/margepro/SKILL.md

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["margepro"] = True.
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin


class MargeProPlugin(BasePlugin):

    plugin_id: str = "margepro"
    display_name: str = "MargePro"
    icon: str = "📣"
    universe: str = "margep"
    color: str = "#ec4899"

    def on_enable(self) -> None:
        print("[MargeProPlugin] ✓ Module margepro activé")

    def on_disable(self) -> None:
        print("[MargeProPlugin] Module margepro désactivé")

    def get_nav_items(self) -> list[dict]:
        return [{"label": "MargePro", "icon": "📣", "route": "margepro"}]

    def get_chat_context(self, company_id: str | None = None) -> str:
        try:
            from config import MARGEPRO_CONTEXT
            if MARGEPRO_CONTEXT:
                return f"Contexte MargePro :\n{MARGEPRO_CONTEXT}"
        except Exception:
            pass
        return "Module MargePro actif. Tu génères du contenu marketing pour les réseaux sociaux."

    def get_skills(self) -> list[str]:
        return ["margepro"]

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        return [
            "Rédige un post LinkedIn",
            "Rédige un post Instagram",
            "Génère une accroche percutante",
            "Calendrier éditorial cette semaine",
        ]

    def get_function_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "generate_post",
                    "description": "Génère un post optimisé pour un réseau social (LinkedIn, Instagram, Facebook).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "platform": {"type": "string", "enum": ["linkedin", "instagram", "facebook", "twitter"], "description": "Réseau social cible"},
                            "topic":    {"type": "string", "description": "Sujet ou message clé du post"},
                            "tone":     {"type": "string", "enum": ["professionnel", "décontracté", "inspirant", "humoristique"], "description": "Ton du post"},
                        },
                        "required": ["platform", "topic"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_post",
                    "description": "Planifie la publication d'un post via n8n.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "platform":  {"type": "string", "description": "Réseau social cible"},
                            "content":   {"type": "string", "description": "Contenu du post à publier"},
                            "scheduled_at": {"type": "string", "description": "Date/heure de publication ISO 8601"},
                        },
                        "required": ["platform", "content", "scheduled_at"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_analytics",
                    "description": "Récupère les métriques de performance des dernières publications.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "platform": {"type": "string", "description": "Réseau social (optionnel — tous si absent)"},
                            "days":     {"type": "integer", "description": "Nombre de jours à analyser (défaut: 7)"},
                        },
                    },
                },
            },
        ]

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        return {
            "function_gemma": [
                "post linkedin", "post facebook", "post instagram", "rédige un post",
                "contenu marketing", "accroche", "copywriting", "margepro",
                "planifie une publication", "calendrier éditorial",
                "génère un texte pour", "publie sur", "contenu réseaux sociaux",
            ]
        }

    def get_n8n_webhooks(self) -> dict[str, str]:
        return {
            "generate-post":  "http://localhost:5678/webhook/margepro-generate",
            "schedule-post":  "http://localhost:5678/webhook/margepro-schedule",
        }

    def handle_action(self, action: str, params: dict) -> dict:
        if action == "generate_post":
            try:
                from config import MARKETING_MODEL, OLLAMA_URL
                from core.settings_store import settings as _settings
                import requests as _req

                ollama_url = _settings.get("ollama_url", OLLAMA_URL)
                model = _settings.get("models.marketing", MARKETING_MODEL)
                platform = params.get("platform", "linkedin")
                topic = params.get("topic", "")
                tone = params.get("tone", "professionnel")

                prompt = (
                    f"Génère un post {platform} {tone} sur le sujet suivant : {topic}. "
                    f"Adapte le format, les hashtags et la longueur au réseau social {platform}. "
                    f"Réponds uniquement avec le contenu du post, sans commentaire."
                )
                resp = _req.post(
                    f"{ollama_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=60,
                )
                resp.raise_for_status()
                content = resp.json().get("response", "")
                return {"success": True, "message": "Post généré", "data": {"content": content, "platform": platform}}
            except Exception as exc:
                return {"success": False, "message": str(exc), "data": None}

        return {"success": False, "message": f"Action MargePro {action} : connecteur n8n requis", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        return (
            "Tu crées du contenu marketing pour MargePro.\n"
            "Fonctions disponibles : generate_post, schedule_post, get_analytics.\n"
            "Adapte toujours le ton et le format au réseau social cible."
        )

    def get_dashboard_kpis(self) -> list[dict]:
        return [
            {"id": "mp_posts_week", "label": "Posts cette semaine", "value": "—", "color": "#ec4899"},
            {"id": "mp_scheduled",  "label": "Publications planif.", "value": "—"},
        ]
