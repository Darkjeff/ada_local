# Calibre Library Integration Design

## Goal

Enable ADA to search the personal ebook library (Calibre-Web on Docker/Ubuntu, library on NAS) by title, author, or genre/tag via voice and Telegram, returning full book details and a download link.

## Architecture

One new layer added to the existing ADA pipeline:

1. **`core/calibre_manager.py`** — Calibre-Web REST API client
2. **`config.py`** — 1 new LLM tool definition (`search_book`)
3. **`core/function_executor.py`** — 1 new handler (`_search_book`)
4. **`core/semantic_router.py`** — book utterances added to `function_gemma` route
5. **`gui/tabs/library.py`** — new settings tab (url, username, password)
6. **`locales/fr.json` + `locales/en.json`** — i18n keys

The semantic router detects book queries → routes to `function_gemma` → LLM calls `search_book` → executor calls `calibre_manager` → result injected into LLM context → natural French response via voice and Telegram.

---

## Section 1 — `core/calibre_manager.py`

Thin Calibre-Web REST API client. Reads credentials from settings:
- `calibre.url` (e.g. `http://192.168.1.70:8083`)
- `calibre.username`
- `calibre.password`

### Public interface

```python
def search_books(self, query: str, search_type: str = "all", count: int = 3) -> list[dict]:
    """
    GET /api/search?query={query}&limit={count}
    search_type: "title" | "author" | "tags" | "all"
    Returns list of dicts with keys:
      id, title, author, year, formats (list[str]), description, download_url
    Returns [] on error or no results.
    """

def get_book_details(self, book_id: int) -> Optional[dict]:
    """
    GET /api/books/{id}
    Returns full book dict or None on error.
    """

def get_download_url(self, book_id: int, fmt: str = "epub") -> str:
    """
    Returns: {base_url}/api/books/{id}/download/{fmt}
    Format priority if fmt not specified: epub > pdf > mobi
    """
```

### API endpoint note

Calibre-Web's REST API endpoint for search is `/api/search?query=...` in recent versions (0.6.20+). If this returns 404, fall back to `/api/books?search=...`. Both are tried in `_get_search_endpoint()` during the first call and the result is cached.

### Error handling

- Calibre-Web unreachable → `[]` + `print("[Calibre] Unreachable: ...")`
- Auth failure (401/403) → `[]` + `print("[Calibre] Auth failed")`
- Book has no description → `description: ""`
- Book has no formats → `formats: []`, `download_url: ""`
- `calibre.url` not configured → `[]` immediately (no network call)

### Singleton

```python
calibre_manager = CalibreManager()
```

---

## Section 2 — LLM Tool (`config.py`)

One new entry in the `FUNCTIONS` list:

```json
{
  "name": "search_book",
  "description": "Search for a book in the personal library by title, author, or genre/tag",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search terms (title, author name, or genre/tag)"
      },
      "search_type": {
        "type": "string",
        "enum": ["title", "author", "tags", "all"],
        "description": "Which field to search (default: all)"
      }
    },
    "required": ["query"]
  }
}
```

---

## Section 3 — `function_executor.py`

New handler `_search_book(params)` registered in `execute()`:

**Logic:**
1. Read `query` from params (required). Read `search_type` (default `"all"`).
2. Call `calibre_manager.search_books(query, search_type, count=3)`.
3. If empty → return `{"success": False, "message": "Aucun livre trouvé pour « {query} ».", "data": None}`
4. For each result, build a formatted block:
   ```
   « {title} » — {author} ({year})
   Formats : {epub, pdf, ...}
   {description[:200]}...
   Télécharger : {download_url}
   ```
5. Return `{"success": True, "message": <formatted results joined by \n\n>, "data": results}`

The formatted message is injected as a hint in the LLM follow-up so it responds naturally in French.

---

## Section 4 — Semantic Router (`core/semantic_router.py`)

Add book utterances to `_ROUTES["function_gemma"]`:

```python
# Book search
"cherche un livre", "trouve un livre", "tu as un livre",
"cherche dans ma bibliothèque", "dans ma bibliothèque",
"un livre de", "un livre sur", "un roman de",
"as-tu un livre", "est-ce que tu as un",
"find a book", "search for a book", "do you have a book by",
# Genre/tag
"un livre de science-fiction", "un polar", "un roman historique",
"de la fantasy", "un essai sur", "un manga",
```

Add a `_LIBRARY_KEYWORDS` regex guard (same pattern as `_MUSIC_KEYWORDS`) to prevent semantic drift:

```python
_LIBRARY_KEYWORDS = re.compile(
    r"\b(livre|roman|bouquin|biblioth[eè]que|auteur|epub|pdf|calibre|"
    r"book|library|novel|author|genre|fantasy|polar|manga)\b",
    re.IGNORECASE,
)
```

Update `get_route()` order: vision → music → **library** → function → embedding.

---

## Section 5 — Settings UI (`gui/tabs/library.py`)

New tab following the same pattern as `gui/tabs/music.py`:

- `SettingCardGroup` "Calibre-Web" with 3 `LineEditSettingCard` fields:
  - `calibre.url` — "URL Calibre-Web" / "Calibre-Web URL"
  - `calibre.username` — "Nom d'utilisateur" / "Username"
  - `calibre.password` — "Mot de passe" / "Password" (masked input)

The tab must be registered in the main window nav list.

---

## Section 6 — i18n

Add to `locales/fr.json` and `locales/en.json`:

```json
// fr.json
"library.title": "Bibliothèque",
"library.calibre_group": "Calibre-Web",
"library.url": "URL Calibre-Web",
"library.url_desc": "Adresse de votre instance Calibre-Web",
"library.username": "Nom d'utilisateur",
"library.username_desc": "Identifiant Calibre-Web",
"library.password": "Mot de passe",
"library.password_desc": "Mot de passe Calibre-Web"

// en.json
"library.title": "Library",
"library.calibre_group": "Calibre-Web",
"library.url": "Calibre-Web URL",
"library.url_desc": "Address of your Calibre-Web instance",
"library.username": "Username",
"library.username_desc": "Calibre-Web username",
"library.password": "Password",
"library.password_desc": "Calibre-Web password"
```

---

## Error Handling Summary

| Situation | Message retourné |
|-----------|-----------------|
| `calibre.url` non configuré | `"Calibre-Web n'est pas configuré. Configure l'URL dans les paramètres."` |
| Service inaccessible | `"Calibre-Web est inaccessible."` |
| Auth échouée | `"Impossible de se connecter à Calibre-Web (identifiants incorrects)."` |
| Aucun résultat | `"Aucun livre trouvé pour « {query} »."` |

---

## Testing

- `tests/test_calibre_manager.py` — mock HTTP responses for search, detail, download URL, error cases
- `tests/test_calibre_executor.py` — mock calibre_manager calls, verify formatted message output

No integration test against real Calibre-Web needed (mocked at HTTP level).

---

## Files Modified / Created

| File | Action |
|------|--------|
| `core/calibre_manager.py` | Create |
| `core/function_executor.py` | Extend (1 new handler) |
| `config.py` | Extend (1 new tool definition) |
| `core/semantic_router.py` | Extend (library utterances + keyword guard) |
| `gui/tabs/library.py` | Create |
| `locales/fr.json` | Extend |
| `locales/en.json` | Extend |
| `tests/test_calibre_manager.py` | Create |
| `tests/test_calibre_executor.py` | Create |
