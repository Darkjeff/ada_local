"""
ProxmoxPlugin — Plugin infrastructure Proxmox pour ADA.
Univers : opent.

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["proxmox"] = True.
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin


class ProxmoxPlugin(BasePlugin):

    plugin_id: str = "proxmox"
    display_name: str = "Infrastructure"
    icon: str = "🖥️"
    universe: str = "opent"
    color: str = "#00d4ff"

    def on_enable(self) -> None:
        print("[ProxmoxPlugin] ✓ Module proxmox activé")

    def on_disable(self) -> None:
        print("[ProxmoxPlugin] Module proxmox désactivé")

    def get_nav_items(self) -> list[dict]:
        return [{"label": "Infrastructure", "icon": "🖥️", "route": "infra"}]

    def get_chat_context(self, company_id: str | None = None) -> str:
        return (
            "Module Infrastructure Proxmox actif. "
            "Tu peux interroger les VMs, les nodes, les snapshots et les backups."
        )

    def get_skills(self) -> list[str]:
        return []

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        return [
            "Liste les VMs",
            "CPU et RAM des nodes",
            "Dernier backup réussi ?",
            "Espace disque NAS",
        ]

    def get_function_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "vm_list",
                    "description": "Liste les VMs Proxmox d'un node.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node": {"type": "string", "description": "Nom du node Proxmox (ex: pve, pve2)"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "vm_power",
                    "description": "Démarre, arrête ou redémarre une VM Proxmox. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":   {"type": "integer", "description": "ID de la VM"},
                            "action": {"type": "string", "enum": ["start", "stop", "reboot"], "description": "Action"},
                            "node":   {"type": "string", "description": "Nom du node Proxmox"},
                        },
                        "required": ["vmid", "action"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Confirmer l'action sur la VM {vmid} ?",
                    "x_confirm_cmd":      "qm {action} {vmid}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "vm_backup",
                    "description": "Lance une sauvegarde vzdump d'une VM vers le NAS. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":    {"type": "integer", "description": "ID de la VM à sauvegarder"},
                            "node":    {"type": "string",  "description": "Nom du node"},
                            "storage": {"type": "string",  "description": "Stockage cible (défaut: nas-backup)"},
                        },
                        "required": ["vmid"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Lancer le backup de la VM {vmid} vers le NAS ?",
                    "x_confirm_cmd":      "vzdump {vmid} --compress zstd --storage {storage}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "vm_snapshot",
                    "description": "Crée un snapshot d'une VM Proxmox. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":     {"type": "integer", "description": "ID de la VM"},
                            "snapname": {"type": "string",  "description": "Nom du snapshot"},
                            "node":     {"type": "string",  "description": "Nom du node"},
                        },
                        "required": ["vmid", "snapname"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Créer le snapshot '{snapname}' sur VM {vmid} ?",
                    "x_confirm_cmd":      "qm snapshot {vmid} {snapname}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "vm_restore",
                    "description": "Restaure une VM depuis un backup. CONFIRMATION REQUISE — action destructive.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":    {"type": "integer", "description": "ID de la VM cible"},
                            "backup":  {"type": "string",  "description": "Fichier de backup (chemin ou identifiant)"},
                            "storage": {"type": "string",  "description": "Stockage cible"},
                        },
                        "required": ["vmid", "backup"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "⚠ RESTAURATION VM {vmid} — cette opération est destructive et irréversible.",
                    "x_confirm_cmd":      "qmrestore {backup} {vmid} --storage {storage}",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "node_reboot",
                    "description": "Redémarre un node Proxmox. CONFIRMATION REQUISE — toutes les VMs seront affectées.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node": {"type": "string", "description": "Nom du node à redémarrer"},
                        },
                        "required": ["node"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "⚠ Redémarrer le node {node} ? Toutes les VMs seront interrompues.",
                    "x_confirm_cmd":      "ssh root@{node} reboot",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "node_stats",
                    "description": "Récupère les statistiques CPU, RAM et uptime d'un node Proxmox.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node": {"type": "string", "description": "Nom du node (optionnel — tous si absent)"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "storage_status",
                    "description": "Vérifie la capacité des datastores NAS et Proxmox.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node":    {"type": "string", "description": "Nom du node (optionnel)"},
                            "storage": {"type": "string", "description": "Nom du storage (optionnel)"},
                        },
                    },
                },
            },
        ]

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        return {
            "function_gemma": [
                "proxmox", "vm", "machine virtuelle", "backup", "sauvegarde", "snapshot",
                "serveur", "node", "RAM serveur", "CPU serveur", "infrastructure",
                "redémarre", "stoppe la vm", "vzdump", "NAS", "restaure",
                "espace datastore", "liste les vms", "démarre la vm",
                "mémoire serveur", "charge serveur", "reboot node",
            ]
        }

    def get_n8n_webhooks(self) -> dict[str, str]:
        return {
            "vm-list":     "http://localhost:5678/webhook/proxmox-vm-list",
            "vm-power":    "http://localhost:5678/webhook/proxmox-vm-power",
            "vm-backup":   "http://localhost:5678/webhook/proxmox-vm-backup",
            "vm-snapshot": "http://localhost:5678/webhook/proxmox-vm-snapshot",
            "vm-restore":  "http://localhost:5678/webhook/proxmox-vm-restore",
            "node-reboot": "http://localhost:5678/webhook/proxmox-node-reboot",
            "node-stats":  "http://localhost:5678/webhook/proxmox-node-stats",
        }

    def handle_action(self, action: str, params: dict) -> dict:
        return {"success": False, "message": f"Action Proxmox {action} : connecteur n8n requis", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        return (
            "Tu gères l'infrastructure Proxmox.\n"
            "Fonctions disponibles : vm_list, vm_power, vm_backup, vm_snapshot, vm_restore, node_reboot, node_stats, storage_status.\n"
            "RÈGLE CRITIQUE : vm_power, vm_backup, vm_snapshot, vm_restore et node_reboot nécessitent TOUJOURS une confirmation explicite avant exécution.\n"
            "node_reboot est particulièrement dangereux : toutes les VMs du node seront affectées — insiste sur ce point."
        )

    def get_dashboard_kpis(self) -> list[dict]:
        return [
            {"id": "prox_nodes",   "label": "Nodes online",  "value": "—", "color": "#00d4ff"},
            {"id": "prox_cpu",     "label": "CPU global",    "value": "—", "unit": "%"},
            {"id": "prox_ram",     "label": "RAM utilisée",  "value": "—"},
            {"id": "prox_backups", "label": "Backups 24h",   "value": "—"},
        ]
