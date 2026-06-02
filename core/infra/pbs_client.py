"""
core/infra/pbs_client.py — Client HTTP pour l'API REST Proxmox Backup Server.

API PBS : https://pbs.proxmox.com/docs/api-viewer/
Auth    : Authorization: PBSAPIToken=user@realm!tokenid=secret
  ⚠  Format strict : PBSAPIToken= (pas PVEAPIToken=)
  ⚠  Realm doit correspondre à l'user PBS (pam ou pbs)

MODULE_SOCIETE: ignoré si MODULES_ENABLED["proxmox"] = False.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0


# ── Exceptions PBS ────────────────────────────────────────────────────────────

class PBSError(Exception):
    """Erreur PBS générique."""


class PBSAuthError(PBSError):
    """401 — Token invalide, realm incorrect ou user inexistant."""


class PBSPermissionError(PBSError):
    """403 — Privilège insuffisant sur le datastore."""


class PBSNotFoundError(PBSError):
    """404 — Datastore ou ressource introuvable."""


class PBSServerError(PBSError):
    """500 — Erreur interne PBS."""


def _raise_for_pbs(resp: httpx.Response) -> None:
    """Lève l'exception PBS appropriée selon le code HTTP.
    Logue systématiquement le header x-proxmox-error si présent.
    """
    if resp.is_success:
        return
    detail = resp.headers.get("x-proxmox-error") or resp.text[:200]
    logger.warning("[pbs_client] HTTP %s — x-proxmox-error: %s", resp.status_code, detail)
    if resp.status_code == 401:
        raise PBSAuthError(
            f"Token invalide ou realm incorrect — vérifier PBSAPIToken= et realm (pam/pbs). Détail: {detail}"
        )
    if resp.status_code == 403:
        raise PBSPermissionError(f"Privilège insuffisant sur le datastore. Détail: {detail}")
    if resp.status_code == 404:
        raise PBSNotFoundError(f"Datastore ou ressource introuvable. Détail: {detail}")
    if resp.status_code >= 500:
        raise PBSServerError(f"Erreur interne PBS ({resp.status_code}). Détail: {detail}")
    resp.raise_for_status()


class PBSClient:
    """
    Client léger pour l'API Proxmox Backup Server REST.
    Instancié par instance PBS.

    Auth header : PBSAPIToken=<user>@<realm>!<token_name>=<token_value>
    ⚠  Distinct de PVE — le préfixe est PBSAPIToken=, pas PVEAPIToken=
    """

    def __init__(self, instance: dict) -> None:
        host = instance["host"].rstrip("/")
        # Accepte host avec ou sans schéma (ex: "192.168.1.11" ou "https://...")
        if not host.startswith("http"):
            host = f"https://{host}"
        self._base = f"{host}:{instance['port']}/api2/json"
        self._headers = {
            "Authorization": (
                f"PBSAPIToken={instance['user']}!"
                f"{instance['token_name']}={instance['token_value']}"
            ),
        }
        self._verify = instance.get("verify_ssl", False)
        self._instance_id = instance["id"]

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(verify=self._verify, timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=self._headers, params=params or {})
            _raise_for_pbs(resp)
            return resp.json().get("data")

    async def _post(self, path: str, data: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(verify=self._verify, timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=self._headers, json=data or {})
            _raise_for_pbs(resp)
            return resp.json().get("data")

    # ── Version / ping ────────────────────────────────────────────────────────

    async def version(self) -> dict:
        """Teste la connexion et retourne la version PBS."""
        ver = await self._get("/version")
        return {
            "instance_id": self._instance_id,
            "version":     ver.get("version") if ver else "?",
            "release":     ver.get("release") if ver else "?",
        }

    # ── Datastores ────────────────────────────────────────────────────────────

    async def list_datastores(self) -> list[dict]:
        """Liste les datastores PBS avec leur espace disque."""
        return await self._get("/admin/datastore") or []

    async def datastore_status(self, datastore: str) -> dict:
        return await self._get(f"/admin/datastore/{datastore}") or {}

    # Alias spec (get_datastore_status)
    async def get_datastore_status(self, store: str) -> dict:
        """Alias spec — usage disque, nombre de snapshots, dernier GC."""
        return await self.datastore_status(store)

    # ── Snapshots / backups ───────────────────────────────────────────────────

    async def list_snapshots(
        self,
        datastore: str,
        backup_type: str | None = None,
        backup_id: str | None = None,
        vmid: int | None = None,
    ) -> list[dict]:
        """
        Liste les snapshots dans un datastore.
        Filtres : backup_type (vm/ct/host), backup_id (ex: "vm/100"),
                  ou vmid (converti en backup-id automatiquement).
        """
        params: dict = {}
        if backup_type:
            params["backup-type"] = backup_type
        if backup_id:
            params["backup-id"] = backup_id
        elif vmid is not None:
            params["backup-id"] = str(vmid)
        return await self._get(f"/admin/datastore/{datastore}/snapshots", params=params) or []

    async def list_all_backups(self, vmid: int | None = None) -> list[dict]:
        """Liste les backups dans tous les datastores PBS."""
        datastores = await self.list_datastores()
        all_backups: list[dict] = []
        for ds in datastores:
            ds_name = ds.get("name") or ds.get("store")
            if not ds_name:
                continue
            try:
                snaps = await self.list_snapshots(ds_name, vmid=vmid)
                for snap in snaps:
                    snap["datastore"] = ds_name
                    snap["pbs_id"] = self._instance_id
                all_backups.extend(snaps)
            except Exception as exc:
                logger.warning("[pbs_client] list_snapshots %s: %s", ds_name, exc)
        return all_backups

    # ── Jobs de backup ────────────────────────────────────────────────────────

    async def list_backup_jobs(self) -> list[dict]:
        """Liste les jobs de backup PBS configurés."""
        return await self._get("/config/backup") or []

    async def get_tasks(self, limit: int = 50, errors_only: bool = False) -> list[dict]:
        """
        Tâches récentes sur le nœud PBS localhost.
        errors_only=True → ne retourne que les tâches avec status != "OK".
        """
        params: dict = {"limit": limit}
        tasks = await self._get("/nodes/localhost/tasks", params=params) or []
        if errors_only:
            tasks = [
                t for t in tasks
                if t.get("status") and t["status"] not in ("OK", "ok", "")
            ]
        return tasks

    async def get_task_log(self, upid: str) -> list[str]:
        """Retourne les logs d'une tâche PBS (UPID)."""
        data = await self._get(f"/nodes/localhost/tasks/{upid}/log")
        if isinstance(data, list):
            return [line.get("t", "") for line in data]
        return []

    # ── Espace disque ─────────────────────────────────────────────────────────

    async def status(self) -> dict:
        """
        Retourne un résumé de l'état PBS :
        datastores, espace libre total, jobs actifs.
        """
        datastores = await self.list_datastores()
        total_avail = sum(ds.get("avail", 0) for ds in datastores)
        total_used  = sum(ds.get("used",  0) for ds in datastores)
        return {
            "pbs_id":      self._instance_id,
            "datastores":  len(datastores),
            "avail_bytes": total_avail,
            "used_bytes":  total_used,
            "detail":      [
                {
                    "name":      ds.get("name") or ds.get("store"),
                    "avail_gb":  round(ds.get("avail", 0) / 1_073_741_824, 1),
                    "used_gb":   round(ds.get("used",  0) / 1_073_741_824, 1),
                }
                for ds in datastores
            ],
        }
