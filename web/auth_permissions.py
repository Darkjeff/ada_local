"""
ADA Auth — groupes de permissions.

Chaque groupe donne accès à un sous-ensemble de menu_tags.
Les groupes sont additifs : un utilisateur peut avoir plusieurs groupes.
"""
from __future__ import annotations

# Tous les tags de menus disponibles dans l'application
ALL_MENU_TAGS: list[str] = [
    "dashboard",
    "chat",
    "planner",
    "briefing",
    "home",          # data-page="home"  (Domotique)
    "cameras",       # data-view="cameras"
    "senses",        # data-page="senses"
    "cad",           # data-page="cad"
    "printers",      # data-page="printers"
    "webagent",      # data-view="webagent"
    "skills",        # data-page="skills"
    "memory",        # data-view="memory"
    "music",         # data-page="music"
    "library",       # data-page="library"
    "marketing",     # data-view="marketing"
    "infrastructure",# data-page="infrastructure"
    "settings",      # data-view="settings"
    "profile-editor",# data-view="profile-editor" (admin only)
    # MODULE_SOCIETE
    "societe",       # data-view="societe"
]

# Définition des groupes prédéfinis
PERMISSION_GROUPS: dict[str, list[str]] = {
    "admin": ALL_MENU_TAGS,
    "assistant": [
        "dashboard", "chat", "planner", "briefing",
        "webagent", "memory", "skills",
    ],
    "domotique": [
        "dashboard", "home", "cameras", "senses",
    ],
    "print3d": [
        "dashboard", "cad", "printers",
    ],
    "media": [
        "dashboard", "music", "library", "marketing",
    ],
    "tools": [
        "dashboard", "skills", "memory", "infrastructure", "settings",
    ],
}

# Description humaine des groupes
GROUP_DESCRIPTIONS: dict[str, str] = {
    "admin":      "Accès complet à toutes les fonctionnalités",
    "assistant":  "Chat, planificateur, briefing, agent web, mémoire",
    "domotique":  "Domotique, caméras, capteurs",
    "print3d":    "Agent CAD, imprimantes 3D",
    "media":      "Musique, bibliothèque, marketing",
    "tools":      "Compétences, mémoire, infrastructure, paramètres",
}


def groups_to_tags(groups: list[str]) -> list[str]:
    """Retourne l'union des tags accessibles pour une liste de groupes."""
    tags: set[str] = set()
    for g in groups:
        tags.update(PERMISSION_GROUPS.get(g, []))
    return sorted(tags)


def can_access_tag(groups: list[str], tag: str) -> bool:
    return tag in groups_to_tags(groups)
