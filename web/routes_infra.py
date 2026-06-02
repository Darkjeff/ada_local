"""
web/routes_infra.py — Routes REST pour l'infrastructure Proxmox/PBS.

Endpoints :
  GET  /api/proxmox/instances        → liste des instances PVE configurées
  GET  /api/proxmox/test             → tester la connexion à une instance PVE
  GET  /api/proxmox/kpis             → KPIs live multi-instance (nodes online, CPU, RAM)
  GET  /api/proxmox/backup-list      → liste des backups (local ou PBS)
  GET  /api/pbs/instances            → liste des instances PBS configurées
  GET  /api/pbs/status               → état live d'un ou plusieurs PBS
  GET  /api/pbs/test                 → tester la connexion à une instance PBS
  GET  /api/proxmox/profiles         → liste des profils de backup
  POST /api/proxmox/instances        → créer/mettre à jour une instance PVE
  POST /api/pbs/instances            → créer/mettre à jour une instance PBS
  POST /api/proxmox/profiles         → créer/mettre à jour un profil de backup

MODULE_SOCIETE: branché sans guard — retourne liste vide si aucune instance configurée.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.infra import proxmox_config as _cfg

logger = logging.getLogger(__name__)

router = APIRouter(tags=["infra"])


# ── Schémas ───────────────────────────────────────────────────────────────────

class InstanceBody(BaseModel):
    id:           str
    label:        str
    host:         str
    port:         int   = 8006
    user:         str   = "root@pam"
    token_name:   str   = "ada"
    token_value:  str   = ""
    verify_ssl:   bool  = False
    enabled:      bool  = True
    universe:     str   = ""
    company_id:   str | None = None
    tags:         list[str]  = []
    pbs_id:       str | None = None


class PBSBody(BaseModel):
    id:           str
    label:        str
    host:         str
    port:         int   = 8007
    user:         str   = "root@pam"
    token_name:   str   = "ada"
    token_value:  str   = ""
    verify_ssl:   bool  = False
    enabled:      bool  = True
    universe:     str   = ""
    company_id:   str | None = None
    tags:         list[str]  = []


class ProfileBody(BaseModel):
    id:        str
    label:     str
    storage:   str
    compress:  str  = "zstd"
    mode:      str  = "snapshot"
    retention: dict = {}
    schedule:  str  = ""
    universe:  str  = ""
    tags:      list[str] = []


# ── Instances PVE ─────────────────────────────────────────────────────────────

@router.get("/api/proxmox/instances")
async def list_pve_instances():
    """Liste toutes les instances PVE (avec token_value masqué)."""
    result = []
    for inst in _cfg.PROXMOX_INSTANCES:
        safe = dict(inst)
        safe["token_value"] = "***" if safe.get("token_value") else ""
        result.append(safe)
    return result


@router.post("/api/proxmox/instances")
async def upsert_pve_instance(body: InstanceBody):
    """Crée ou met à jour une instance PVE (persisté sur disque)."""
    data = body.model_dump()
    existing = next((i for i in _cfg.PROXMOX_INSTANCES if i["id"] == data["id"]), None)
    if existing:
        existing.update(data)
        _cfg.save_pve()
        return {"ok": True, "action": "updated", "id": data["id"]}
    _cfg.PROXMOX_INSTANCES.append(data)
    _cfg.save_pve()
    return {"ok": True, "action": "created", "id": data["id"]}


@router.delete("/api/proxmox/instances/{instance_id}")
async def delete_pve_instance(instance_id: str):
    """Supprime définitivement une instance PVE (persisté sur disque)."""
    before = len(_cfg.PROXMOX_INSTANCES)
    _cfg.PROXMOX_INSTANCES[:] = [i for i in _cfg.PROXMOX_INSTANCES if i["id"] != instance_id]
    if len(_cfg.PROXMOX_INSTANCES) == before:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' introuvable")
    _cfg.save_pve()
    return {"ok": True, "deleted": instance_id}


@router.get("/api/proxmox/test")
async def test_pve_connection(instance_id: str = Query(..., description="ID de l'instance PVE")):
    """
    Teste la connexion à une instance PVE.
    Retourne version + nb de nodes ou une erreur lisible.
    """
    inst = _cfg.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' introuvable")
    try:
        from core.infra.proxmox_client import ProxmoxClient
        client = ProxmoxClient(inst)
        info = await client.version()
        return {"ok": True, **info}
    except Exception as exc:
        logger.warning("[routes_infra] test_pve %s: %s", instance_id, exc)
        return {"ok": False, "error": str(exc), "instance_id": instance_id}


@router.get("/api/proxmox/kpis")
async def pve_kpis(instance_id: str | None = Query(None)):
    """
    KPIs live : pour chaque instance activée (ou celle spécifiée),
    retourne nodes online, CPU moyen, RAM utilisée.
    """
    instances = (
        [_cfg.get_instance(instance_id)] if instance_id else _cfg.enabled_instances()
    )
    instances = [i for i in instances if i]
    result = []
    for inst in instances:
        try:
            from core.infra.proxmox_client import ProxmoxClient
            client = ProxmoxClient(inst)
            nodes = await client.list_nodes()
            online = sum(1 for n in nodes if n.get("status") == "online")
            total  = len(nodes)
            avg_cpu = round(
                sum(n.get("cpu", 0) for n in nodes) / total * 100, 1
            ) if total else 0
            total_mem   = sum(n.get("maxmem", 0) for n in nodes)
            used_mem    = sum(n.get("mem",    0) for n in nodes)
            result.append({
                "instance_id": inst["id"],
                "label":       inst["label"],
                "nodes_online": online,
                "nodes_total":  total,
                "cpu_pct":      avg_cpu,
                "mem_used_gb":  round(used_mem    / 1_073_741_824, 1),
                "mem_total_gb": round(total_mem   / 1_073_741_824, 1),
            })
        except Exception as exc:
            logger.warning("[routes_infra] pve_kpis %s: %s", inst["id"], exc)
            result.append({
                "instance_id": inst["id"],
                "label":       inst["label"],
                "error":       str(exc),
            })
    return result


@router.get("/api/proxmox/backup-list")
async def pve_backup_list(
    instance_id: str | None = Query(None),
    vmid:        int | None = Query(None),
    storage:     str        = Query("local"),
):
    """Liste les backups locaux sur un ou plusieurs PVE."""
    instances = (
        [_cfg.get_instance(instance_id)] if instance_id else _cfg.enabled_instances()
    )
    instances = [i for i in instances if i]
    result = []
    for inst in instances:
        try:
            from core.infra.proxmox_client import ProxmoxClient
            client = ProxmoxClient(inst)
            backups = await client.backup_list(vmid=vmid, storage=storage)
            for b in backups:
                b["instance_id"] = inst["id"]
            result.extend(backups)
        except Exception as exc:
            logger.warning("[routes_infra] backup_list %s: %s", inst["id"], exc)
    return result


# ── Instances PBS ─────────────────────────────────────────────────────────────

@router.get("/api/pbs/instances")
async def list_pbs_instances():
    """Liste toutes les instances PBS (token masqué)."""
    result = []
    for pbs in _cfg.PBS_INSTANCES:
        safe = dict(pbs)
        safe["token_value"] = "***" if safe.get("token_value") else ""
        result.append(safe)
    return result


@router.post("/api/pbs/instances")
async def upsert_pbs_instance(body: PBSBody):
    """Crée ou met à jour une instance PBS (persisté sur disque)."""
    data = body.model_dump()
    existing = next((p for p in _cfg.PBS_INSTANCES if p["id"] == data["id"]), None)
    if existing:
        existing.update(data)
        _cfg.save_pbs()
        return {"ok": True, "action": "updated", "id": data["id"]}
    data["datastores"] = []
    _cfg.PBS_INSTANCES.append(data)
    _cfg.save_pbs()
    return {"ok": True, "action": "created", "id": data["id"]}


@router.delete("/api/pbs/instances/{pbs_id}")
async def delete_pbs_instance(pbs_id: str):
    """Supprime définitivement une instance PBS (persisté sur disque)."""
    before = len(_cfg.PBS_INSTANCES)
    _cfg.PBS_INSTANCES[:] = [p for p in _cfg.PBS_INSTANCES if p["id"] != pbs_id]
    if len(_cfg.PBS_INSTANCES) == before:
        raise HTTPException(status_code=404, detail=f"PBS '{pbs_id}' introuvable")
    _cfg.save_pbs()
    return {"ok": True, "deleted": pbs_id}


@router.get("/api/pbs/test")
async def test_pbs_connection(pbs_id: str = Query(..., description="ID de l'instance PBS")):
    """Teste la connexion à un PBS. Retourne version + nb datastores."""
    pbs = _cfg.get_pbs(pbs_id)
    if not pbs:
        raise HTTPException(status_code=404, detail=f"PBS '{pbs_id}' introuvable")
    try:
        from core.infra.pbs_client import PBSClient
        client = PBSClient(pbs)
        info = await client.version()
        datastores = await client.list_datastores()
        return {"ok": True, **info, "datastores": len(datastores)}
    except Exception as exc:
        logger.warning("[routes_infra] test_pbs %s: %s", pbs_id, exc)
        return {"ok": False, "error": str(exc), "pbs_id": pbs_id}


@router.get("/api/pbs/status")
async def pbs_status(pbs_id: str | None = Query(None)):
    """
    État live d'un ou plusieurs PBS :
    datastores, espace libre total, espace utilisé.
    """
    pbs_list = (
        [_cfg.get_pbs(pbs_id)] if pbs_id else _cfg.enabled_pbs()
    )
    pbs_list = [p for p in pbs_list if p]
    result = []
    for pbs in pbs_list:
        try:
            from core.infra.pbs_client import PBSClient
            client = PBSClient(pbs)
            status = await client.status()
            result.append(status)
        except Exception as exc:
            logger.warning("[routes_infra] pbs_status %s: %s", pbs["id"], exc)
            result.append({"pbs_id": pbs["id"], "error": str(exc)})
    return result


@router.get("/api/pbs/snapshots")
async def pbs_snapshots(
    pbs_id:      str        = Query(..., description="ID de l'instance PBS"),
    store:       str        = Query(..., description="Nom du datastore"),
    backup_type: str | None = Query(None, description="Filtre type : vm | ct | host"),
    backup_id:   str | None = Query(None, description="Filtre backup-id (ex: '100')"),
):
    """Liste les snapshots d'un datastore PBS, avec filtres optionnels."""
    pbs = _cfg.get_pbs(pbs_id)
    if not pbs:
        raise HTTPException(status_code=404, detail=f"PBS '{pbs_id}' introuvable")
    try:
        from core.infra.pbs_client import PBSClient
        client = PBSClient(pbs)
        snaps = await client.list_snapshots(
            datastore=store,
            backup_type=backup_type,
            backup_id=backup_id,
        )
        return {"pbs_id": pbs_id, "store": store, "count": len(snaps), "snapshots": snaps}
    except Exception as exc:
        logger.warning("[routes_infra] pbs_snapshots %s/%s: %s", pbs_id, store, exc)
        return {"pbs_id": pbs_id, "store": store, "error": str(exc)}


@router.get("/api/pbs/tasks")
async def pbs_tasks(
    pbs_id:      str  = Query(..., description="ID de l'instance PBS"),
    limit:       int  = Query(50, ge=1, le=500),
    errors_only: bool = Query(False, description="Ne retourner que les tâches en erreur"),
):
    """Tâches récentes du nœud PBS (via /nodes/localhost/tasks)."""
    pbs = _cfg.get_pbs(pbs_id)
    if not pbs:
        raise HTTPException(status_code=404, detail=f"PBS '{pbs_id}' introuvable")
    try:
        from core.infra.pbs_client import PBSClient
        client = PBSClient(pbs)
        tasks = await client.get_tasks(limit=limit, errors_only=errors_only)
        return {"pbs_id": pbs_id, "count": len(tasks), "tasks": tasks}
    except Exception as exc:
        logger.warning("[routes_infra] pbs_tasks %s: %s", pbs_id, exc)
        return {"pbs_id": pbs_id, "error": str(exc)}


# ── Profils de backup ─────────────────────────────────────────────────────────

@router.get("/api/proxmox/profiles")
async def list_profiles(universe: str | None = Query(None)):
    """Liste les profils de backup, optionnellement filtrés par univers."""
    profiles = _cfg.PROXMOX_BACKUP_PROFILES
    if universe:
        profiles = [p for p in profiles if p.get("universe") == universe]
    return profiles


@router.post("/api/proxmox/profiles")
async def upsert_profile(body: ProfileBody):
    """Crée ou met à jour un profil de backup (persisté sur disque)."""
    data = body.model_dump()
    existing = next((p for p in _cfg.PROXMOX_BACKUP_PROFILES if p["id"] == data["id"]), None)
    if existing:
        existing.update(data)
        _cfg.save_profiles()
        return {"ok": True, "action": "updated", "id": data["id"]}
    _cfg.PROXMOX_BACKUP_PROFILES.append(data)
    _cfg.save_profiles()
    return {"ok": True, "action": "created", "id": data["id"]}


@router.delete("/api/proxmox/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """Supprime définitivement un profil de backup (persisté sur disque)."""
    before = len(_cfg.PROXMOX_BACKUP_PROFILES)
    _cfg.PROXMOX_BACKUP_PROFILES[:] = [p for p in _cfg.PROXMOX_BACKUP_PROFILES if p["id"] != profile_id]
    if len(_cfg.PROXMOX_BACKUP_PROFILES) == before:
        raise HTTPException(status_code=404, detail=f"Profil '{profile_id}' introuvable")
    _cfg.save_profiles()
    return {"ok": True, "deleted": profile_id}
