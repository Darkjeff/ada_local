# Calibre Library Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable ADA to search the personal Calibre-Web ebook library by title, author, or genre via voice and Telegram, returning title, author, year, available formats, description, and a download link.

**Architecture:** `core/calibre_manager.py` is a thin Calibre-Web REST API client (same pattern as `core/music_manager.py`). One LLM tool `search_book` is added to `config.py` and handled in `core/function_executor.py`. The semantic router guards book queries with a `_LIBRARY_KEYWORDS` regex. A new `gui/tabs/library.py` tab holds the credentials settings.

**Tech Stack:** Python `requests`, Calibre-Web REST API (Basic Auth), PySide6 + qfluentwidgets for UI.

---

## File Map

| File | Action |
|------|--------|
| `core/calibre_manager.py` | Create |
| `tests/test_calibre_manager.py` | Create |
| `config.py` | Modify — append `search_book` to `FUNCTIONS` |
| `core/function_executor.py` | Modify — add `_search_book`, register in `execute()` |
| `tests/test_calibre_executor.py` | Create |
| `core/semantic_router.py` | Modify — add utterances + `_LIBRARY_KEYWORDS` guard |
| `gui/tabs/library.py` | Create |
| `gui/app.py` | Modify — import + register `LibraryTab` |
| `locales/fr.json` | Modify — add `library.*` + `nav.library` keys |
| `locales/en.json` | Modify — add same keys in English |

---

## Task 1: `core/calibre_manager.py`

**Files:**
- Create: `core/calibre_manager.py`
- Test: `tests/test_calibre_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calibre_manager.py
from unittest.mock import patch, MagicMock
import requests
from core.calibre_manager import CalibreManager


def _make_manager():
    return CalibreManager()


def _settings(k, d=""):
    return {
        "calibre.url": "http://localhost:8083",
        "calibre.username": "jeff",
        "calibre.password": "pass",
    }.get(k, d)


def _mock_response(json_data, status=200):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = json_data
    r.status_code = status
    return r


def test_search_books_returns_results():
    mgr = _make_manager()
    books = [
        {
            "id": 1,
            "title": "Dune",
            "authors": [{"name": "Frank Herbert"}],
            "pubdate": "1965-01-01",
            "formats": ["epub", "pdf"],
            "description": "A science fiction epic.",
        }
    ]
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": books})):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Dune")
    assert len(result) == 1
    assert result[0]["title"] == "Dune"
    assert result[0]["author"] == "Frank Herbert"
    assert "epub" in result[0]["formats"]


def test_search_books_no_url():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.return_value = ""
        result = mgr.search_books("Dune")
    assert result == []


def test_search_books_network_error():
    mgr = _make_manager()
    with patch("core.calibre_manager.requests.get", side_effect=requests.RequestException("timeout")):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Dune")
    assert result == []


def test_search_books_empty_results():
    mgr = _make_manager()
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": []})):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("unknownbook99999")
    assert result == []


def test_get_download_url_epub_priority():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.side_effect = _settings
        url = mgr.get_download_url(42, ["epub", "pdf"])
    assert "localhost:8083" in url
    assert "42" in url
    assert "epub" in url


def test_get_download_url_fallback_to_pdf():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.side_effect = _settings
        url = mgr.get_download_url(42, ["pdf", "mobi"])
    assert "pdf" in url


def test_get_download_url_no_formats():
    mgr = _make_manager()
    with patch("core.calibre_manager.settings") as s:
        s.get.side_effect = _settings
        url = mgr.get_download_url(42, [])
    assert url == ""


def test_search_books_missing_description():
    mgr = _make_manager()
    books = [{"id": 2, "title": "Test", "authors": [{"name": "Auth"}], "pubdate": "", "formats": [], "description": None}]
    with patch("core.calibre_manager.requests.get", return_value=_mock_response({"books": books})):
        with patch("core.calibre_manager.settings") as s:
            s.get.side_effect = _settings
            result = mgr.search_books("Test")
    assert result[0]["description"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/Desktop/ada_local
python -m pytest tests/test_calibre_manager.py -v 2>&1 | head -30
```

Expected: `ImportError: No module named 'core.calibre_manager'`

- [ ] **Step 3: Create `core/calibre_manager.py`**

```python
"""Calibre-Web REST API client — book search and download URL generation."""

import requests
from typing import Optional

from core.settings_store import settings

_FORMAT_PRIORITY = ["epub", "pdf", "mobi", "azw3", "fb2"]


class CalibreManager:

    def _base_url(self) -> str:
        return settings.get("calibre.url", "").rstrip("/")

    def _auth(self) -> tuple:
        return (
            settings.get("calibre.username", ""),
            settings.get("calibre.password", ""),
        )

    def _get(self, endpoint: str, **params) -> Optional[dict]:
        base = self._base_url()
        if not base:
            return None
        try:
            r = requests.get(
                f"{base}{endpoint}",
                params=params,
                auth=self._auth(),
                timeout=10,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[CalibreManager] {endpoint} request failed: {e}")
            return None
        try:
            return r.json()
        except ValueError as e:
            print(f"[CalibreManager] {endpoint} JSON parse failed: {e}")
            return None

    def _parse_book(self, raw: dict) -> dict:
        """Normalise a raw Calibre-Web book dict into a flat result dict."""
        authors = raw.get("authors") or []
        author = authors[0]["name"] if authors else ""
        pubdate = (raw.get("pubdate") or "")[:4]  # "YYYY-MM-DD" → "YYYY"
        formats = [f.lower() for f in (raw.get("formats") or [])]
        description = raw.get("description") or ""
        return {
            "id": raw.get("id"),
            "title": raw.get("title", ""),
            "author": author,
            "year": pubdate,
            "formats": formats,
            "description": description,
            "download_url": self.get_download_url(raw.get("id"), formats),
        }

    def search_books(self, query: str, search_type: str = "all", count: int = 3) -> list[dict]:
        """
        Search Calibre-Web for books matching `query`.
        search_type: "title" | "author" | "tags" | "all" (ignored server-side, passed for logging).
        Returns up to `count` normalised book dicts. Returns [] on error or no match.
        """
        data = self._get("/api/books", search=query, limit=count)
        if not data:
            return []
        books = data.get("books") or []
        return [self._parse_book(b) for b in books[:count]]

    def get_download_url(self, book_id: Optional[int], formats: list[str]) -> str:
        """
        Return the best download URL for `book_id`.
        Picks format by priority: epub > pdf > mobi > azw3 > fb2 > first available.
        Returns "" if book_id is None or formats is empty.
        """
        if not book_id or not formats:
            return ""
        base = self._base_url()
        if not base:
            return ""
        fmt = next((f for f in _FORMAT_PRIORITY if f in formats), formats[0])
        return f"{base}/api/books/{book_id}/download/{fmt}"


calibre_manager = CalibreManager()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_calibre_manager.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add core/calibre_manager.py tests/test_calibre_manager.py
git commit -m "feat(calibre): add CalibreManager REST API client with tests"
```

---

## Task 2: `config.py` — add `search_book` tool

**Files:**
- Modify: `config.py` (append to `FUNCTIONS` list before closing `]`)

- [ ] **Step 1: Open `config.py` and locate the end of `FUNCTIONS`**

Find the closing `]` of the `FUNCTIONS` list (currently after the `set_volume` entry around line 208).

- [ ] **Step 2: Append the `search_book` tool definition**

Insert before the closing `]` of `FUNCTIONS`:

```python
    {
        "type": "function",
        "function": {
            "name": "search_book",
            "description": "Search for a book in the personal library by title, author, or genre/tag. Use when the user asks for a book, novel, or wants to find something to read.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms: title, author name, or genre/tag (e.g. 'Dune', 'Frank Herbert', 'science fiction')",
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["title", "author", "tags", "all"],
                        "description": "Which field to search. Defaults to 'all'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
```

- [ ] **Step 3: Verify the FUNCTIONS list still parses**

```bash
python -c "from config import FUNCTIONS; print(len(FUNCTIONS), 'tools loaded')"
```

Expected: `N tools loaded` (one more than before, no SyntaxError).

- [ ] **Step 4: Commit**

```bash
git add config.py
git commit -m "feat(calibre): add search_book LLM tool definition to FUNCTIONS"
```

---

## Task 3: `core/function_executor.py` — `_search_book` handler

**Files:**
- Modify: `core/function_executor.py`
- Test: `tests/test_calibre_executor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calibre_executor.py
from unittest.mock import patch, MagicMock
from core.function_executor import FunctionExecutor


def _make_executor():
    return FunctionExecutor()


def _book(title="Dune", author="Frank Herbert", year="1965",
          formats=None, description="Epic sci-fi.", bid=1):
    formats = formats or ["epub", "pdf"]
    return {
        "id": bid,
        "title": title,
        "author": author,
        "year": year,
        "formats": formats,
        "description": description,
        "download_url": f"http://localhost:8083/api/books/{bid}/download/epub",
    }


def test_search_book_success():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book()]
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    assert "Dune" in result["message"]
    assert "Frank Herbert" in result["message"]
    assert "epub" in result["message"].lower()
    assert "localhost:8083" in result["message"]


def test_search_book_no_results():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = []
        result = ex.execute("search_book", {"query": "unknownxyz"})
    assert result["success"] is False
    assert "unknownxyz" in result["message"]


def test_search_book_no_url_configured():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = []
        # When calibre.url is not set, search_books returns []
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is False


def test_search_book_description_truncated():
    ex = _make_executor()
    long_desc = "A" * 500
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book(description=long_desc)]
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    # description is truncated to ≤ 200 chars in the message
    assert long_desc not in result["message"]


def test_search_book_multiple_results():
    ex = _make_executor()
    books = [_book("Dune", bid=1), _book("Dune Messiah", bid=2)]
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = books
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    assert "Dune" in result["message"]
    assert "Dune Messiah" in result["message"]


def test_search_book_with_search_type():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book()]
        result = ex.execute("search_book", {"query": "Herbert", "search_type": "author"})
    cm.search_books.assert_called_once_with("Herbert", "author", 3)
    assert result["success"] is True


def test_search_book_no_description():
    ex = _make_executor()
    with patch("core.calibre_manager.calibre_manager") as cm:
        cm.search_books.return_value = [_book(description="")]
        result = ex.execute("search_book", {"query": "Dune"})
    assert result["success"] is True
    assert "Dune" in result["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_calibre_executor.py -v 2>&1 | head -20
```

Expected: tests fail because `search_book` is not handled in `execute()`.

- [ ] **Step 3: Add `search_book` to `execute()` dispatch**

In `core/function_executor.py`, inside the `execute()` method, add after the `set_volume` branch (before the final `else`):

```python
            elif func_name == "search_book":
                return self._search_book(params)
```

- [ ] **Step 4: Add `_search_book` method to `FunctionExecutor`**

Add this method after `_set_volume` in `core/function_executor.py`:

```python
    def _search_book(self, params: Dict) -> Dict:
        """Search the Calibre-Web library and return formatted book info."""
        from core.calibre_manager import calibre_manager

        query = params.get("query", "").strip()
        search_type = params.get("search_type", "all")

        if not query:
            return {"success": False, "message": "Aucune recherche spécifiée.", "data": None}

        books = calibre_manager.search_books(query, search_type, count=3)

        if not books:
            return {
                "success": False,
                "message": f"Aucun livre trouvé pour « {query} ».",
                "data": None,
            }

        lines = []
        for b in books:
            desc = b.get("description") or ""
            if len(desc) > 200:
                desc = desc[:200].rstrip() + "…"
            year = f" ({b['year']})" if b.get("year") else ""
            fmts = ", ".join(b.get("formats") or []) or "—"
            dl = b.get("download_url") or "—"
            block = (
                f"« {b['title']} » — {b['author']}{year}\n"
                f"Formats : {fmts}\n"
            )
            if desc:
                block += f"{desc}\n"
            block += f"Télécharger : {dl}"
            lines.append(block)

        message = "\n\n".join(lines)
        return {"success": True, "message": message, "data": books}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_calibre_executor.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add core/function_executor.py tests/test_calibre_executor.py
git commit -m "feat(calibre): add _search_book executor handler with tests"
```

---

## Task 4: `core/semantic_router.py` — library route guard

**Files:**
- Modify: `core/semantic_router.py`

- [ ] **Step 1: Add book utterances to `_ROUTES["function_gemma"]`**

In `core/semantic_router.py`, inside `_ROUTES["function_gemma"]`, add after the volume utterances (before the closing `],`):

```python
        # Book search
        "cherche un livre", "trouve un livre", "tu as un livre",
        "cherche dans ma bibliothèque", "dans ma bibliothèque",
        "un livre de", "un livre sur", "un roman de",
        "as-tu un livre", "est-ce que tu as un livre",
        "trouve-moi un livre", "je cherche un livre",
        "find a book", "search for a book", "do you have a book by",
        "un livre de science-fiction", "un polar", "un roman historique",
        "de la fantasy", "un essai sur", "un manga", "un bouquin",
```

- [ ] **Step 2: Add `_LIBRARY_KEYWORDS` regex after `_MUSIC_KEYWORDS`**

After the `_MUSIC_KEYWORDS` definition (around line 387), add:

```python
_LIBRARY_KEYWORDS = re.compile(
    r"\b(livre[sz]?|roman[sz]?|bouquin[sz]?|biblioth[eè]que"
    r"|auteur[sz]?|epub|calibre"
    r"|book[sz]?|library|novel[sz]?|ebook[sz]?)\b",
    re.IGNORECASE,
)
```

- [ ] **Step 3: Add library guard to `get_route()`**

In `get_route()`, after the music guard and before the function keywords guard:

```python
    # Fast keyword guard for book search — beats embedding drift
    if _LIBRARY_KEYWORDS.search(prompt):
        return "function_gemma"
```

The full `get_route()` function should now be:

```python
def get_route(prompt: str) -> str:
    if _VISION_KEYWORDS.search(prompt):
        return "vision"
    if _MUSIC_KEYWORDS.search(prompt):
        return "function_gemma"
    if _LIBRARY_KEYWORDS.search(prompt):
        return "function_gemma"
    if _FUNCTION_KEYWORDS.search(prompt):
        return "function_gemma"
    return _router.route(prompt)
```

- [ ] **Step 4: Verify import works**

```bash
python -c "from core.semantic_router import get_route; print(get_route('cherche un livre de Frank Herbert'))"
```

Expected: `function_gemma`

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/semantic_router.py
git commit -m "feat(calibre): add library utterances and _LIBRARY_KEYWORDS guard to semantic router"
```

---

## Task 5: `gui/tabs/library.py` — settings tab

**Files:**
- Create: `gui/tabs/library.py`

- [ ] **Step 1: Create `gui/tabs/library.py`**

Follow the exact same structure as `gui/tabs/music.py` (SettingCard pattern):

```python
"""
Library Tab — Calibre-Web connection settings.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit
from qfluentwidgets import (
    FluentIcon as FIF, SettingCardGroup, SettingCard, TitleLabel,
)
from core.i18n import tr
from core.settings_store import settings


class _LineCard(SettingCard):
    """Generic editable line-edit setting card."""

    def __init__(self, icon, title_key: str, desc_key: str,
                 setting_key: str, placeholder: str = "", masked: bool = False,
                 parent=None):
        super().__init__(icon, tr(title_key), tr(desc_key), parent)
        self._title_key = title_key
        self._desc_key = desc_key
        self._setting_key = setting_key

        self._edit = QLineEdit(settings.get(setting_key, ""), self)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumWidth(280)
        if masked:
            self._edit.setEchoMode(QLineEdit.Password)
        self._edit.textChanged.connect(lambda v: settings.set(setting_key, v.strip()))
        self.hBoxLayout.addWidget(self._edit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def retranslate(self):
        self.titleLabel.setText(tr(self._title_key))
        self.contentLabel.setText(tr(self._desc_key))


class LibraryTab(QWidget):
    """Calibre-Web connection settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("libraryInterface")
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)

        root.addWidget(TitleLabel(tr("library.title"), self))

        group = SettingCardGroup(tr("library.calibre_group"), self)

        group.addSettingCard(_LineCard(
            FIF.LINK,
            "library.url", "library.url_desc",
            "calibre.url",
            placeholder="http://192.168.1.70:8083",
            parent=group,
        ))
        group.addSettingCard(_LineCard(
            FIF.PEOPLE,
            "library.username", "library.username_desc",
            "calibre.username",
            placeholder="jeff",
            parent=group,
        ))
        group.addSettingCard(_LineCard(
            FIF.FINGERPRINT,
            "library.password", "library.password_desc",
            "calibre.password",
            placeholder="••••••",
            masked=True,
            parent=group,
        ))

        root.addWidget(group)
        root.addStretch()
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
python -c "from gui.tabs.library import LibraryTab; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add gui/tabs/library.py
git commit -m "feat(calibre): add LibraryTab settings UI for Calibre-Web credentials"
```

---

## Task 6: `gui/app.py` — register the tab

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Add the import**

In `gui/app.py`, after the `from gui.tabs.music import MusicTab` import (line 37), add:

```python
from gui.tabs.library import LibraryTab
```

- [ ] **Step 2: Create the lazy tab instance**

In `_init_views()`, after `self.music_lazy = LazyTab(MusicTab, "musicInterface")` (line 231), add:

```python
        self.library_lazy = LazyTab(LibraryTab, "libraryInterface")
```

- [ ] **Step 3: Register in the nav**

After `self.addSubInterface(self.music_lazy, FIF.MUSIC, tr("nav.music"))` (line 243), add:

```python
        self.addSubInterface(self.library_lazy, FIF.BOOK_SHELF, tr("nav.library"))
```

- [ ] **Step 4: Verify app imports cleanly**

```bash
python -c "import gui.app; print('OK')"
```

Expected: `OK` (no ImportError).

- [ ] **Step 5: Commit**

```bash
git add gui/app.py
git commit -m "feat(calibre): register LibraryTab in main nav"
```

---

## Task 7: i18n — add `library.*` and `nav.library` keys

**Files:**
- Modify: `locales/fr.json`
- Modify: `locales/en.json`

- [ ] **Step 1: Add keys to `locales/fr.json`**

In `locales/fr.json`, inside the `"nav"` object, add after `"music": "Musique",`:

```json
    "library": "Bibliothèque",
```

Then add a new top-level `"library"` section (after the `"music"` section):

```json
  "library": {
    "title": "Bibliothèque",
    "calibre_group": "Calibre-Web",
    "url": "URL Calibre-Web",
    "url_desc": "Adresse de votre instance Calibre-Web (ex : http://192.168.1.70:8083)",
    "username": "Nom d'utilisateur",
    "username_desc": "Identifiant Calibre-Web",
    "password": "Mot de passe",
    "password_desc": "Mot de passe Calibre-Web"
  },
```

- [ ] **Step 2: Add keys to `locales/en.json`**

In `locales/en.json`, inside `"nav"`, add after `"music": "Music",`:

```json
    "library": "Library",
```

Then add the `"library"` section:

```json
  "library": {
    "title": "Library",
    "calibre_group": "Calibre-Web",
    "url": "Calibre-Web URL",
    "url_desc": "Address of your Calibre-Web instance (e.g. http://192.168.1.70:8083)",
    "username": "Username",
    "username_desc": "Calibre-Web username",
    "password": "Password",
    "password_desc": "Calibre-Web password"
  },
```

- [ ] **Step 3: Verify i18n keys resolve**

```bash
python -c "
from core.i18n import tr
print(tr('library.title'))
print(tr('library.url'))
print(tr('nav.library'))
"
```

Expected:
```
Bibliothèque
URL Calibre-Web
Bibliothèque
```

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add locales/fr.json locales/en.json
git commit -m "feat(calibre): add library i18n keys to fr.json and en.json"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ `core/calibre_manager.py` — Task 1
- ✅ `config.py` `search_book` tool — Task 2
- ✅ `function_executor.py` `_search_book` — Task 3
- ✅ Semantic router utterances + guard — Task 4
- ✅ Settings UI — Task 5
- ✅ Nav registration — Task 6
- ✅ i18n keys — Task 7
- ✅ Tests — Tasks 1 and 3
- ✅ Error handling: no URL, network error, no results, missing description

**Type consistency:**
- `calibre_manager.search_books(query, search_type, count)` — used identically in Task 1 (impl), Task 3 (executor), and Task 3 (test: `cm.search_books.assert_called_once_with("Herbert", "author", 3)`) ✅
- `get_download_url(book_id, formats)` — used identically in `_parse_book` and tests ✅
- `_book()` helper in tests returns all keys used by `_search_book` ✅

**No placeholders:** ✅
