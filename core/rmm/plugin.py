"""
RmmPlugin — Plugin supervision/RMM clients pour ADA.
Univers : opent.

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["rmm"] = True.
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin


class RmmPlugin(BasePlugin):

    plugin_id: str = "rmm"
    display_name: str = "Supervision"
    icon: str = "📡"
    universe: str = "opent"
    color: str = "#f59e0b"

    def on_enable(self) -> None:
        print("[RmmPlugin] ✓ Module rmm activé")

    def on_disable(self) -> None:
        print("[RmmPlugin] Module rmm désactivé")

    def get_nav_items(self) -> list[dict]:
        return [{"label": "Supervision", "icon": "📡", "route": "rmm"}]

    def get_chat_context(self, company_id: str | None = None) -> str:
        return (
            "Module RMM actif. "
            "Tu supervises les postes et serveurs clients. "
            "Tu peux lister les alertes, consulter l'état d'un client, redémarrer des services."
        )

    def get_skills(self) -> list[str]:
        return []

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        return [
            "Alertes actives",
            "État des clients",
            "Disques pleins ?",
            "Services arrêtés ?",
        ]

    def get_function_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "rmm_alerts_list",
                    "description": "Liste toutes les alertes actives sur l'ensemble des clients supervisés.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["all", "critical", "warning", "info"], "description": "Filtre par sévérité"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rmm_client_status",
                    "description": "Récupère l'état de supervision d'un client spécifique.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name": {"type": "string", "description": "Nom du client"},
                        },
                        "required": ["client_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rmm_service_restart",
                    "description": "Redémarre un service Windows sur un poste client distant. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name":   {"type": "string", "description": "Nom du client"},
                            "service_name":  {"type": "string", "description": "Nom du service Windows (ex: SVC_BACKUP, W3SVC)"},
                            "computer_name": {"type": "string", "description": "Nom de la machine (optionnel)"},
                        },
                        "required": ["client_name", "service_name"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Redémarrer le service {service_name} chez {client_name} ?",
                    "x_confirm_cmd":      "Restart-Service -Name {service_name} -ComputerName {computer_name}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rmm_disk_cleanup",
                    "description": "Lance un nettoyage disque sur un poste client distant. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name":   {"type": "string", "description": "Nom du client"},
                            "computer_name": {"type": "string", "description": "Nom de la machine"},
                            "drive":         {"type": "string", "description": "Lettre du disque (défaut: C)"},
                        },
                        "required": ["client_name"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Lancer le nettoyage disque {drive}: sur {computer_name} ({client_name}) ?",
                    "x_confirm_cmd":      "cleanmgr /sagerun:1 /d {drive} @ {computer_name}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rmm_computer_reboot",
                    "description": "Redémarre un poste client à distance. CONFIRMATION REQUISE — interruption de service.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name":   {"type": "string", "description": "Nom du client"},
                            "computer_name": {"type": "string", "description": "Nom de la machine à redémarrer"},
                            "delay_minutes": {"type": "integer", "description": "Délai avant redémarrage en minutes (défaut: 0)"},
                        },
                        "required": ["client_name", "computer_name"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "⚠ Redémarrer {computer_name} chez {client_name} ? L'utilisateur sera déconnecté.",
                    "x_confirm_cmd":      "Restart-Computer -ComputerName {computer_name} -Delay {delay_minutes}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rmm_script_run",
                    "description": "Exécute un script PowerShell sur un poste client. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name":   {"type": "string", "description": "Nom du client"},
                            "computer_name": {"type": "string", "description": "Nom de la machine"},
                            "script_name":   {"type": "string", "description": "Nom du script à exécuter"},
                        },
                        "required": ["client_name", "script_name"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Exécuter le script '{script_name}' sur {computer_name} ({client_name}) ?",
                    "x_confirm_cmd":      "Invoke-Command -ComputerName {computer_name} -ScriptBlock {{ .\\{script_name} }}",
                },
            },
        ]

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        return {
            "function_gemma": [
                "rmm", "client", "alerte client", "disque plein", "service arrêté",
                "monitoring client", "supervision", "poste distant", "redémarre le service",
                "alertes actives", "état des clients", "serveur client",
                "nettoyage disque", "redémarre le poste", "script rmm",
            ]
        }

    def get_n8n_webhooks(self) -> dict[str, str]:
        return {
            "rmm-alerts-list":     "http://localhost:5678/webhook/rmm-alerts",
            "rmm-client-status":   "http://localhost:5678/webhook/rmm-client-status",
            "rmm-service-restart": "http://localhost:5678/webhook/rmm-service-restart",
            "rmm-disk-cleanup":    "http://localhost:5678/webhook/rmm-disk-cleanup",
            "rmm-computer-reboot": "http://localhost:5678/webhook/rmm-computer-reboot",
            "rmm-script-run":      "http://localhost:5678/webhook/rmm-script-run",
        }

    def handle_action(self, action: str, params: dict) -> dict:
        return {"success": False, "message": f"Action RMM {action} : connecteur n8n requis", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        return (
            "Tu supervises les clients via le RMM.\n"
            "Fonctions disponibles : rmm_alerts_list, rmm_client_status, rmm_service_restart, "
            "rmm_disk_cleanup, rmm_computer_reboot, rmm_script_run.\n"
            "RÈGLE CRITIQUE : rmm_service_restart, rmm_disk_cleanup, rmm_computer_reboot et rmm_script_run "
            "nécessitent TOUJOURS une confirmation explicite avant exécution.\n"
            "rmm_computer_reboot est particulièrement impactant : l'utilisateur distant sera déconnecté."
        )

    def get_dashboard_kpis(self) -> list[dict]:
        return [
            {"id": "rmm_alerts",  "label": "Alertes actives", "value": "—", "color": "#ef4444"},
            {"id": "rmm_clients", "label": "Clients OK",       "value": "—", "color": "#22c55e"},
        ]
