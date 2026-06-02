# ADA — Spécification : Profils d'affichage & Univers configurables

**Branche cible :** `integration-n8n`
**Repo :** `oscim/ada_local`
**Date :** 2026-05-31
**Statut :** À implémenter

---

## 1. Contexte & objectif

ADA est un assistant local (FastAPI + frontend SPA) accessible depuis plusieurs appareils
authentifiés via UUID device (JWT + QR code). Chaque appareil dispose d'un token JWT
contenant `device_id`, `user_id` et `groups`.

**Objectif :** permettre à chaque device d'afficher une interface adaptée à son usage
(mobile synthétique, bureau pro, poste maison) en définissant :

- Des **univers** — regroupements nommés de modules (vues)
- Des **profils d'affichage** — assignés par device, choisissent quels univers afficher,
  lequel est actif par défaut, et le thème visuel

La config est **stockée côté serveur** (SQLite `data/auth.db`), servie au client au
chargement via `/api/profile`, et **appliquée dynamiquement** par le frontend SPA.

---

## 2. Structure à créer

```
core/
  views.py              ← modèle de données : modules disponibles
  routes/               ← NOUVEAU dossier
    __init__.py
    profiles.py         ← CRUD profils + univers (/api/profiles/*)
    devices.py          ← extension devices existants (assign profile)

web/
  router_profiles.py    ← router FastAPI branché dans server.py
  static/
    views/
      profile-editor/   ← UI de configuration des profils (admin)
        index.js
        style.css
```

---

## 3. Modèle de données

### 3.1 Tables SQLite à ajouter dans `data/auth.db`

Fichier à modifier : **`web/auth_db.py`**

```sql
-- Bibliothèque des modules disponibles (statique, seed au démarrage)
CREATE TABLE IF NOT EXISTS modules (
    id          TEXT PRIMARY KEY,   -- ex: "dashboard", "chat", "home", "cameras"…
    label       TEXT NOT NULL,      -- ex: "Tableau de bord"
    icon        TEXT NOT NULL,      -- nom de fichier SVG sans extension, ex: "Layout_white"
    category    TEXT NOT NULL,      -- "core" | "maison" | "societe" | "transversal" | "tools"
    requires_module TEXT            -- feature flag config.py, ex: "societe" (nullable)
);

-- Univers : groupes de modules définis par l'admin
CREATE TABLE IF NOT EXISTS universes (
    id          TEXT PRIMARY KEY,   -- uuid4
    name        TEXT NOT NULL,      -- ex: "Maison", "OpenTechno", "Mobile"
    icon        TEXT NOT NULL DEFAULT '◈',
    color       TEXT NOT NULL DEFAULT '#00c8f0',
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);

-- Modules assignés à un univers (table de liaison ordonnée)
CREATE TABLE IF NOT EXISTS universe_modules (
    universe_id TEXT NOT NULL,
    module_id   TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (universe_id, module_id),
    FOREIGN KEY (universe_id) REFERENCES universes(id) ON DELETE CASCADE
);

-- Profils d'affichage
CREATE TABLE IF NOT EXISTS display_profiles (
    id              TEXT PRIMARY KEY,   -- uuid4
    name            TEXT NOT NULL,      -- ex: "Mobile", "Bureau Pro", "Maison"
    theme           TEXT NOT NULL DEFAULT 'dark',  -- dark|light|midnight|graphite
    density         TEXT NOT NULL DEFAULT 'normal', -- compact|normal|comfortable
    default_universe_id TEXT,           -- univers affiché au démarrage (nullable → dashboard)
    created_at      REAL NOT NULL,
    FOREIGN KEY (default_universe_id) REFERENCES universes(id) ON DELETE SET NULL
);

-- Univers visibles dans un profil (table de liaison ordonnée)
CREATE TABLE IF NOT EXISTS profile_universes (
    profile_id  TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (profile_id, universe_id),
    FOREIGN KEY (profile_id)  REFERENCES display_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (universe_id) REFERENCES universes(id)        ON DELETE CASCADE
);

-- Colonne à ajouter sur la table devices existante
ALTER TABLE devices ADD COLUMN profile_id TEXT REFERENCES display_profiles(id) ON DELETE SET NULL;
```

### 3.2 Modules disponibles (seed)

Inséré une fois au démarrage si la table `modules` est vide.
Liste issue de `web/auth_permissions.py` → `ALL_MENU_TAGS` + mapping label/icon/category.

| id              | label            | icon               | category      | requires_module |
|-----------------|------------------|--------------------|---------------|-----------------|
| dashboard       | Tableau de bord  | Layout_white       | core          | null            |
| chat            | Discussion       | Chat_white         | core          | null            |
| planner         | Planificateur    | Calendar_white     | transversal   | null            |
| briefing        | Briefing         | PencilInk_white    | transversal   | null            |
| home            | Domotique        | Home_white         | maison        | null            |
| cameras         | Caméras          | Camera_white       | maison        | null            |
| senses          | Capteurs         | IOT_white          | maison        | null            |
| music           | Musique          | Music_white        | maison        | null            |
| infrastructure  | Infrastructure   | Tiles_white        | societe       | null            |
| societe         | Sociétés         | Globe_white        | societe       | societe         |
| marketing       | Marketing        | PencilInk_white    | societe       | null            |
| webagent        | Agent Web        | Globe_white        | tools         | null            |
| cad             | Agent CAD        | Code_white         | tools         | null            |
| printers        | Imprimantes      | IOT_white          | tools         | null            |
| skills          | Compétences      | Setting_white      | tools         | null            |
| memory          | Mémoire          | History_white      | tools         | null            |
| library         | Bibliothèque     | LibraryFill_white  | tools         | null            |
| settings        | Paramètres       | Setting_white      | tools         | null            |

### 3.3 Profils par défaut (seed)

Créés si aucun profil n'existe.

**Profil "Complet"** (admin)
- Thème : dark, densité : normal
- Univers : Dashboard, Maison, Société, Planification, Outils
- Univers par défaut : Dashboard

**Profil "Mobile"**
- Thème : dark, densité : compact
- Univers : Dashboard uniquement (chat intégré)
- Univers par défaut : Dashboard

**Profil "Maison"**
- Thème : light, densité : comfortable
- Univers : Dashboard, Maison
- Univers par défaut : Maison

---

## 4. Fichier `core/views.py` (nouveau)

Modèle de données Python pur, sans dépendance FastAPI.

```python
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
    ModuleDef("music",          "Musique",           "Music_white",       "maison"),
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
```

---

## 5. Fichier `core/routes/__init__.py` (nouveau)

```python
# core/routes/__init__.py
```

---

## 6. Fichier `core/routes/profiles.py` (nouveau)

Logique métier pure (pas de FastAPI ici) : CRUD profils, univers, assignation device.
Séparation claire entre logique et transport HTTP.

```python
"""
core/routes/profiles.py — Logique métier profils & univers.
Appelé par web/router_profiles.py.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from web.auth_db import _connect          # réutilise la connexion SQLite existante
from core.views import ALL_MODULES, MODULE_BY_ID, available_modules
from config import MODULES_ENABLED


# ── Initialisation ─────────────────────────────────────────────────────────

def initialize() -> None:
    """Crée les tables, seed modules et profils par défaut."""
    conn = _connect()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS modules (
            id               TEXT PRIMARY KEY,
            label            TEXT NOT NULL,
            icon             TEXT NOT NULL,
            category         TEXT NOT NULL,
            requires_module  TEXT
        );

        CREATE TABLE IF NOT EXISTS universes (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            icon        TEXT NOT NULL DEFAULT '◈',
            color       TEXT NOT NULL DEFAULT '#00c8f0',
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS universe_modules (
            universe_id TEXT NOT NULL,
            module_id   TEXT NOT NULL,
            position    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (universe_id, module_id),
            FOREIGN KEY (universe_id) REFERENCES universes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS display_profiles (
            id                  TEXT PRIMARY KEY,
            name                TEXT NOT NULL,
            theme               TEXT NOT NULL DEFAULT 'dark',
            density             TEXT NOT NULL DEFAULT 'normal',
            default_universe_id TEXT,
            created_at          REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile_universes (
            profile_id  TEXT NOT NULL,
            universe_id TEXT NOT NULL,
            position    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (profile_id, universe_id),
            FOREIGN KEY (profile_id)  REFERENCES display_profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (universe_id) REFERENCES universes(id)        ON DELETE CASCADE
        );
        """)

        # Migration devices si colonne absente
        cols = [r[1] for r in conn.execute("PRAGMA table_info(devices)").fetchall()]
        if "profile_id" not in cols:
            conn.execute("ALTER TABLE devices ADD COLUMN profile_id TEXT")

    conn.close()
    _seed_modules()
    _seed_default_profiles()


def _seed_modules() -> None:
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    if count == 0:
        with conn:
            for m in ALL_MODULES:
                conn.execute(
                    "INSERT OR IGNORE INTO modules (id, label, icon, category, requires_module) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (m.id, m.label, m.icon, m.category, m.requires_module),
                )
    conn.close()


def _seed_default_profiles() -> None:
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) FROM display_profiles").fetchone()[0]
    if count > 0:
        conn.close()
        return

    now = time.time()

    def _make_universe(conn, name, icon, color, position, module_ids):
        uid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO universes (id, name, icon, color, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, name, icon, color, position, now),
        )
        for pos, mid in enumerate(module_ids):
            conn.execute(
                "INSERT INTO universe_modules (universe_id, module_id, position) VALUES (?, ?, ?)",
                (uid, mid, pos),
            )
        return uid

    def _make_profile(conn, name, theme, density, universe_ids, default_uid):
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO display_profiles (id, name, theme, density, default_universe_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, theme, density, default_uid, now),
        )
        for pos, uid in enumerate(universe_ids):
            conn.execute(
                "INSERT INTO profile_universes (profile_id, universe_id, position) VALUES (?, ?, ?)",
                (pid, uid, pos),
            )
        return pid

    with conn:
        # Profil Complet
        u_dash  = _make_universe(conn, "Dashboard",    "◈",  "#00c8f0", 0,
                                  ["dashboard", "chat"])
        u_maison= _make_universe(conn, "Maison",       "🏠", "#8870ff", 1,
                                  ["home", "cameras", "senses", "music"])
        u_societe= _make_universe(conn, "Société",     "◈",  "#00e898", 2,
                                  ["infrastructure", "societe", "marketing"])
        u_plan  = _make_universe(conn, "Planification","📅", "#ff9a00", 3,
                                  ["planner", "briefing"])
        u_tools = _make_universe(conn, "Outils",       "⚙",  "#ff6b35", 4,
                                  ["webagent", "cad", "printers", "skills",
                                   "memory", "library", "settings"])
        _make_profile(conn, "Complet", "dark", "normal",
                      [u_dash, u_maison, u_societe, u_plan, u_tools], u_dash)

        # Profil Mobile
        u_mobile= _make_universe(conn, "Dashboard",   "◈",  "#00c8f0", 0,
                                  ["dashboard", "chat", "planner", "briefing"])
        _make_profile(conn, "Mobile", "dark", "compact", [u_mobile], u_mobile)

        # Profil Maison
        u_mh_dash = _make_universe(conn, "Dashboard", "◈",  "#00c8f0", 0,
                                   ["dashboard", "chat"])
        u_mh_home = _make_universe(conn, "Maison",    "🏠", "#8870ff", 1,
                                   ["home", "cameras", "senses", "music"])
        _make_profile(conn, "Maison", "light", "comfortable",
                      [u_mh_dash, u_mh_home], u_mh_home)

    conn.close()


# ── Modules ────────────────────────────────────────────────────────────────

def list_modules() -> list[dict]:
    """Retourne les modules disponibles (filtrés par feature flags actifs)."""
    avail = {m.id for m in available_modules(MODULES_ENABLED)}
    conn = _connect()
    rows = conn.execute("SELECT * FROM modules ORDER BY category, id").fetchall()
    conn.close()
    return [dict(r) for r in rows if r["id"] in avail]


# ── Univers ────────────────────────────────────────────────────────────────

def list_universes() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM universes ORDER BY position").fetchall()
    result = []
    for row in rows:
        modules = conn.execute(
            "SELECT module_id, position FROM universe_modules "
            "WHERE universe_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        result.append({**dict(row), "modules": [r["module_id"] for r in modules]})
    conn.close()
    return result


def get_universe(universe_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM universes WHERE id = ?", (universe_id,)).fetchone()
    if not row:
        conn.close()
        return None
    modules = conn.execute(
        "SELECT module_id FROM universe_modules WHERE universe_id = ? ORDER BY position",
        (universe_id,),
    ).fetchall()
    result = {**dict(row), "modules": [r["module_id"] for r in modules]}
    conn.close()
    return result


def create_universe(name: str, icon: str, color: str, module_ids: list[str]) -> dict:
    uid = str(uuid.uuid4())
    now = time.time()
    conn = _connect()
    max_pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM universes").fetchone()[0]
    with conn:
        conn.execute(
            "INSERT INTO universes (id, name, icon, color, position, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, name, icon, color, max_pos + 1, now),
        )
        for pos, mid in enumerate(module_ids):
            conn.execute(
                "INSERT INTO universe_modules (universe_id, module_id, position) "
                "VALUES (?, ?, ?)", (uid, mid, pos),
            )
    conn.close()
    return get_universe(uid)


def update_universe(universe_id: str, name: str, icon: str, color: str,
                    module_ids: list[str]) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT id FROM universes WHERE id = ?", (universe_id,)).fetchone()
    if not row:
        conn.close()
        return None
    with conn:
        conn.execute(
            "UPDATE universes SET name=?, icon=?, color=? WHERE id=?",
            (name, icon, color, universe_id),
        )
        conn.execute("DELETE FROM universe_modules WHERE universe_id=?", (universe_id,))
        for pos, mid in enumerate(module_ids):
            conn.execute(
                "INSERT INTO universe_modules (universe_id, module_id, position) "
                "VALUES (?, ?, ?)", (universe_id, mid, pos),
            )
    conn.close()
    return get_universe(universe_id)


def delete_universe(universe_id: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT id FROM universes WHERE id=?", (universe_id,)).fetchone()
    if not row:
        conn.close()
        return False
    with conn:
        conn.execute("DELETE FROM universes WHERE id=?", (universe_id,))
    conn.close()
    return True


# ── Profils ────────────────────────────────────────────────────────────────

def list_profiles() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM display_profiles ORDER BY created_at").fetchall()
    result = []
    for row in rows:
        universes = conn.execute(
            "SELECT universe_id, position FROM profile_universes "
            "WHERE profile_id=? ORDER BY position",
            (row["id"],),
        ).fetchall()
        result.append({
            **dict(row),
            "universe_ids": [r["universe_id"] for r in universes],
        })
    conn.close()
    return result


def get_profile(profile_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM display_profiles WHERE id=?", (profile_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    universes = conn.execute(
        "SELECT universe_id FROM profile_universes WHERE profile_id=? ORDER BY position",
        (profile_id,),
    ).fetchall()
    # Hydrate chaque univers
    universe_list = []
    for u in universes:
        uni = get_universe(u["universe_id"])
        if uni:
            universe_list.append(uni)
    result = {
        **dict(row),
        "universes": universe_list,
    }
    conn.close()
    return result


def create_profile(name: str, theme: str, density: str,
                   universe_ids: list[str], default_universe_id: str | None) -> dict:
    pid = str(uuid.uuid4())
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO display_profiles "
            "(id, name, theme, density, default_universe_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, theme, density, default_universe_id, time.time()),
        )
        for pos, uid in enumerate(universe_ids):
            conn.execute(
                "INSERT INTO profile_universes (profile_id, universe_id, position) "
                "VALUES (?, ?, ?)", (pid, uid, pos),
            )
    conn.close()
    return get_profile(pid)


def update_profile(profile_id: str, name: str, theme: str, density: str,
                   universe_ids: list[str], default_universe_id: str | None) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT id FROM display_profiles WHERE id=?", (profile_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    with conn:
        conn.execute(
            "UPDATE display_profiles SET name=?, theme=?, density=?, "
            "default_universe_id=? WHERE id=?",
            (name, theme, density, default_universe_id, profile_id),
        )
        conn.execute("DELETE FROM profile_universes WHERE profile_id=?", (profile_id,))
        for pos, uid in enumerate(universe_ids):
            conn.execute(
                "INSERT INTO profile_universes (profile_id, universe_id, position) "
                "VALUES (?, ?, ?)", (profile_id, uid, pos),
            )
    conn.close()
    return get_profile(profile_id)


def delete_profile(profile_id: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT id FROM display_profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        conn.close()
        return False
    with conn:
        conn.execute("DELETE FROM display_profiles WHERE id=?", (profile_id,))
        conn.execute(
            "UPDATE devices SET profile_id=NULL WHERE profile_id=?", (profile_id,)
        )
    conn.close()
    return True


# ── Device → Profile ────────────────────────────────────────────────────────

def assign_profile_to_device(device_id: str, profile_id: str | None) -> bool:
    conn = _connect()
    row = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        conn.close()
        return False
    with conn:
        conn.execute(
            "UPDATE devices SET profile_id=? WHERE id=?", (profile_id, device_id)
        )
    conn.close()
    return True


def get_device_profile(device_id: str) -> dict | None:
    """Retourne le profil hydraté du device, ou le profil 'Complet' par défaut."""
    conn = _connect()
    row = conn.execute(
        "SELECT profile_id FROM devices WHERE id=?", (device_id,)
    ).fetchone()
    conn.close()
    if row and row["profile_id"]:
        return get_profile(row["profile_id"])
    # Fallback : premier profil (seed "Complet")
    conn = _connect()
    first = conn.execute(
        "SELECT id FROM display_profiles ORDER BY created_at LIMIT 1"
    ).fetchone()
    conn.close()
    return get_profile(first["id"]) if first else None
```

---

## 7. Fichier `core/routes/devices.py` (nouveau)

```python
"""
core/routes/devices.py — Logique métier extension devices (profil, infos device).
"""
from __future__ import annotations
from web.auth_db import _connect, list_devices


def get_device_with_profile(device_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("profile_id"):
        from core.routes.profiles import get_profile
        d["profile"] = get_profile(d["profile_id"])
    else:
        d["profile"] = None
    return d
```

---

## 8. Fichier `web/router_profiles.py` (nouveau)

Router FastAPI branché dans `server.py`. Tous les endpoints admin requièrent le groupe
`admin` (via `_require_admin` de `router_auth.py`).

### Endpoints

```
GET  /api/profile              → profil du device courant (via JWT device_id)
GET  /api/modules              → liste des modules disponibles
GET  /api/universes            → liste tous les univers
POST /api/universes            → crée un univers (admin)
PUT  /api/universes/{id}       → modifie un univers (admin)
DELETE /api/universes/{id}     → supprime un univers (admin)
GET  /api/profiles             → liste tous les profils (admin)
POST /api/profiles             → crée un profil (admin)
PUT  /api/profiles/{id}        → modifie un profil (admin)
DELETE /api/profiles/{id}      → supprime un profil (admin)
POST /api/devices/{id}/profile → assigne un profil à un device (admin)
```

### Schéma de réponse `/api/profile`

```json
{
  "profile": {
    "id": "uuid",
    "name": "Complet",
    "theme": "dark",
    "density": "normal",
    "default_universe_id": "uuid",
    "universes": [
      {
        "id": "uuid",
        "name": "Dashboard",
        "icon": "◈",
        "color": "#00c8f0",
        "position": 0,
        "modules": ["dashboard", "chat"]
      },
      {
        "id": "uuid",
        "name": "Maison",
        "icon": "🏠",
        "color": "#8870ff",
        "position": 1,
        "modules": ["home", "cameras", "senses", "music"]
      }
    ]
  }
}
```

### Intégration dans `server.py`

Ajouter après les imports existants :

```python
from core.routes.profiles import initialize as _profiles_init
from web.router_profiles import router as _profiles_router

app.include_router(_profiles_router)
```

Et dans `_startup()` :

```python
_profiles_init()
```

---

## 9. Modifications `web/auth_db.py`

Ajouter la fonction `get_device_profile_id` :

```python
def get_device_profile_id(device_id: str) -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT profile_id FROM devices WHERE id=?", (device_id,)
    ).fetchone()
    conn.close()
    return row["profile_id"] if row else None
```

---

## 10. Frontend — consommation du profil

### 10.1 Chargement au démarrage (`core/core.js`)

Au `DOMContentLoaded`, avant d'afficher la nav :

```javascript
// 1. Charger le profil depuis le serveur
const profileRes = await fetch('/api/profile', { headers: { Authorization: `Bearer ${token}` } });
const { profile } = await profileRes.json();

// 2. Appliquer le thème
document.documentElement.setAttribute('data-theme', profile.theme);

// 3. Appliquer la densité
document.documentElement.setAttribute('data-density', profile.density);

// 4. Construire la nav dynamiquement depuis profile.universes
buildNav(profile.universes, profile.default_universe_id);
```

### 10.2 Fonction `buildNav(universes, defaultUniverseId)`

Remplace la nav statique hardcodée dans `index.html`.

```javascript
function buildNav(universes, defaultUniverseId) {
  const nav = document.getElementById('sidebar');
  // Vider les nav-items existants
  nav.querySelectorAll('.nav-item').forEach(el => el.remove());

  for (const universe of universes) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.dataset.universe = universe.id;

    // Le premier module de l'univers est la vue d'entrée
    const entryModule = universe.modules[0];
    li.dataset.view = entryModule;

    li.innerHTML = `
      <img src="/static/icons/${moduleIconMap[entryModule]}.svg" class="nav-icon" />
      <span>${universe.name}</span>
    `;

    if (universe.id === defaultUniverseId) {
      li.classList.add('active');
    }

    li.addEventListener('click', () => navigateToUniverse(universe));
    nav.appendChild(li);
  }
}
```

### 10.3 Navigation dans un univers

Quand on clique sur un univers, afficher ses sous-modules comme onglets dans la vue.
La vue principale de chaque univers est un `universe-view` avec :
- Une barre d'onglets pour les modules de l'univers
- Le contenu du module actif

### 10.4 CSS thème par densité

```css
[data-density="compact"]     { --spacing-base: 8px;  --font-size-base: 12px; }
[data-density="normal"]      { --spacing-base: 14px; --font-size-base: 14px; }
[data-density="comfortable"] { --spacing-base: 20px; --font-size-base: 16px; }
```

---

## 11. Vue admin `profile-editor` (`web/static/views/profile-editor/`)

Interface permettant à l'admin de :

1. **Lister / créer / supprimer des univers** avec leurs modules
2. **Lister / créer / supprimer des profils** avec leurs univers et thème
3. **Assigner un profil à un device** depuis la liste des devices

Accessible via `data-page="profile-editor"` dans la nav admin.
Utilise exclusivement l'API REST définie ci-dessus.

---

## 12. Ordre d'implémentation recommandé pour les agents

1. **`core/views.py`** — catalogue des modules (aucune dépendance)
2. **`core/routes/__init__.py`** — fichier vide
3. **`core/routes/profiles.py`** — logique métier + init SQLite
4. **`core/routes/devices.py`** — extension devices
5. **`web/auth_db.py`** — ajouter `get_device_profile_id`
6. **`web/router_profiles.py`** — router FastAPI avec tous les endpoints
7. **`web/server.py`** — brancher le router + appel `_profiles_init()` dans `_startup()`
8. **`web/static/core/core.js`** — charger `/api/profile` au démarrage, appliquer thème/densité, `buildNav()`
9. **`web/static/index.html`** — alléger la nav statique (garder une nav minimale de fallback)
10. **`web/static/views/profile-editor/`** — UI admin CRUD

---

## 13. Contraintes & règles à respecter

- **Non-intrusif** : ne pas modifier `core/` existant, uniquement ajouter
- **Compatibilité** : si `/api/profile` échoue (auth off, device sans profil), fallback sur la nav statique existante de `index.html`
- **Feature flags** : respecter `config.MODULES_ENABLED` — le module `societe` n'apparaît que si `MODULES_ENABLED["societe"] = True`
- **Auth** : les endpoints admin (`/api/profiles`, `/api/universes`, `POST /api/devices/{id}/profile`) nécessitent le groupe `admin`. `/api/profile` (GET) est accessible à tout device authentifié.
- **SQLite thread-safety** : utiliser `_connect()` de `web/auth_db.py` (WAL + `check_same_thread=False`)
- **Pas de migration destructive** : `ALTER TABLE devices ADD COLUMN profile_id` est idempotente (vérifier si la colonne existe avant)
- **Tests** : créer `tests/test_profiles.py` couvrant init, CRUD univers, CRUD profils, assignation device

---

## 14. Fichiers à créer / modifier — récapitulatif

| Fichier | Action |
|---|---|
| `core/views.py` | CRÉER |
| `core/routes/__init__.py` | CRÉER |
| `core/routes/profiles.py` | CRÉER |
| `core/routes/devices.py` | CRÉER |
| `web/auth_db.py` | MODIFIER — ajouter `get_device_profile_id` |
| `web/router_profiles.py` | CRÉER |
| `web/server.py` | MODIFIER — inclure router + init dans `_startup()` |
| `web/static/core/core.js` | MODIFIER — charger profil au démarrage |
| `web/static/index.html` | MODIFIER — nav minimale de fallback |
| `web/static/views/profile-editor/index.js` | CRÉER |
| `web/static/views/profile-editor/style.css` | CRÉER |
| `tests/test_profiles.py` | CRÉER |
