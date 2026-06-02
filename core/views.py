"""
core/views.py — Modèle des modules disponibles et helpers profils/univers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModuleDef:
    id: str
    label: str
    icon: str
    category: str           # core | maison | societe | transversal | tools
    requires_module: Optional[str] = None  # feature flag config.py


# Catalogue statique — source de vérité des modules disponibles
ALL_MODULES: list[ModuleDef] = [
    ModuleDef("dashboard",      "Tableau de bord",  "Layout_white",      "core"),
    ModuleDef("chat",           "Discussion",        "Chat_white",        "core"),
    ModuleDef("planner",        "Planificateur",     "Calendar_white",    "transversal"),
    ModuleDef("briefing",       "Briefing",          "PencilInk_white",   "transversal"),
    ModuleDef("home",           "Domotique",         "Home_white",        "maison"),
    ModuleDef("cameras",        "Caméras",           "Camera_white",      "maison"),
    ModuleDef("senses",         "Capteurs",          "IOT_white",         "maison"),
    ModuleDef("music",          "Musique",           "Music_white",       "maison",  "music"),
    ModuleDef("infrastructure", "Infrastructure",    "Tiles_white",       "societe"),
    ModuleDef("societe",        "Sociétés",          "Globe_white",       "societe",   "societe"),
    ModuleDef("marketing",      "Marketing",         "PencilInk_white",   "societe"),
    ModuleDef("webagent",       "Agent Web",         "Globe_white",       "tools"),
    ModuleDef("cad",            "Agent CAD",         "Code_white",        "tools"),
    ModuleDef("printers",       "Imprimantes",       "IOT_white",         "tools"),
    ModuleDef("skills",         "Compétences",       "Setting_white",     "tools"),
    ModuleDef("memory",         "Mémoire",           "History_white",     "tools"),
    ModuleDef("library",        "Bibliothèque",      "LibraryFill_white", "tools"),
    ModuleDef("settings",       "Paramètres",        "Setting_white",     "tools"),
]

MODULE_BY_ID: dict[str, ModuleDef] = {m.id: m for m in ALL_MODULES}


def available_modules(enabled_flags: dict[str, bool]) -> list[ModuleDef]:
    """Filtre les modules selon les feature flags actifs (config.MODULES_ENABLED)."""
    return [
        m for m in ALL_MODULES
        if m.requires_module is None or enabled_flags.get(m.requires_module, False)
    ]
