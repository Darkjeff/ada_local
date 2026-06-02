# Runtime State Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer un `RuntimeStateManager` singleton qui collecte l'état réel des services ADA (Ollama, n8n, HA, Navidrome, Docker) et court-circuiter le LLM pour répondre factuellement aux questions "état infra" dans Telegram et l'onglet Infrastructure.

**Architecture:** Un module `core/runtime_state.py` expose un singleton `runtime_state` avec `refresh()`, `get_state()`, `format_infra_status_fr()`. L'onglet Infrastructure délègue ses checks au singleton plutôt que de les recoder. Le `TelegramAdapter` intercepte les phrases "état infra" avant d'appeler le LLM et répond directement.

**Tech Stack:** Python 3.10+, `requests`, `subprocess`, PySide6 (QThread/QTimer), stdlib uniquement pour les nouveaux checks.

---

## Fichiers touchés

| Fichier | Action | Rôle |
|---|---|---|
| `core/runtime_state.py` | **Créer** | Singleton RuntimeStateManager |
| `config/infrastructure_registry.json` | **Créer** | Registre hôtes (optionnel, structure seulement) |
| `tests/test_runtime_state.py` | **Créer** | Tests unitaires du module |
| `gui/tabs/infrastructure.py` | **Modifier** | Déléguer les checks au singleton |
| `core/telegram_adapter.py` | **Modifier** | Routing déterministe "état infra" |

---

## Task 1 : Créer `core/runtime_state.py`

**Files:**
- Create: `core/runtime_state.py`

- [ ] **Step 1 : Écrire le fichier**

```python
"""
Runtime State Engine — collecte l'état factuel des services sans passer par le LLM.

Usage:
    from core.runtime_state import runtime_state
    runtime_state.refresh()          # lance les checks (bloquant, ~3-5 s)
    state = runtime_state.get_state()
    text  = runtime_state.format_infra_status_fr()
"""

import subprocess
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Individual check functions — each returns a dict, never raises
# ---------------------------------------------------------------------------

def _check_ollama(ollama_url: str) -> dict:
    """GET /tags — vérifie qu'Ollama répond."""
    try:
        import requests
        r = requests.get(f"{ollama_url.rstrip('/')}/tags", timeout=3)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return {"status": "online", "details": f"{len(models)} modèle(s)"}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_n8n(n8n_url: str) -> dict:
    """GET /healthz — vérifie que n8n répond."""
    try:
        import requests
        r = requests.get(f"{n8n_url.rstrip('/')}/healthz", timeout=3)
        if r.status_code == 200:
            return {"status": "online", "details": ""}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_home_assistant(ha_url: str, ha_token: str) -> dict:
    """GET /api/ avec Bearer token — vérifie Home Assistant."""
    if not ha_url or not ha_token:
        return {"status": "unknown", "details": "non configuré"}
    try:
        import requests
        r = requests.get(
            f"{ha_url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=3,
        )
        if r.status_code == 200:
            return {"status": "online", "details": ""}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_navidrome(nav_url: str, user: str, password: str) -> dict:
    """Subsonic ping.view — vérifie Navidrome."""
    if not nav_url:
        return {"status": "unknown", "details": "non configuré"}
    try:
        import requests
        r = requests.get(
            f"{nav_url.rstrip('/')}/rest/ping.view",
            params={"u": user, "p": password, "v": "1.16.0", "c": "ada", "f": "json"},
            timeout=3,
        )
        if r.status_code == 200:
            body = r.json()
            if body.get("subsonic-response", {}).get("status") == "ok":
                return {"status": "online", "details": ""}
        return {"status": "offline", "details": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "offline", "details": str(e)[:80]}


def _check_docker() -> dict:
    """docker ps — liste les containers actifs."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
            timeout=5,
            stderr=subprocess.DEVNULL,
        )
        containers = []
        for line in out.decode().strip().splitlines():
            if line:
                parts = line.split("|")
                containers.append({
                    "name":   parts[0] if len(parts) > 0 else "",
                    "status": parts[1] if len(parts) > 1 else "",
                    "image":  parts[2] if len(parts) > 2 else "",
                })
        return {"status": "online", "containers": containers}
    except FileNotFoundError:
        return {"status": "unknown", "containers": []}
    except Exception:
        return {"status": "offline", "containers": []}


def _check_cuda() -> bool | None:
    """Détecte CUDA sans planter si torch n'est pas installé."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return None


def _check_voice() -> dict:
    """Détecte la disponibilité des modules STT/TTS."""
    stt = tts = None
    try:
        import core.stt  # noqa: F401
        stt = True
    except Exception:
        stt = False
    try:
        import core.tts  # noqa: F401
        tts = True
    except Exception:
        tts = False
    return {"stt": stt, "tts": tts, "wake_word": None}


# ---------------------------------------------------------------------------
# RuntimeStateManager
# ---------------------------------------------------------------------------

class RuntimeStateManager:
    """
    Collecte l'état factuel de tous les services ADA.
    Thread-safe : refresh() peut être appelé depuis n'importe quel thread.
    get_state() retourne toujours un dict valide, même avant le premier refresh().
    """

    def __init__(self):
        self._state: dict[str, Any] = self._empty_state()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Lance tous les checks et met à jour l'état interne. Ne lève jamais."""
        try:
            self._state = self._collect()
        except Exception as e:
            self._state["warnings"].append(f"refresh error: {e}")

    def get_state(self) -> dict:
        """Retourne l'état complet (dernière collecte)."""
        return self._state

    def get_infra_summary(self) -> dict:
        """Sous-ensemble services + docker, pratique pour l'UI."""
        s = self._state
        return {
            "services":   s.get("services", {}),
            "docker":     s.get("docker", {}),
            "warnings":   s.get("warnings", []),
            "updated_at": s.get("updated_at", ""),
        }

    def format_infra_status_fr(self) -> str:
        """Formate un résumé lisible en français. Ne lève jamais."""
        try:
            return self._format()
        except Exception as e:
            return f"⚠️ Impossible de récupérer l'état infra : {e}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _empty_state(self) -> dict:
        return {
            "services": {
                "ollama":         {"status": "unknown", "details": ""},
                "n8n":            {"status": "unknown", "details": ""},
                "home_assistant": {"status": "unknown", "details": ""},
                "navidrome":      {"status": "unknown", "details": ""},
            },
            "docker":     {"status": "unknown", "containers": []},
            "voice":      {"stt": None, "tts": None, "wake_word": None},
            "ai":         {"model": "", "cuda_available": None},
            "warnings":   [],
            "updated_at": "",
        }

    def _collect(self) -> dict:
        from config import OLLAMA_URL, RESPONDER_MODEL
        from core.settings_store import settings

        n8n_url  = settings.get("n8n.url", "http://localhost:5678")
        ha_url   = settings.get("home_assistant.url", "")
        ha_token = settings.get("home_assistant.token", "")

        nav_cfg  = settings.get("navidrome") or {}
        nav_url  = nav_cfg.get("url", "http://localhost:4533")
        nav_user = nav_cfg.get("user", "")
        nav_pass = nav_cfg.get("password", "")

        cuda = _check_cuda()
        warnings = []
        if cuda is False:
            warnings.append("CUDA indisponible, fallback CPU")

        return {
            "services": {
                "ollama":         _check_ollama(OLLAMA_URL),
                "n8n":            _check_n8n(n8n_url),
                "home_assistant": _check_home_assistant(ha_url, ha_token),
                "navidrome":      _check_navidrome(nav_url, nav_user, nav_pass),
            },
            "docker":     _check_docker(),
            "voice":      _check_voice(),
            "ai":         {"model": RESPONDER_MODEL, "cuda_available": cuda},
            "warnings":   warnings,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _format(self) -> str:
        s = self._state
        icons  = {"online": "🟢", "offline": "🔴", "unknown": "🟡"}
        labels = {
            "ollama":         "Ollama",
            "n8n":            "n8n",
            "home_assistant": "Home Assistant",
            "navidrome":      "Navidrome",
        }
        status_fr = {"online": "en ligne", "offline": "hors ligne", "unknown": "statut non vérifié"}

        lines = ["🖥️ *État infrastructure*\n"]

        for key, label in labels.items():
            svc    = s["services"].get(key, {})
            status = svc.get("status", "unknown")
            lines.append(f"{icons.get(status, '🟡')} {label} : {status_fr.get(status, status)}")

        docker     = s.get("docker", {})
        containers = docker.get("containers", [])
        if containers:
            lines.append("\n🐳 *Containers :*")
            for c in containers:
                lines.append(f"- {c['name']} : {c['status']}")
        elif docker.get("status") == "online":
            lines.append("\n🐳 Docker : aucun container actif")

        warnings = s.get("warnings", [])
        if warnings:
            lines.append("\n⚠️ *Alertes :*")
            for w in warnings:
                lines.append(f"- {w}")

        return "\n".join(lines)


# Module-level singleton
runtime_state = RuntimeStateManager()
```

- [ ] **Step 2 : Vérifier l'import depuis Python**

```bash
cd /c/wamp64/www/ada_local
python3 -c "from core.runtime_state import runtime_state; print(runtime_state.get_state())"
```

Résultat attendu : dict avec clés `services`, `docker`, `voice`, `ai`, `warnings`, `updated_at` (toutes à `unknown`/vide car `refresh()` n'a pas encore été appelé).

- [ ] **Step 3 : Commit**

```bash
git add core/runtime_state.py
git commit -m "feat: add RuntimeStateManager singleton (core/runtime_state.py)"
```

---

## Task 2 : Créer `config/infrastructure_registry.json`

**Files:**
- Create: `config/infrastructure_registry.json`

- [ ] **Step 1 : Créer le dossier config s'il n'existe pas et écrire le fichier**

```bash
mkdir -p /c/wamp64/www/ada_local/config
```

Contenu du fichier `config/infrastructure_registry.json` :

```json
{
  "_comment": "Registre des hôtes de l'infrastructure ADA. Non utilisé activement en v1 — structure pour la v2.",
  "hosts": [
    {
      "id": "ubuntu_bureau",
      "name": "Ubuntu Bureau",
      "ip": "192.168.1.70",
      "roles": ["ada", "docker", "ollama", "n8n", "navidrome"]
    },
    {
      "id": "nas",
      "name": "NAS Synology",
      "ip": "192.168.1.44",
      "roles": ["storage", "music", "plex"]
    },
    {
      "id": "proxmox",
      "name": "Proxmox",
      "ip": "192.168.1.166",
      "roles": ["virtualization", "home_assistant"]
    }
  ],
  "dependencies": [
    {"service": "navidrome", "depends_on": ["docker", "nas"]},
    {"service": "ada",       "depends_on": ["ollama", "n8n", "home_assistant"]}
  ]
}
```

- [ ] **Step 2 : Commit**

```bash
git add config/infrastructure_registry.json
git commit -m "feat: add infrastructure_registry.json (hosts structure, not yet wired)"
```

---

## Task 3 : Créer `tests/test_runtime_state.py`

**Files:**
- Create: `tests/test_runtime_state.py`

- [ ] **Step 1 : Écrire les tests**

```python
"""
Tests for core/runtime_state.py.

Run: pytest tests/test_runtime_state.py -v
These tests mock all network/subprocess calls so they pass offline.
"""

import sys
import types
import unittest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — mock heavy deps before importing the module
# ---------------------------------------------------------------------------

def _make_settings_mock():
    m = MagicMock()
    m.get.side_effect = lambda key, default=None: {
        "n8n.url":              "http://localhost:5678",
        "home_assistant.url":   "",
        "home_assistant.token": "",
        "navidrome":            None,
    }.get(key, default)
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRuntimeStateManager(unittest.TestCase):

    def _make_manager(self):
        """Import RuntimeStateManager with all external deps mocked."""
        # Patch settings and config before importing
        fake_settings = _make_settings_mock()
        config_mod = types.ModuleType("config")
        config_mod.OLLAMA_URL = "http://localhost:11434/api"
        config_mod.RESPONDER_MODEL = "qwen3:1.7b"

        with patch.dict("sys.modules", {
            "config": config_mod,
            "core.settings_store": MagicMock(settings=fake_settings),
        }):
            # Import fresh each time
            import importlib
            import core.runtime_state as mod
            importlib.reload(mod)
            return mod.RuntimeStateManager()

    def test_get_state_returns_dict_before_refresh(self):
        """get_state() must always return a dict, even before refresh()."""
        mgr = self._make_manager()
        state = mgr.get_state()
        self.assertIsInstance(state, dict)
        self.assertIn("services", state)
        self.assertIn("docker", state)
        self.assertIn("warnings", state)
        self.assertIn("updated_at", state)

    def test_format_infra_status_fr_returns_string(self):
        """format_infra_status_fr() must return a non-empty string."""
        mgr = self._make_manager()
        text = mgr.format_infra_status_fr()
        self.assertIsInstance(text, str)
        self.assertTrue(len(text) > 0)

    def test_format_after_refresh_contains_services(self):
        """After refresh(), formatted text contains service names."""
        mgr = self._make_manager()

        with patch("requests.get") as mock_get, \
             patch("subprocess.check_output", side_effect=FileNotFoundError):
            # All services return 200
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"models": []}
            mock_get.return_value = mock_response

            mgr.refresh()

        text = mgr.format_infra_status_fr()
        self.assertIn("Ollama", text)
        self.assertIn("n8n", text)
        self.assertIn("Home Assistant", text)

    def test_refresh_never_raises_when_all_services_offline(self):
        """refresh() must not raise even if every network call fails."""
        mgr = self._make_manager()
        with patch("requests.get", side_effect=ConnectionError("offline")), \
             patch("subprocess.check_output", side_effect=Exception("docker absent")):
            try:
                mgr.refresh()
            except Exception as e:
                self.fail(f"refresh() raised an exception: {e}")

        state = mgr.get_state()
        self.assertIsInstance(state, dict)
        # All services must be offline/unknown, not missing
        for svc in ("ollama", "n8n", "home_assistant", "navidrome"):
            self.assertIn(state["services"][svc]["status"], ("offline", "unknown"))

    def test_get_state_structure_after_refresh(self):
        """State dict has the expected schema after refresh()."""
        mgr = self._make_manager()
        with patch("requests.get", side_effect=ConnectionError()), \
             patch("subprocess.check_output", side_effect=FileNotFoundError()):
            mgr.refresh()

        state = mgr.get_state()
        self.assertIn("ai", state)
        self.assertIn("model", state["ai"])
        self.assertIn("cuda_available", state["ai"])
        self.assertIn("voice", state)
        self.assertIn("stt", state["voice"])
        self.assertIn("tts", state["voice"])

    def test_format_infra_status_fr_never_raises(self):
        """format_infra_status_fr() must not raise even with corrupt state."""
        mgr = self._make_manager()
        # Corrupt internal state deliberately
        mgr._state = {}
        try:
            result = mgr.format_infra_status_fr()
        except Exception as e:
            self.fail(f"format_infra_status_fr() raised: {e}")
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : Lancer les tests**

```bash
cd /c/wamp64/www/ada_local
python3 -m pytest tests/test_runtime_state.py -v
```

Résultat attendu : 6 tests PASS.

- [ ] **Step 3 : Commit**

```bash
git add tests/test_runtime_state.py
git commit -m "test: add RuntimeStateManager unit tests (offline-safe)"
```

---

## Task 4 : Modifier `gui/tabs/infrastructure.py`

**Files:**
- Modify: `gui/tabs/infrastructure.py`

Objectif : `InfraWorker.collect()` délègue à `runtime_state` et ajoute les lignes Navidrome et Home Assistant dans l'UI. On conserve la structure existante — on étend sans tout réécrire.

- [ ] **Step 1 : Remplacer `InfraWorker.collect()` et ajouter les imports**

Remplacer le bloc `collect()` actuel (lignes 44–99) par la version ci-dessous, et ajouter l'import du singleton en haut du fichier (après les imports existants) :

**Import à ajouter** (après `from qfluentwidgets import ...` ligne 16) :
```python
from core.runtime_state import runtime_state
```

**Nouvelle méthode `InfraWorker.collect()`** — remplace entièrement l'ancienne :
```python
def collect(self) -> None:
    """Délègue à runtime_state puis construit le dict pour l'UI."""
    runtime_state.refresh()
    summary = runtime_state.get_infra_summary()
    services = summary.get("services", {})

    result: dict = {
        "ollama":            services.get("ollama",         {}).get("status") == "online",
        "n8n":               services.get("n8n",            {}).get("status") == "online",
        "home_assistant":    services.get("home_assistant",  {}).get("status"),
        "navidrome":         services.get("navidrome",       {}).get("status"),
        "docker_containers": summary.get("docker", {}).get("containers", []),
        "workflows":         self._scan_workflows(),
    }
    self.updated.emit(result)

def _scan_workflows(self) -> list:
    """Rescans workflow JSON files (logique existante extraite)."""
    workflows = []
    if WORKFLOWS_DIR.exists():
        exported = {p.stem for p in WORKFLOWS_DIR.glob("*.json")}
        for action in _WORKFLOW_META:
            workflows.append({"action": action, "exported": action in exported})
    else:
        for action in _WORKFLOW_META:
            workflows.append({"action": action, "exported": False})
    return workflows
```

- [ ] **Step 2 : Ajouter les lignes Navidrome et Home Assistant dans `_build_left()`**

Dans `_build_left()`, après `self._row_ollama = _StatusRow("Ollama")` et son `addWidget`, ajouter :
```python
self._row_navidrome = _StatusRow("Navidrome")
self._row_ha        = _StatusRow("Home Assistant")
svc_lay.addWidget(self._row_navidrome)
svc_lay.addWidget(self._row_ha)
```

- [ ] **Step 3 : Mettre à jour `_on_updated()` pour les nouveaux services**

Dans `_on_updated()`, après les deux lignes existantes `self._row_n8n.set_status(...)` et `self._row_ollama.set_status(...)`, ajouter :
```python
# Navidrome et HA retournent une string de statut, pas un bool
nav_status = data.get("navidrome")
self._row_navidrome.set_status(
    True if nav_status == "online" else (False if nav_status == "offline" else None)
)
ha_status = data.get("home_assistant")
self._row_ha.set_status(
    True if ha_status == "online" else (False if ha_status == "offline" else None)
)
```

- [ ] **Step 4 : Vérifier visuellement**

Lancer ADA, ouvrir l'onglet Infrastructure, vérifier que :
- Les 4 services s'affichent (Ollama, n8n, Navidrome, Home Assistant)
- Le bouton "Actualiser" fonctionne toujours
- L'auto-refresh 30 s continue de fonctionner

- [ ] **Step 5 : Commit**

```bash
git add gui/tabs/infrastructure.py
git commit -m "feat: infrastructure tab delegates checks to RuntimeStateManager, adds Navidrome + HA rows"
```

---

## Task 5 : Modifier `core/telegram_adapter.py` — routing déterministe

**Files:**
- Modify: `core/telegram_adapter.py:204-237` (`_handle_text`)

Objectif : intercepter les questions "état infra" avant le LLM et répondre avec `runtime_state.format_infra_status_fr()`.

- [ ] **Step 1 : Ajouter la constante de triggers en haut du fichier**

Après les imports existants (ligne ~26), ajouter :
```python
# Triggers déterministes — répondent sans passer par le LLM
_INFRA_TRIGGERS = frozenset({
    "état infra", "etat infra", "status infra", "infrastructure status",
    "état de l'infra", "etat de l infra",
})
```

- [ ] **Step 2 : Ajouter le routing déterministe au début de `_handle_text()`**

Dans la méthode `_handle_text()` (ligne 204), insérer ce bloc **avant** la construction de `messages` (avant `with self._lock:`) :

```python
# --- Routing déterministe : état infra ---
text_lower = text.lower().strip()
if any(trigger in text_lower for trigger in _INFRA_TRIGGERS):
    from core.runtime_state import runtime_state
    runtime_state.refresh()
    self._send(chat_id, runtime_state.format_infra_status_fr())
    return
```

La méthode `_handle_text()` complète après modification :

```python
def _handle_text(self, chat_id: int, text: str):
    session_id = f"telegram_{chat_id}"

    # --- Routing déterministe : état infra ---
    text_lower = text.lower().strip()
    if any(trigger in text_lower for trigger in _INFRA_TRIGGERS):
        from core.runtime_state import runtime_state
        runtime_state.refresh()
        self._send(chat_id, runtime_state.format_infra_status_fr())
        return

    with self._lock:
        history = self._histories.setdefault(chat_id, [])

    # Build messages list
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages += history[-20:]

    # Skill injection
    messages = skill_manager.inject(messages, text)

    # Memory context injection into system message
    mem = memory_store.build_context(text, current_session_id=session_id)
    if mem:
        messages[0] = {
            "role": "system",
            "content": messages[0]["content"] + "\n\n" + mem,
        }

    messages.append({"role": "user", "content": text})

    response = self._call_llm(messages)

    # Save to history and memory
    with self._lock:
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": response})

    memory_store.save(session_id, "user", text)
    memory_store.save(session_id, "assistant", response)

    self._send(chat_id, response)
```

- [ ] **Step 3 : Vérifier**

Envoyer "état infra" dans Telegram. La réponse doit :
- Arriver en moins de 10 secondes
- Commencer par `🖥️ *État infrastructure*`
- **Ne pas** être une réponse vague du LLM

- [ ] **Step 4 : Commit**

```bash
git add core/telegram_adapter.py
git commit -m "feat: deterministic 'état infra' routing in TelegramAdapter bypasses LLM"
```

---

## Self-review

### Couverture spec

| Exigence spec | Couverte par |
|---|---|
| `core/runtime_state.py` avec singleton | Task 1 |
| `refresh()`, `get_state()`, `get_infra_summary()`, `format_infra_status_fr()` | Task 1 |
| Check Ollama (`/api/tags`) | Task 1 `_check_ollama` |
| Check n8n (`/healthz`) | Task 1 `_check_n8n` |
| Check Docker (`docker ps`) | Task 1 `_check_docker` |
| Check Navidrome (Subsonic ping) | Task 1 `_check_navidrome` |
| Check Home Assistant (`/api/`) | Task 1 `_check_home_assistant` |
| CUDA détection sans planter | Task 1 `_check_cuda` |
| Voice sans planter | Task 1 `_check_voice` |
| Aucun check ne plante ADA | Tous les checks en try/except |
| Timeout courts | timeout=3 sur tous les checks réseau |
| `config/infrastructure_registry.json` | Task 2 |
| Tests `get_state()` retourne dict | Task 3 |
| Tests `format_infra_status_fr()` retourne string | Task 3 |
| Tests offline (services down) | Task 3 |
| Onglet Infrastructure délègue à runtime_state | Task 4 |
| Navidrome + HA visibles dans l'UI | Task 4 |
| Routing déterministe Telegram | Task 5 |
| Réponse factuelle "état infra" sans LLM | Task 5 |

### Placeholder scan
Aucun TBD, TODO, "voir task N", "ajouter plus tard" dans le plan.

### Cohérence des types
- `InfraWorker.collect()` → `_scan_workflows()` : méthode définie dans la même classe ✓
- `runtime_state.get_infra_summary()` retourne `dict` avec clés `services`, `docker`, `warnings`, `updated_at` ✓
- `_on_updated()` reçoit toujours le même format de dict ✓

---

## Comment tester manuellement

1. **Lancer ADA** : `python3 main.py`
2. **Onglet Infrastructure** → cliquer "Actualiser" → vérifier que 4 services s'affichent
3. **Telegram** → envoyer `état infra` → vérifier réponse factuelle en < 10 s
4. **Tests unitaires** : `python3 -m pytest tests/test_runtime_state.py -v` → 6 PASS
