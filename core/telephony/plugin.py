"""
TelephonyPlugin — Plugin téléphonie SIP pour ADA.
Univers : opent. Désactivé par défaut.

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["telephony"] = True.
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin


class TelephonyPlugin(BasePlugin):

    plugin_id: str = "telephony"
    display_name: str = "Téléphonie"
    icon: str = "📞"
    universe: str = "opent"
    color: str = "#06b6d4"

    def on_enable(self) -> None:
        print("[TelephonyPlugin] ✓ Module téléphonie activé")

    def on_disable(self) -> None:
        print("[TelephonyPlugin] Module téléphonie désactivé")

    def get_nav_items(self) -> list[dict]:
        return [{"label": "Téléphonie", "icon": "📞", "route": "telephony"}]

    def get_chat_context(self, company_id: str | None = None) -> str:
        return (
            "Module Téléphonie actif. "
            "Tu peux consulter l'état des lignes, l'historique des appels et la liste des extensions SIP."
        )

    def get_skills(self) -> list[str]:
        return []

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        return [
            "Lignes actives",
            "Appels du jour",
            "Extensions SIP",
        ]

    def get_function_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "call_status",
                    "description": "Récupère l'état des lignes téléphoniques actives.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "call_history",
                    "description": "Récupère l'historique des appels entrants et sortants.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date":      {"type": "string", "description": "Date au format YYYY-MM-DD (optionnel — aujourd'hui si absent)"},
                            "direction": {"type": "string", "enum": ["all", "inbound", "outbound"], "description": "Sens des appels"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "extension_list",
                    "description": "Liste les extensions SIP enregistrées.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        return {
            "function_gemma": [
                "téléphonie", "appel", "ligne", "extension SIP", "historique appels",
                "appels entrants", "appels sortants", "voip", "trunk",
            ]
        }

    def get_n8n_webhooks(self) -> dict[str, str]:
        return {
            "call-status":   "http://localhost:5678/webhook/telephony-call-status",
            "call-history":  "http://localhost:5678/webhook/telephony-call-history",
            "extension-list": "http://localhost:5678/webhook/telephony-extensions",
        }

    def handle_action(self, action: str, params: dict) -> dict:
        return {"success": False, "message": f"Action téléphonie {action} : connecteur n8n requis", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        return (
            "Tu gères la téléphonie SIP.\n"
            "Fonctions disponibles : call_status, call_history, extension_list."
        )

    def get_dashboard_kpis(self) -> list[dict]:
        return [
            {"id": "tel_lines",  "label": "Lignes actives", "value": "—", "color": "#06b6d4"},
            {"id": "tel_calls",  "label": "Appels du jour", "value": "—"},
        ]
