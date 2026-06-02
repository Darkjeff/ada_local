"""
DomotiquePlugin — Plugin domotique pour ADA.
Univers : home. Dépendance : core/ha_state_watcher.py

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["domotique"] = True.
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin


class DomotiquePlugin(BasePlugin):

    plugin_id: str = "domotique"
    display_name: str = "Domotique"
    icon: str = "🏠"
    universe: str = "home"
    color: str = "#7c5cfc"

    def on_enable(self) -> None:
        print("[DomotiquePlugin] ✓ Module domotique activé")

    def on_disable(self) -> None:
        print("[DomotiquePlugin] Module domotique désactivé")

    def get_nav_items(self) -> list[dict]:
        return [{"label": "Domotique", "icon": "🏠", "route": "domotique"}]

    def get_chat_context(self, company_id: str | None = None) -> str:
        return (
            "Module Domotique actif. Tu contrôles les appareils de la maison via Home Assistant. "
            "Entités disponibles via l'API /api/page/home."
        )

    def get_skills(self) -> list[str]:
        return ["domotique"]

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        return [
            "Allume le salon",
            "Mode nuit",
            "Éteins tout",
            "Température du salon",
            "État de l'alarme",
        ]

    def get_function_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "control_light",
                    "description": "Allume, éteint ou dimme une lumière dans une pièce via Home Assistant.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action":      {"type": "string", "enum": ["on", "off", "dim"], "description": "Action : on/off/dim"},
                            "device_name": {"type": "string", "description": "Nom de la pièce ou de l'appareil (ex: salon, bureau, all)"},
                            "brightness":  {"type": "integer", "description": "Niveau de luminosité 0-100 (pour dim uniquement)"},
                        },
                        "required": ["action", "device_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scene_activate",
                    "description": "Active une scène Home Assistant (ambiance prédéfinie).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scene": {"type": "string", "enum": ["focus", "relax", "night", "off", "security"], "description": "Nom de la scène"},
                        },
                        "required": ["scene"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "thermostat_set",
                    "description": "Règle la température du thermostat dans une zone.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "zone":        {"type": "string", "description": "Zone ou pièce (ex: salon, chambre)"},
                            "temperature": {"type": "number", "description": "Température cible en °C"},
                        },
                        "required": ["zone", "temperature"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "alarm_set",
                    "description": "Arme ou désarme l'alarme de la maison. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "state": {"type": "string", "enum": ["arm", "disarm"], "description": "arm = armée, disarm = désarmée"},
                        },
                        "required": ["state"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Confirmer le {state} de l'alarme maison ?",
                    "x_confirm_cmd":      "ha alarm.{state}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "cover_control",
                    "description": "Contrôle un volet, store ou portail. CONFIRMATION REQUISE pour le portail.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string", "description": "Identifiant de l'entité (ex: portail, volet_salon)"},
                            "action": {"type": "string", "enum": ["open", "close", "stop"], "description": "Action à effectuer"},
                        },
                        "required": ["entity", "action"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Confirmer : {action} → {entity} ?",
                    "x_confirm_cmd":      "ha cover.{action} entity_id={entity}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "device_status",
                    "description": "Récupère l'état d'un appareil ou de tous les appareils domotiques.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string", "description": "ID de l'entité (optionnel — tous si absent)"},
                        },
                    },
                },
            },
        ]

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        return {
            "function_gemma": [
                "allume", "éteins", "lumière", "lampe", "salon", "bureau", "chambre",
                "mode nuit", "mode focus", "mode relax",
                "thermostat", "chauffage", "température",
                "alarme", "portail", "volet", "éclairage", "scène", "ambiance",
                "active la scène", "change la lumière", "règle le thermostat",
                "ouvre le portail", "ferme le portail", "arme l'alarme",
                "désarme l'alarme", "quel est l'état de", "status des appareils",
            ]
        }

    def get_n8n_webhooks(self) -> dict[str, str]:
        return {
            "control-light":  "http://localhost:5678/webhook/ha-control-light",
            "scene-activate": "http://localhost:5678/webhook/ha-scene",
            "thermostat-set": "http://localhost:5678/webhook/ha-thermostat",
            "alarm-set":      "http://localhost:5678/webhook/ha-alarm",
            "cover-control":  "http://localhost:5678/webhook/ha-cover",
        }

    def handle_action(self, action: str, params: dict) -> dict:
        try:
            from core.ha_control import ha_control
            if action == "control_light":
                result = ha_control.control_light(
                    params.get("device_name", "all"),
                    params.get("action", "on"),
                    params.get("brightness"),
                )
                return {"success": True, "message": f"Lumière {params.get('action')} — {params.get('device_name')}", "data": result}
            if action == "scene_activate":
                result = ha_control.activate_scene(params.get("scene", ""))
                return {"success": True, "message": f"Scène {params.get('scene')} activée", "data": result}
            if action == "thermostat_set":
                result = ha_control.set_thermostat(params.get("zone", ""), params.get("temperature", 20))
                return {"success": True, "message": f"Thermostat {params.get('zone')} → {params.get('temperature')}°C", "data": result}
            if action == "alarm_set":
                result = ha_control.set_alarm(params.get("state", "arm"))
                return {"success": True, "message": f"Alarme {params.get('state')}", "data": result}
            if action == "cover_control":
                result = ha_control.control_cover(params.get("entity", ""), params.get("action", "open"))
                return {"success": True, "message": f"{params.get('entity')} → {params.get('action')}", "data": result}
            if action == "device_status":
                from core.ha_state_watcher import ha_state_watcher
                states = ha_state_watcher.get_all_states()
                entity = params.get("entity")
                data = states.get(entity) if entity else states
                return {"success": True, "message": "État récupéré", "data": data}
        except Exception as exc:
            return {"success": False, "message": str(exc), "data": None}
        return {"success": False, "message": f"Action domotique {action} non gérée localement", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        return (
            "Tu contrôles la domotique via Home Assistant.\n"
            "Fonctions disponibles : control_light, scene_activate, thermostat_set, alarm_set, cover_control, device_status.\n"
            "RÈGLE : alarm_set et cover_control nécessitent TOUJOURS une confirmation avant exécution.\n"
            "Utilise device_status pour vérifier l'état avant d'agir si on te pose une question sur l'état des appareils."
        )

    def get_dashboard_kpis(self) -> list[dict]:
        kpis = [
            {"id": "domo_devices_on", "label": "Appareils actifs", "value": "—", "color": "#7c5cfc"},
            {"id": "domo_temp",       "label": "Température salon", "value": "—", "unit": "°C"},
            {"id": "domo_alarm",      "label": "Alarme",            "value": "—", "color": "#f59e0b"},
        ]
        try:
            from core.ha_state_watcher import ha_state_watcher
            states = ha_state_watcher.get_all_states()
            if states:
                on_count = sum(1 for s in states.values() if isinstance(s, dict) and s.get("state") in ("on", "open", "home"))
                kpis[0]["value"] = str(on_count)
        except Exception:
            pass
        return kpis
