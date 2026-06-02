"""
core/documents/documents_mount.py
Vérification du point de montage NVMe (Linux + Windows).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_mount_status(
    root_path: str,
    expected_mount_path: str = "",
    expected_device_hint: str = "",
) -> dict:
    """
    Retourne l'état du dossier documentaire.

    {
        "ok": bool,
        "root_path": str,
        "exists": bool,
        "is_dir": bool,
        "is_mount": bool | None,
        "device": str | None,
        "filesystem": str | None,
        "reason": str
    }
    """
    result: dict = {
        "ok": False,
        "root_path": root_path,
        "exists": False,
        "is_dir": False,
        "is_mount": None,
        "device": None,
        "filesystem": None,
        "reason": "",
    }

    if not root_path:
        result["reason"] = "root_path non configuré"
        return result

    p = Path(root_path)
    result["exists"] = p.exists()
    result["is_dir"] = p.is_dir()

    if not p.exists():
        result["reason"] = f"Le dossier n'existe pas : {root_path}"
        return result

    if not p.is_dir():
        result["reason"] = f"root_path n'est pas un dossier : {root_path}"
        return result

    # ── Linux ──────────────────────────────────────────────────────────────
    if sys.platform.startswith("linux"):
        mounts = _read_proc_mounts()
        mount_point, device, fs = _find_mount_for_path(str(p), mounts)
        result["is_mount"] = mount_point != "/"
        result["device"] = device
        result["filesystem"] = fs

        if expected_mount_path:
            ep = Path(expected_mount_path)
            # Le mount_point trouvé doit être égal ou parent du expected_mount_path
            if not (Path(mount_point) == ep or ep == p or str(p).startswith(str(ep))):
                result["reason"] = (
                    f"Le point de montage attendu '{expected_mount_path}' "
                    f"ne correspond pas au montage détecté '{mount_point}'"
                )
                return result

        if expected_device_hint:
            hint_lower = expected_device_hint.lower()
            combo = f"{device} {mount_point} {fs}".lower()
            if hint_lower not in combo:
                result["reason"] = (
                    f"device_hint '{expected_device_hint}' introuvable dans "
                    f"'{device} {mount_point} {fs}'"
                )
                return result

        result["ok"] = True
        result["reason"] = "OK"
        return result

    # ── Windows ────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        drive = Path(root_path).drive  # ex: "D:"
        result["is_mount"] = True if drive else None

        if expected_mount_path:
            exp_drive = Path(expected_mount_path).drive.upper()
            cur_drive = drive.upper()
            if cur_drive != exp_drive:
                result["reason"] = (
                    f"Lecteur attendu '{exp_drive}', trouvé '{cur_drive}'"
                )
                return result

        if expected_device_hint:
            try:
                import psutil  # type: ignore
                parts = psutil.disk_partitions()
                found = any(
                    expected_device_hint.lower() in (
                        p.device + p.fstype + p.mountpoint
                    ).lower()
                    for p in parts
                    if p.mountpoint.upper().startswith(drive.upper())
                )
                if not found:
                    result["reason"] = (
                        f"device_hint '{expected_device_hint}' non trouvé sur '{drive}'"
                    )
                    return result
                for part in parts:
                    if part.mountpoint.upper().startswith(drive.upper()):
                        result["device"] = part.device
                        result["filesystem"] = part.fstype
            except ImportError:
                pass  # psutil non installé → best-effort

        result["ok"] = True
        result["reason"] = "OK"
        return result

    # ── Autre OS ─────────────────────────────────────────────────────────
    result["ok"] = p.exists() and p.is_dir()
    result["reason"] = "OK" if result["ok"] else "Dossier inaccessible"
    return result


# ── Helpers Linux ──────────────────────────────────────────────────────────

def _read_proc_mounts() -> list[tuple[str, str, str]]:
    """Lit /proc/mounts → [(mountpoint, device, fstype), ...]"""
    entries: list[tuple[str, str, str]] = []
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    device, mountpoint, fstype = parts[0], parts[1], parts[2]
                    entries.append((mountpoint, device, fstype))
    except Exception:
        pass
    return entries


def _find_mount_for_path(
    path: str,
    mounts: list[tuple[str, str, str]],
) -> tuple[str, str, str]:
    """Trouve le point de montage le plus précis couvrant path."""
    path = os.path.realpath(path)
    best_mp = "/"
    best_dev = ""
    best_fs = ""
    best_len = 0
    for mp, dev, fs in mounts:
        if path.startswith(mp) and len(mp) > best_len:
            best_mp = mp
            best_dev = dev
            best_fs = fs
            best_len = len(mp)
    return best_mp, best_dev, best_fs
