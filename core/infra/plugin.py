"""
ProxmoxPlugin v2 — Plugin infrastructure Proxmox pour ADA.
Multi-instance · PBS · Profils de backup · Affectation univers/société/tag.

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["proxmox"] = True.

MODULE_SOCIETE: get_system_prompt_injection() filtre par context_id (univers ou company_id).
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin
from core.infra.proxmox_config import (
    PROXMOX_INSTANCES,
    PBS_INSTANCES,
    PROXMOX_BACKUP_PROFILES,
)


class ProxmoxPlugin(BasePlugin):

    plugin_id: str    = "proxmox"
    display_name: str = "Infrastructure"
    icon: str         = "🖥️"
    universe: str     = "opent"
    color: str        = "#00d4ff"

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def on_enable(self) -> None:
        print("[ProxmoxPlugin] ✓ Module proxmox activé (v2 multi-instance)")

    def on_disable(self) -> None:
        print("[ProxmoxPlugin] Module proxmox désactivé")

    # ── Navigation & contexte ─────────────────────────────────────────────────

    def get_nav_items(self) -> list[dict]:
        return [{"label": "Infrastructure", "icon": "🖥️", "route": "infra"}]

    def get_chat_context(self, company_id: str | None = None) -> str:
        instances = self._get_instances_for_context(company_id)
        if not instances:
            return "Module Infrastructure Proxmox actif (aucune instance configurée)."
        names = ", ".join(i["label"] for i in instances)
        return (
            f"Module Infrastructure Proxmox actif — instances : {names}. "
            "Tu peux interroger les VMs, les nodes, les snapshots, les backups et les serveurs PBS."
        )

    def get_skills(self) -> list[str]:
        return []

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        return [
            "Liste les VMs",
            "CPU et RAM des nodes",
            "Dernier backup réussi ?",
            "État du PBS",
            "Espace disque datastores",
            "Instances Proxmox disponibles",
        ]

    # ── Filtrage par contexte ─────────────────────────────────────────────────

    def _get_instances_for_context(self, context_id: str | None) -> list[dict]:
        """
        Retourne les instances PVE pertinentes selon le contexte actif.
        context_id peut être un univers ('opent', 'home'…) ou un company_id.
        """
        if context_id is None:
            return [i for i in PROXMOX_INSTANCES if i["enabled"]]
        return [
            i for i in PROXMOX_INSTANCES
            if i["enabled"] and (
                i.get("universe")    == context_id or
                i.get("company_id")  == context_id or
                context_id in i.get("tags", [])
            )
        ]

    def _get_pbs_for_context(self, context_id: str | None) -> list[dict]:
        if context_id is None:
            return [p for p in PBS_INSTANCES if p["enabled"]]
        return [
            p for p in PBS_INSTANCES
            if p["enabled"] and (
                p.get("universe")   == context_id or
                p.get("company_id") == context_id or
                context_id in p.get("tags", [])
            )
        ]

    # ── System prompt injection ───────────────────────────────────────────────

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        instances = self._get_instances_for_context(context_id)
        pbs_list  = self._get_pbs_for_context(context_id)
        profiles  = [
            pr for pr in PROXMOX_BACKUP_PROFILES
            if not context_id or pr.get("universe") == context_id
        ]

        instance_lines = "\n".join(
            f"  - {i['id']} : {i['label']} ({i['host']}) — tags: {', '.join(i.get('tags', []))}"
            for i in instances
        ) or "  Aucune instance activée"

        pbs_lines = "\n".join(
            f"  - {p['id']} : {p['label']} ({p['host']})"
            for p in pbs_list
        ) or "  Aucun PBS configuré"

        profile_lines = "\n".join(
            f"  - {pr['id']} : {pr['label']} (storage: {pr['storage']}, rétention: {pr['retention']})"
            for pr in profiles
        ) or "  Aucun profil défini"

        return f"""Tu gères l'infrastructure Proxmox (multi-instance).
Instances disponibles :
{instance_lines}

Serveurs PBS disponibles :
{pbs_lines}

Profils de backup disponibles :
{profile_lines}

Fonctions disponibles : vm_list, vm_power, vm_backup, vm_snapshot, vm_restore,
                        node_reboot, node_stats, storage_status,
                        pbs_status, pbs_backup_run, pbs_restore, backup_list,
                        proxmox_instances_list.

RÈGLES :
- vm_power (stop/reboot), vm_backup, vm_snapshot, vm_restore, node_reboot,
  pbs_backup_run, pbs_restore : TOUJOURS demander confirmation avant exécution.
- Si l'utilisateur ne précise pas l'instance et qu'il y en a plusieurs dans le contexte,
  demande sur quelle instance il veut agir.
- node_reboot : avertir que toutes les VMs du node seront impactées.""".strip()

    # ── Fonctions LLM ─────────────────────────────────────────────────────────

    def get_function_definitions(self) -> list[dict]:
        return [
            # ── vm_list ───────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "vm_list",
                    "description": "Liste les VMs QEMU et containers LXC (CT) d'une instance Proxmox. Utiliser pour toute demande de liste/affichage de VM, CT, machines virtuelles, conteneurs. Peut filtrer par instance et/ou node.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instance_id": {"type": "string",  "description": "ID de l'instance PVE (optionnel — toutes si absent)"},
                            "node":        {"type": "string",  "description": "Nom du node Proxmox (optionnel)"},
                        },
                    },
                },
            },
            # ── vm_power ──────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "vm_power",
                    "description": "Démarre, arrête ou redémarre une VM Proxmox. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "ID de la VM"},
                            "action":      {"type": "string",  "enum": ["start", "stop", "reboot", "shutdown"], "description": "Action"},
                            "node":        {"type": "string",  "description": "Nom du node Proxmox"},
                            "instance_id": {"type": "string",  "description": "ID de l'instance PVE"},
                        },
                        "required": ["vmid", "action", "instance_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Confirmer l'action '{action}' sur la VM {vmid} (instance {instance_id}) ?",
                    "x_confirm_cmd":      "qm {action} {vmid}",
                },
            },
            # ── vm_backup ─────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "vm_backup",
                    "description": "Lance une sauvegarde vzdump d'une VM. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "ID de la VM à sauvegarder"},
                            "node":        {"type": "string",  "description": "Nom du node"},
                            "instance_id": {"type": "string",  "description": "ID de l'instance PVE"},
                            "storage":     {"type": "string",  "description": "Stockage cible (défaut: local)"},
                            "profile_id":  {"type": "string",  "description": "ID du profil de backup (optionnel)"},
                        },
                        "required": ["vmid", "instance_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Lancer le backup de la VM {vmid} sur l'instance {instance_id} ?",
                    "x_confirm_cmd":      "vzdump {vmid} --compress zstd --storage {storage}",
                },
            },
            # ── vm_snapshot ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "vm_snapshot",
                    "description": "Crée un snapshot d'une VM Proxmox. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "ID de la VM"},
                            "snapname":    {"type": "string",  "description": "Nom du snapshot"},
                            "node":        {"type": "string",  "description": "Nom du node"},
                            "instance_id": {"type": "string",  "description": "ID de l'instance PVE"},
                        },
                        "required": ["vmid", "snapname", "instance_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Créer le snapshot '{snapname}' sur VM {vmid} (instance {instance_id}) ?",
                    "x_confirm_cmd":      "qm snapshot {vmid} {snapname}",
                },
            },
            # ── vm_restore ────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "vm_restore",
                    "description": "Restaure une VM depuis un backup. CONFIRMATION REQUISE — action destructive.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "ID de la VM cible"},
                            "backup":      {"type": "string",  "description": "Fichier/identifiant de backup"},
                            "storage":     {"type": "string",  "description": "Stockage cible"},
                            "instance_id": {"type": "string",  "description": "ID de l'instance PVE"},
                        },
                        "required": ["vmid", "backup", "instance_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "⚠ RESTAURATION VM {vmid} sur {instance_id} — opération destructive et irréversible.",
                    "x_confirm_cmd":      "qmrestore {backup} {vmid} --storage {storage}",
                },
            },
            # ── node_reboot ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "node_reboot",
                    "description": "Redémarre un node Proxmox. CONFIRMATION REQUISE — toutes les VMs seront affectées.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node":        {"type": "string", "description": "Nom du node à redémarrer"},
                            "instance_id": {"type": "string", "description": "ID de l'instance PVE"},
                        },
                        "required": ["node", "instance_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "⚠ Redémarrer le node {node} sur {instance_id} ? Toutes les VMs seront interrompues.",
                    "x_confirm_cmd":      "ssh root@{node} reboot",
                },
            },
            # ── node_stats ────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "node_stats",
                    "description": "Récupère les statistiques CPU, RAM et uptime d'un ou plusieurs nodes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node":        {"type": "string", "description": "Nom du node (tous si absent)"},
                            "instance_id": {"type": "string", "description": "ID de l'instance PVE (toutes si absent)"},
                        },
                    },
                },
            },
            # ── storage_status ────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "storage_status",
                    "description": "Vérifie la capacité des datastores Proxmox.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node":        {"type": "string", "description": "Nom du node (optionnel)"},
                            "storage":     {"type": "string", "description": "Nom du storage (optionnel)"},
                            "instance_id": {"type": "string", "description": "ID de l'instance PVE (toutes si absent)"},
                        },
                    },
                },
            },
            # ── pbs_status ────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "pbs_status",
                    "description": "Affiche l'état d'un serveur PBS : datastores, jobs actifs, espace utilisé.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pbs_id": {"type": "string", "description": "ID de l'instance PBS (tous si absent)"},
                        },
                    },
                },
            },
            # ── pbs_backup_run ────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "pbs_backup_run",
                    "description": "Déclenche un backup PBS immédiat selon un profil défini. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "ID de la VM/LXC à sauvegarder"},
                            "instance_id": {"type": "string",  "description": "Instance Proxmox source"},
                            "pbs_id":      {"type": "string",  "description": "Instance PBS cible"},
                            "profile_id":  {"type": "string",  "description": "Profil de backup (rétention, compression) — optionnel"},
                        },
                        "required": ["vmid", "instance_id", "pbs_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Lancer le backup PBS de la VM {vmid} vers {pbs_id} avec le profil {profile_id} ?",
                    "x_confirm_cmd":      "vzdump {vmid} --storage {pbs_id}",
                },
            },
            # ── pbs_restore ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "pbs_restore",
                    "description": "Restaure une VM depuis un backup PBS. CONFIRMATION REQUISE.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "ID VM à restaurer"},
                            "snapshot_id": {"type": "string",  "description": "Identifiant du snapshot PBS"},
                            "pbs_id":      {"type": "string",  "description": "Instance PBS source"},
                            "instance_id": {"type": "string",  "description": "Instance Proxmox cible"},
                            "target_vmid": {"type": "integer", "description": "Nouvel ID VM (optionnel — écrase si absent)"},
                        },
                        "required": ["vmid", "snapshot_id", "pbs_id", "instance_id"],
                    },
                    "x_confirm_required": True,
                    "x_confirm_message":  "Restaurer la VM {vmid} depuis le snapshot {snapshot_id} sur PBS {pbs_id} ? Cette opération écrasera la VM existante.",
                    "x_confirm_cmd":      "qmrestore {pbs_id}:{snapshot_id} {vmid} --force",
                },
            },
            # ── backup_list ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "backup_list",
                    "description": "Liste les backups disponibles pour une VM, sur PBS ou sur le stockage local.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "vmid":        {"type": "integer", "description": "Filtrer par VM (tous si absent)"},
                            "instance_id": {"type": "string",  "description": "Instance Proxmox (optionnel)"},
                            "pbs_id":      {"type": "string",  "description": "Instance PBS (stockage local si absent)"},
                        },
                    },
                },
            },
            # ── proxmox_instances_list ────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "proxmox_instances_list",
                    "description": "Liste toutes les instances Proxmox configurées et leur état (activées/désactivées).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "universe":   {"type": "string", "description": "Filtre par univers (optionnel)"},
                            "company_id": {"type": "string", "description": "Filtre par société (optionnel)"},
                            "tag":        {"type": "string", "description": "Filtre par tag (optionnel)"},
                        },
                    },
                },
            },
        ]

    # ── Utterances semantic_router ────────────────────────────────────────────

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        return {
            "function_gemma": [
                # Proxmox général
                "proxmox", "vm", "machine virtuelle", "backup", "sauvegarde", "snapshot",
                "serveur", "node", "RAM serveur", "CPU serveur", "infrastructure",
                "redémarre", "stoppe la vm", "vzdump", "NAS", "restaure",
                "espace datastore", "liste les vms", "démarre la vm",
                "mémoire serveur", "charge serveur", "reboot node",
                # PBS
                "pbs", "proxmox backup server", "datastore", "backup pbs",
                "restauration", "restore", "point de restauration",
                "retention", "rétention backup",
                # Multi-instance
                "quelle instance", "sur quel proxmox", "les deux proxmox",
                "proxmox maison", "proxmox opentechno",
            ]
        }

    # ── Webhooks n8n ──────────────────────────────────────────────────────────

    def get_n8n_webhooks(self) -> dict[str, str]:
        return {
            # Proxmox VE
            "vm-list":       "http://localhost:5678/webhook/proxmox-vm-list",
            "vm-power":      "http://localhost:5678/webhook/proxmox-vm-power",
            "vm-backup":     "http://localhost:5678/webhook/proxmox-vm-backup",
            "vm-snapshot":   "http://localhost:5678/webhook/proxmox-vm-snapshot",
            "vm-restore":    "http://localhost:5678/webhook/proxmox-vm-restore",
            "node-reboot":   "http://localhost:5678/webhook/proxmox-node-reboot",
            "node-stats":    "http://localhost:5678/webhook/proxmox-node-stats",
            "storage-status":"http://localhost:5678/webhook/proxmox-storage-status",
            # PBS — nouveaux
            "pbs-status":     "http://localhost:5678/webhook/pbs-status",
            "pbs-backup-run": "http://localhost:5678/webhook/pbs-backup-run",
            "pbs-restore":    "http://localhost:5678/webhook/pbs-restore",
            "backup-list":    "http://localhost:5678/webhook/backup-list",
        }

    # ── Handle action ─────────────────────────────────────────────────────────

    def handle_action(self, action: str, params: dict) -> dict:
        """
        Exécute les actions Proxmox directement via ProxmoxClient / PBSClient.
        Les actions x_confirm_required passent ici UNIQUEMENT après confirmation de l'utilisateur.
        """
        from core.async_runner import run_async
        try:
            if action == "proxmox_instances_list":
                return self._action_instances_list(params)
            elif action == "vm_list":
                return run_async(self._async_vm_list(params))
            elif action == "node_stats":
                return run_async(self._async_node_stats(params))
            elif action == "storage_status":
                return run_async(self._async_storage_status(params))
            elif action == "pbs_status":
                return run_async(self._async_pbs_status(params))
            elif action == "backup_list":
                return run_async(self._async_backup_list(params))
            elif action == "vm_power":
                return run_async(self._async_vm_power(params))
            elif action == "vm_backup":
                return run_async(self._async_vm_backup(params))
            elif action == "vm_snapshot":
                return run_async(self._async_vm_snapshot(params))
            elif action == "node_reboot":
                return run_async(self._async_node_reboot(params))
            elif action == "pbs_backup_run":
                return run_async(self._async_pbs_backup_run(params))
            else:
                return {"success": False, "message": f"Action '{action}' non implémentée localement."}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("[ProxmoxPlugin] handle_action %s: %s", action, exc)
            return {"success": False, "message": str(exc)}

    # ── Helpers synchrones ────────────────────────────────────────────────────

    def _action_instances_list(self, params: dict) -> dict:
        universe   = params.get("universe")
        company_id = params.get("company_id")
        tag        = params.get("tag")
        result = []
        for i in PROXMOX_INSTANCES:
            if universe   and i.get("universe")   != universe:   continue
            if company_id and i.get("company_id") != company_id: continue
            if tag        and tag not in i.get("tags", []):       continue
            result.append(f"- **{i['id']}** : {i['label']} ({i['host']}) — {'✓ activée' if i['enabled'] else '✗ désactivée'}")
        if not result:
            return {"success": True, "message": "Aucune instance Proxmox configurée."}
        return {"success": True, "message": "Instances Proxmox configurées :\n" + "\n".join(result)}

    # ── Coroutines async ──────────────────────────────────────────────────────

    async def _async_vm_list(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        instance_id = params.get("instance_id")
        node        = params.get("node")
        instances   = (
            [self._get_single_instance(instance_id)]
            if instance_id else self._get_instances_for_context(None)
        )
        instances = [i for i in instances if i]
        if not instances:
            return {"success": False, "message": "Aucune instance Proxmox activée."}
        lines = []
        for inst in instances:
            try:
                client = ProxmoxClient(inst)
                vms = await client.list_vms(node=node)
                n_qemu = sum(1 for v in vms if v.get("type") != "lxc")
                n_lxc  = sum(1 for v in vms if v.get("type") == "lxc")
                if not vms:
                    lines.append(f"\n**{inst['label']}** — ⚠️ Aucune VM/CT visible.")
                    lines.append("  → Le token API n'a pas les droits VM.Audit.")
                    lines.append("  → Sur le serveur Proxmox : `pveum acl modify / --tokens root@pam!ada --roles PVEAdmin`")
                else:
                    lines.append(f"\n**{inst['label']}** — {n_qemu} VM(s) · {n_lxc} CT(s) :")
                    for vm in sorted(vms, key=lambda v: int(v.get('vmid', 0)))[:50]:
                        status = "▶" if vm.get("status") == "running" else "■"
                        kind   = "CT" if vm.get("type") == "lxc" else "VM"
                        lines.append(f"  {status} {kind} {vm['vmid']} — {vm.get('name','?')} [{vm.get('status','?')}] node:{vm.get('node','?')}")
            except Exception as e:
                lines.append(f"\n**{inst['label']}** : ❌ {e}")
        return {"success": True, "message": "\n".join(lines)}

    async def _async_node_stats(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        instance_id = params.get("instance_id")
        node_filter = params.get("node")
        instances   = (
            [self._get_single_instance(instance_id)]
            if instance_id else self._get_instances_for_context(None)
        )
        instances = [i for i in instances if i]
        if not instances:
            return {"success": False, "message": "Aucune instance Proxmox activée."}
        lines = []
        for inst in instances:
            try:
                client = ProxmoxClient(inst)
                nodes  = await client.list_nodes()
                lines.append(f"\n**{inst['label']}** :")
                for n in nodes:
                    if node_filter and n["node"] != node_filter:
                        continue
                    cpu  = round(n.get("cpu", 0) * 100, 1)
                    ram  = round(n.get("mem",    0) / 1_073_741_824, 1)
                    ramt = round(n.get("maxmem", 0) / 1_073_741_824, 1)
                    disk = round(n.get("disk",    0) / 1_073_741_824, 1)
                    diskt= round(n.get("maxdisk", 0) / 1_073_741_824, 1)
                    status = "✓" if n.get("status") == "online" else "✗"
                    lines.append(
                        f"  {status} **{n['node']}** — CPU:{cpu}% RAM:{ram}/{ramt}GB Disk:{disk}/{diskt}GB"
                    )
            except Exception as e:
                lines.append(f"\n**{inst['label']}** : ❌ {e}")
        return {"success": True, "message": "\n".join(lines)}

    async def _async_storage_status(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        instance_id     = params.get("instance_id")
        node_filter     = params.get("node")
        storage_filter  = params.get("storage")
        instances = (
            [self._get_single_instance(instance_id)]
            if instance_id else self._get_instances_for_context(None)
        )
        instances = [i for i in instances if i]
        if not instances:
            return {"success": False, "message": "Aucune instance Proxmox activée."}
        lines = []
        for inst in instances:
            try:
                client = ProxmoxClient(inst)
                nodes  = await client.list_nodes()
                lines.append(f"\n**{inst['label']}** :")
                for n in nodes:
                    if node_filter and n["node"] != node_filter:
                        continue
                    storages = await client._get(f"/nodes/{n['node']}/storage") or []
                    for s in storages:
                        if storage_filter and s.get("storage") != storage_filter:
                            continue
                        used  = round(s.get("used",  0) / 1_073_741_824, 1)
                        total = round(s.get("total", 0) / 1_073_741_824, 1)
                        pct   = round(used / total * 100, 0) if total else 0
                        avail = round(s.get("avail", 0) / 1_073_741_824, 1)
                        lines.append(
                            f"  📦 {s['storage']} ({s.get('type','?')}) node:{n['node']} — {used}/{total}GB utilisés ({pct}%) — {avail}GB libres"
                        )
            except Exception as e:
                lines.append(f"\n**{inst['label']}** : ❌ {e}")
        return {"success": True, "message": "\n".join(lines)}

    async def _async_pbs_status(self, params: dict) -> dict:
        from core.infra.pbs_client import PBSClient
        pbs_id   = params.get("pbs_id")
        pbs_list = (
            [self._get_single_pbs(pbs_id)]
            if pbs_id else self._get_pbs_for_context(None)
        )
        pbs_list = [p for p in pbs_list if p]
        if not pbs_list:
            return {"success": False, "message": "Aucun serveur PBS activé."}
        lines = []
        for pbs in pbs_list:
            try:
                client     = PBSClient(pbs)
                datastores = await client.list_datastores()
                lines.append(f"\n**{pbs['label']}** ({pbs['host']}) :")
                for ds in datastores:
                    used  = round(ds.get("used",  0) / 1_073_741_824, 1)
                    total = round(ds.get("total", 0) / 1_073_741_824, 1)
                    avail = round(ds.get("avail", 0) / 1_073_741_824, 1)
                    lines.append(
                        f"  🗄 {ds.get('store','?')} — {used}/{total}GB ({avail}GB libres)"
                    )
                if not datastores:
                    lines.append("  Aucun datastore.")
            except Exception as e:
                lines.append(f"\n**{pbs['label']}** : ❌ {e}")
        return {"success": True, "message": "\n".join(lines)}

    async def _async_backup_list(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        from core.infra.pbs_client import PBSClient
        vmid        = params.get("vmid")
        instance_id = params.get("instance_id")
        pbs_id      = params.get("pbs_id")
        lines = []
        # PBS backups
        if pbs_id or PBS_INSTANCES:
            pbs_list = [self._get_single_pbs(pbs_id)] if pbs_id else self._get_pbs_for_context(None)
            pbs_list = [p for p in pbs_list if p]
            for pbs in pbs_list:
                try:
                    client     = PBSClient(pbs)
                    datastores = await client.list_datastores()
                    for ds in datastores:
                        snaps = await client.list_snapshots(ds.get("store",""), vmid=vmid)
                        if snaps:
                            lines.append(f"\n**PBS {pbs['label']}** — datastore {ds.get('store','?')} :")
                            for s in snaps[:15]:
                                lines.append(f"  📂 {s.get('backup-id','?')} — {s.get('backup-time','?')}")
                except Exception as e:
                    lines.append(f"\n**PBS {pbs['label']}** : ❌ {e}")
        # PVE local backups
        if not pbs_id:
            instances = [self._get_single_instance(instance_id)] if instance_id else self._get_instances_for_context(None)
            instances = [i for i in instances if i]
            for inst in instances:
                try:
                    client  = ProxmoxClient(inst)
                    backups = await client.backup_list(vmid=vmid, storage="local")
                    if backups:
                        lines.append(f"\n**{inst['label']}** — stockage local :")
                        for b in backups[:10]:
                            lines.append(f"  📂 {b.get('volid','?')} — VM {b.get('vmid','?')}")
                except Exception:
                    pass
        if not lines:
            return {"success": True, "message": "Aucun backup trouvé."}
        return {"success": True, "message": "Backups disponibles :" + "\n".join(lines)}

    async def _find_vm_node(self, client, vmid: int) -> tuple[str, str]:
        """Résout le node et le type (qemu/lxc) d'une VM/CT depuis son vmid."""
        try:
            vms = await client.list_vms()
            for vm in vms:
                if int(vm.get("vmid", -1)) == vmid:
                    return vm.get("node", ""), vm.get("type", "qemu")
        except Exception:
            pass
        return "", "qemu"

    async def _async_vm_power(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        inst = self._get_single_instance(params.get("instance_id"))
        if not inst:
            return {"success": False, "message": "Instance introuvable."}
        client = ProxmoxClient(inst)
        vmid = int(params["vmid"])
        node = params.get("node") or ""
        vm_type = params.get("vm_type") or ""
        if not node:
            node, vm_type = await self._find_vm_node(client, vmid)
            if not node:
                return {"success": False, "message": f"VM/CT {vmid} introuvable sur cette instance."}
        await client.vm_power(node, vmid, params["action"], vm_type=vm_type or "qemu")
        kind = "CT" if vm_type == "lxc" else "VM"
        return {"success": True, "message": f"Action '{params['action']}' lancée sur {kind} {vmid} (node: {node})."}

    async def _async_vm_backup(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        inst = self._get_single_instance(params.get("instance_id"))
        if not inst:
            return {"success": False, "message": "Instance introuvable."}
        client  = ProxmoxClient(inst)
        vmid = int(params["vmid"])
        node = params.get("node") or ""
        if not node:
            node, _ = await self._find_vm_node(client, vmid)
            if not node:
                return {"success": False, "message": f"VM/CT {vmid} introuvable sur cette instance."}
        storage = params.get("storage", "local")
        await client.vm_backup(node, vmid, storage=storage)
        return {"success": True, "message": f"Backup lancé pour la VM/CT {vmid} → storage '{storage}'."}

    async def _async_vm_snapshot(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        inst = self._get_single_instance(params.get("instance_id"))
        if not inst:
            return {"success": False, "message": "Instance introuvable."}
        client = ProxmoxClient(inst)
        await client.vm_snapshot(params.get("node",""), int(params["vmid"]), params["snapname"])
        return {"success": True, "message": f"Snapshot '{params['snapname']}' créé sur VM {params['vmid']}."}

    async def _async_node_reboot(self, params: dict) -> dict:
        from core.infra.proxmox_client import ProxmoxClient
        inst = self._get_single_instance(params.get("instance_id"))
        if not inst:
            return {"success": False, "message": "Instance introuvable."}
        client = ProxmoxClient(inst)
        await client.node_reboot(params["node"])
        return {"success": True, "message": f"Redémarrage du node {params['node']} lancé."}

    async def _async_pbs_backup_run(self, params: dict) -> dict:
        return {"success": False, "message": "pbs_backup_run via API PBS non encore implémenté — utilisez n8n."}

    # ── Helpers de résolution d'instance ─────────────────────────────────────

    def _get_single_instance(self, instance_id: str | None) -> dict | None:
        if not instance_id:
            enabled = [i for i in PROXMOX_INSTANCES if i["enabled"]]
            return enabled[0] if len(enabled) == 1 else None
        # 1. Match exact par id
        inst = next((i for i in PROXMOX_INSTANCES if i["id"] == instance_id), None)
        if inst:
            return inst
        # 2. Match par label (insensible à la casse)
        iid_l = instance_id.lower().replace("-", " ").replace("_", " ")
        for i in PROXMOX_INSTANCES:
            label_l = i.get("label", "").lower().replace("-", " ").replace("_", " ")
            id_l    = i["id"].lower()
            if label_l == iid_l or id_l == instance_id.lower():
                return i
        # 3. Match partiel — label ou id contient le terme (ou inversement)
        for i in PROXMOX_INSTANCES:
            label_l = i.get("label", "").lower().replace("-", " ").replace("_", " ")
            id_l    = i["id"].lower()
            if iid_l in label_l or label_l in iid_l or iid_l in id_l:
                return i
        # 4. Repli : si une seule instance activée, l'utiliser
        enabled = [i for i in PROXMOX_INSTANCES if i["enabled"]]
        return enabled[0] if len(enabled) == 1 else None

    def _get_single_pbs(self, pbs_id: str | None) -> dict | None:
        if not pbs_id:
            enabled = [p for p in PBS_INSTANCES if p["enabled"]]
            return enabled[0] if len(enabled) == 1 else None
        inst = next((p for p in PBS_INSTANCES if p["id"] == pbs_id), None)
        if inst:
            return inst
        pbs_l = pbs_id.lower().replace("-", " ").replace("_", " ")
        for p in PBS_INSTANCES:
            label_l = p.get("label", "").lower().replace("-", " ").replace("_", " ")
            if pbs_l in label_l or label_l in pbs_l or pbs_l in p["id"].lower():
                return p
        enabled = [p for p in PBS_INSTANCES if p["enabled"]]
        return enabled[0] if len(enabled) == 1 else None

    # ── KPIs dashboard ────────────────────────────────────────────────────────

    def get_dashboard_kpis(self) -> list[dict]:
        """
        KPIs multi-instance. Les valeurs '—' sont des placeholders ;
        le vrai remplissage se fait via /api/proxmox/kpis (routes_infra.py).
        """
        instances = [i for i in PROXMOX_INSTANCES if i["enabled"]]
        pbs_list  = [p for p in PBS_INSTANCES if p["enabled"]]

        inst_detail = " · ".join(f"{i['id']}: —/— nodes" for i in instances) or "—"
        pbs_detail  = " · ".join(f"{p['id']}: —" for p in pbs_list) or "—"

        return [
            {
                "id":     "prox_nodes",
                "label":  "Nodes online",
                "value":  "—",
                "detail": inst_detail,
                "color":  "#00d4ff",
            },
            {
                "id":    "prox_cpu",
                "label": "CPU global",
                "value": "—",
                "unit":  "%",
            },
            {
                "id":    "prox_ram",
                "label": "RAM utilisée",
                "value": "—",
            },
            {
                "id":     "prox_pbs",
                "label":  "PBS",
                "value":  f"{len(pbs_list)}/{len(pbs_list)}" if pbs_list else "—",
                "detail": pbs_detail,
                "color":  "#f59e0b",
            },
            {
                "id":    "prox_backups",
                "label": "Backups 24h",
                "value": "—",
            },
        ]
