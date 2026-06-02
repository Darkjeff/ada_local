"""
core/infra/proxmox_client.py — Client HTTP pour l'API REST Proxmox VE.

Utilise httpx (async) + token API Proxmox.
Header : Authorization: PVEAPIToken=user@realm!name=token_value

MODULE_SOCIETE: ignoré si MODULES_ENABLED["proxmox"] = False.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0  # secondes


class ProxmoxClient:
    """
    Client léger pour l'API Proxmox VE REST (v2).
    Instancié par instance PVE ; ne maintient pas de connexion persistante.
    """

    def __init__(self, instance: dict) -> None:
        self._base = f"https://{instance['host']}:{instance['port']}/api2/json"
        self._headers = {
            "Authorization": (
                f"PVEAPIToken={instance['user']}!"
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
            resp.raise_for_status()
            return resp.json().get("data")

    async def _post(self, path: str, data: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(verify=self._verify, timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=self._headers, json=data or {})
            resp.raise_for_status()
            return resp.json().get("data")

    # ── Version / ping ────────────────────────────────────────────────────────

    async def version(self) -> dict:
        """Retourne la version PVE + nb de nodes — utilisé pour tester la connexion."""
        ver = await self._get("/version")
        nodes = await self._get("/nodes")
        return {
            "instance_id": self._instance_id,
            "version":     ver.get("version") if ver else "?",
            "release":     ver.get("release") if ver else "?",
            "nodes":       len(nodes) if nodes else 0,
        }

    # ── Nodes ─────────────────────────────────────────────────────────────────

    async def list_nodes(self) -> list[dict]:
        return await self._get("/nodes") or []

    async def node_stats(self, node: str) -> dict:
        return await self._get(f"/nodes/{node}/status") or {}

    async def node_reboot(self, node: str) -> Any:
        return await self._post(f"/nodes/{node}/status", {"command": "reboot"})

    # ── VMs ───────────────────────────────────────────────────────────────────

    async def list_vms(self, node: str | None = None) -> list[dict]:
        """Retourne les VMs QEMU + les containers LXC (CT) d'un node ou de tous les nodes."""
        if node:
            qemu = await self._get(f"/nodes/{node}/qemu") or []
            for vm in qemu:
                vm["node"] = node
                vm["type"] = "qemu"
            lxc = await self._get(f"/nodes/{node}/lxc") or []
            for ct in lxc:
                ct["node"] = node
                ct["type"] = "lxc"
            return qemu + lxc
        # Tous les nodes
        nodes = await self.list_nodes()
        all_items: list[dict] = []
        for n in nodes:
            node_name = n["node"]
            qemu = await self._get(f"/nodes/{node_name}/qemu") or []
            for vm in qemu:
                vm["node"] = node_name
                vm["type"] = "qemu"
            lxc = await self._get(f"/nodes/{node_name}/lxc") or []
            for ct in lxc:
                ct["node"] = node_name
                ct["type"] = "lxc"
            all_items.extend(qemu)
            all_items.extend(lxc)
        return all_items

    async def vm_power(self, node: str, vmid: int, action: str, vm_type: str = "qemu") -> Any:
        """action: start | stop | reboot | shutdown. vm_type: qemu | lxc"""
        kind = "lxc" if vm_type == "lxc" else "qemu"
        return await self._post(f"/nodes/{node}/{kind}/{vmid}/status/{action}")

    async def vm_snapshot(self, node: str, vmid: int, snapname: str, description: str = "") -> Any:
        return await self._post(f"/nodes/{node}/qemu/{vmid}/snapshot", {
            "snapname":    snapname,
            "description": description,
        })

    async def vm_restore(self, node: str, vmid: int, backup: str,
                         storage: str = "local", force: bool = True) -> Any:
        return await self._post(f"/nodes/{node}/qemu", {
            "vmid":    vmid,
            "archive": backup,
            "storage": storage,
            "force":   1 if force else 0,
        })

    # ── Backup vzdump ─────────────────────────────────────────────────────────

    async def vm_backup(self, node: str, vmid: int, storage: str = "local",
                        compress: str = "zstd", mode: str = "snapshot") -> Any:
        return await self._post(f"/nodes/{node}/vzdump", {
            "vmid":     vmid,
            "storage":  storage,
            "compress": compress,
            "mode":     mode,
        })

    async def backup_list(self, node: str | None = None, vmid: int | None = None,
                          storage: str = "local") -> list[dict]:
        """Liste les backups disponibles sur un storage local."""
        results: list[dict] = []
        nodes = [{"node": node}] if node else await self.list_nodes()
        for n in nodes:
            node_name = n["node"]
            try:
                items = await self._get(f"/nodes/{node_name}/storage/{storage}/content",
                                        params={"content": "backup"}) or []
                for item in items:
                    if vmid is None or item.get("vmid") == vmid:
                        item["node"] = node_name
                        results.append(item)
            except Exception as exc:
                logger.warning("[proxmox_client] backup_list %s/%s: %s", node_name, storage, exc)
        return results

    # ── Storage ───────────────────────────────────────────────────────────────

    async def storage_status(self, node: str | None = None, storage: str | None = None) -> list[dict]:
        results: list[dict] = []
        nodes = [{"node": node}] if node else await self.list_nodes()
        for n in nodes:
            node_name = n["node"]
            try:
                path = f"/nodes/{node_name}/storage"
                if storage:
                    path += f"/{storage}/status"
                    data = await self._get(path)
                    if data:
                        data["node"] = node_name
                        results.append(data)
                else:
                    items = await self._get(path) or []
                    for item in items:
                        item["node"] = node_name
                    results.extend(items)
            except Exception as exc:
                logger.warning("[proxmox_client] storage_status %s: %s", node_name, exc)
        return results
