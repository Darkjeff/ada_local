"""
core/infra/proxmox_config.py — Configuration multi-instance Proxmox + PBS + profils de backup.

Ce fichier est la source de vérité pour les instances PVE/PBS.
Les données sont persistées dans config/proxmox_instances.json, config/pbs_instances.json
et config/proxmox_profiles.json. Si ces fichiers n'existent pas, les exemples ci-dessous
sont utilisés comme point de départ mais NE SONT PAS sauvegardés automatiquement.

MODULE_SOCIETE: structure identique — affectation univers/société/tag sur chaque instance.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONF_DIR = Path(__file__).resolve().parents[2] / "config"
_PVE_FILE      = _CONF_DIR / "proxmox_instances.json"
_PBS_FILE      = _CONF_DIR / "pbs_instances.json"
_PROFILES_FILE = _CONF_DIR / "proxmox_profiles.json"


def _load_json(path: Path, default: list) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[proxmox_config] Impossible de lire %s : %s", path, e)
    return [dict(d) for d in default]


def _save_json(path: Path, data: list) -> None:
    try:
        _CONF_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error("[proxmox_config] Impossible d'écrire %s : %s", path, e)


# ── Données par défaut (exemples) ─────────────────────────────────────────────
# Utilisées uniquement si aucun fichier de config n'existe.

# ── Instances Proxmox VE ──────────────────────────────────────────────────────

_DEFAULT_PVE: list[dict] = [
    {
        "id":           "pve-opent",
        "label":        "Proxmox OpenTechno",
        "host":         "192.168.1.10",
        "port":         8006,
        "user":         "root@pam",
        "token_name":   "ada",
        "token_value":  "",
        "verify_ssl":   False,
        "enabled":      False,
        "universe":     "opent",
        "company_id":   "opentechno",
        "tags":         ["infra", "production"],
        "pbs_id":       "pbs-opent",
    },
    {
        "id":           "pve-home",
        "label":        "Proxmox Maison",
        "host":         "192.168.1.20",
        "port":         8006,
        "user":         "root@pam",
        "token_name":   "ada",
        "token_value":  "",
        "verify_ssl":   False,
        "enabled":      False,
        "universe":     "home",
        "company_id":   None,
        "tags":         ["homelab"],
        "pbs_id":       None,
    },
]

_DEFAULT_PBS: list[dict] = [
    {
        "id":           "pbs-opent",
        "label":        "PBS OpenTechno",
        "host":         "192.168.1.11",
        "port":         8007,
        "user":         "root@pam",
        "token_name":   "ada",
        "token_value":  "",
        "verify_ssl":   False,
        "enabled":      False,
        "universe":     "opent",
        "company_id":   "opentechno",
        "tags":         ["backup", "production"],
        "datastores":   [],
    },
]

_DEFAULT_PROFILES: list[dict] = [
    {
        "id":       "nightly-prod",
        "label":    "Nuit — Production",
        "storage":  "pbs-opent",
        "compress": "zstd",
        "mode":     "snapshot",
        "retention": {"keep_last": 3, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3},
        "schedule": "0 2 * * *",
        "universe": "opent",
        "tags":     ["production"],
    },
    {
        "id":       "weekly-homelab",
        "label":    "Hebdo — Homelab",
        "storage":  "local",
        "compress": "zstd",
        "mode":     "snapshot",
        "retention": {"keep_last": 2, "keep_weekly": 2},
        "schedule": "0 3 * * 0",
        "universe": "home",
        "tags":     ["homelab"],
    },
]


# ── Listes actives (chargées depuis le disque ou depuis les exemples) ─────────

PROXMOX_INSTANCES: list[dict]        = _load_json(_PVE_FILE,      _DEFAULT_PVE)
PBS_INSTANCES: list[dict]            = _load_json(_PBS_FILE,      _DEFAULT_PBS)
PROXMOX_BACKUP_PROFILES: list[dict]  = _load_json(_PROFILES_FILE, _DEFAULT_PROFILES)


# ── Helpers de sauvegarde ─────────────────────────────────────────────────────

def save_pve() -> None:
    """Persiste les instances PVE sur le disque."""
    _save_json(_PVE_FILE, PROXMOX_INSTANCES)


def save_pbs() -> None:
    """Persiste les instances PBS sur le disque."""
    _save_json(_PBS_FILE, PBS_INSTANCES)


def save_profiles() -> None:
    """Persiste les profils de backup sur le disque."""
    _save_json(_PROFILES_FILE, PROXMOX_BACKUP_PROFILES)


# ── Helpers de lecture ────────────────────────────────────────────────────────

def get_instance(instance_id: str) -> dict | None:
    """Retourne une instance PVE par son id."""
    return next((i for i in PROXMOX_INSTANCES if i["id"] == instance_id), None)


def get_pbs(pbs_id: str) -> dict | None:
    """Retourne une instance PBS par son id."""
    return next((p for p in PBS_INSTANCES if p["id"] == pbs_id), None)


def get_profile(profile_id: str) -> dict | None:
    """Retourne un profil de backup par son id."""
    return next((p for p in PROXMOX_BACKUP_PROFILES if p["id"] == profile_id), None)


def enabled_instances() -> list[dict]:
    """Retourne toutes les instances PVE activées."""
    return [i for i in PROXMOX_INSTANCES if i["enabled"]]


def enabled_pbs() -> list[dict]:
    """Retourne tous les PBS activés."""
    return [p for p in PBS_INSTANCES if p["enabled"]]
