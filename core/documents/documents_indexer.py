"""
core/documents/documents_indexer.py
Indexation incrémentale de fichiers Markdown dans la base documentaire FTS5.
"""
from __future__ import annotations

import hashlib
import json
import re
import time as _time
import uuid
from pathlib import Path
from typing import Generator


def _radar(**kw) -> None:
    """Wraper non-bloquant pour emit_event Radar."""
    try:
        from web.radar.events import emit_event
        emit_event(**kw)
    except Exception:
        pass


# ── Chunk Markdown ─────────────────────────────────────────────────────────

def chunk_markdown(
    content: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[dict]:
    """
    Découpe un document Markdown en chunks en respectant les titres.
    Retourne [{"heading": str, "content": str, "token_estimate": int}].
    """
    # Séparer par titres Markdown (#, ##, ###)
    heading_re = re.compile(r"^(#{1,3} .+)$", re.MULTILINE)
    parts = heading_re.split(content)

    chunks: list[dict] = []
    current_heading = ""
    current_buf = ""

    def _flush(heading: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if len(text) <= chunk_size:
            chunks.append({
                "heading": heading,
                "content": text,
                "token_estimate": max(1, len(text) // 4),
            })
        else:
            # Découper par paragraphes
            paragraphs = re.split(r"\n\n+", text)
            sub_buf = ""
            for para in paragraphs:
                if len(sub_buf) + len(para) + 2 > chunk_size and sub_buf:
                    chunks.append({
                        "heading": heading,
                        "content": sub_buf.strip(),
                        "token_estimate": max(1, len(sub_buf) // 4),
                    })
                    # overlap : garder la fin du buffer précédent
                    sub_buf = sub_buf[-overlap:] if overlap else ""
                sub_buf += "\n\n" + para if sub_buf else para
            if sub_buf.strip():
                chunks.append({
                    "heading": heading,
                    "content": sub_buf.strip(),
                    "token_estimate": max(1, len(sub_buf) // 4),
                })

    i = 0
    while i < len(parts):
        part = parts[i]
        if heading_re.match(part):
            _flush(current_heading, current_buf)
            current_heading = part.strip()
            current_buf = ""
        else:
            current_buf += part
        i += 1

    _flush(current_heading, current_buf)
    return [c for c in chunks if c["content"]]


# ── Frontmatter parser ─────────────────────────────────────────────────────

_FM_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Extrait le frontmatter YAML simple (sans dépendance yaml).
    Retourne (meta_dict, body).
    """
    m = _FM_RE.match(text)
    if not m:
        return {}, text

    raw_meta = m.group(1)
    body = m.group(2)
    meta: dict = {}

    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            # Liste simple : [a, b, c]
            items = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
            meta[key] = items
        else:
            meta[key] = val.strip("\"'")

    return meta, body


def _extract_title(meta: dict, body: str, filepath: Path) -> str:
    if meta.get("title"):
        return str(meta["title"])
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return filepath.stem.replace("_", " ").replace("-", " ").title()


# ── Indexation ─────────────────────────────────────────────────────────────

def index_all(force: bool = False) -> dict:
    """
    Scanne root_path et indexe tous les fichiers Markdown.
    Si force=False, ne réindexe que les fichiers nouveaux ou modifiés.
    """
    from core.settings_store import settings

    result = {"indexed": 0, "updated": 0, "skipped": 0, "deleted": 0, "errors": 0}

    if not settings.get("documents.enabled", True):
        return result

    root_path_str = (settings.get("documents.root_path") or "").strip()
    if not root_path_str:
        print("[Documents] root_path non configuré — indexation ignorée")
        return result

    root_path = Path(root_path_str)

    # Vérification montage
    if settings.get("documents.require_mount", True):
        from core.documents.documents_mount import get_mount_status
        mount = get_mount_status(
            root_path_str,
            expected_mount_path=settings.get("documents.expected_mount_path", ""),
            expected_device_hint=settings.get("documents.expected_device_hint", ""),
        )
        if not mount["ok"]:
            print(f"[Documents] Montage invalide : {mount['reason']} — indexation annulée")
            return result

    if not root_path.is_dir():
        print(f"[Documents] root_path introuvable : {root_path}")
        return result

    extensions: list[str] = settings.get("documents.extensions", [".md"])
    ignore_dirs: list[str] = settings.get(
        "documents.ignore_dirs",
        [".git", "node_modules", "__pycache__", ".venv", "venv"],
    )
    chunk_size: int = int(settings.get("documents.chunk_size", 1200))
    chunk_overlap: int = int(settings.get("documents.chunk_overlap", 200))
    max_size_bytes: int = 5 * 1024 * 1024  # 5 Mo

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _radar(type="job.started", level="info", module="documents.indexer",
           job_id=job_id, message="Indexation documentaire démarrée",
           metadata={"force": force, "root": root_path_str})
    _job_start = _time.perf_counter()

    for filepath in _walk(root_path, extensions, ignore_dirs):
        try:
            r = index_file(
                filepath,
                root_path,
                force=force,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                max_size_bytes=max_size_bytes,
            )
            if r == "indexed":
                result["indexed"] += 1
            elif r == "updated":
                result["updated"] += 1
            elif r == "skipped":
                result["skipped"] += 1
        except Exception as e:
            result["errors"] += 1
            print(f"[Documents] Erreur {filepath}: {e}")

    result["deleted"] = remove_missing_files()

    total = result["indexed"] + result["updated"]
    _radar(type="job.completed", level="info", module="documents.indexer",
           job_id=job_id, message="Indexation terminée",
           duration_ms=int((_time.perf_counter() - _job_start) * 1000),
           metadata={**result})
    print(
        f"[Documents] Indexation terminée — "
        f"{total} traités, {result['skipped']} ignorés, "
        f"{result['deleted']} supprimés, {result['errors']} erreurs"
    )
    return result


def index_file(
    path: Path,
    root_path: Path,
    force: bool = False,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    max_size_bytes: int = 5 * 1024 * 1024,
) -> str:
    """
    Indexe un fichier Markdown.
    Retourne "indexed" | "updated" | "skipped".
    """
    from core.documents.documents_db import get_connection, _log

    # Symlink hors du root_path → refus
    real = path.resolve()
    try:
        real.relative_to(root_path.resolve())
    except ValueError:
        return "skipped"

    size = path.stat().st_size
    mtime = path.stat().st_mtime

    if size > max_size_bytes:
        return "skipped"

    text = path.read_text(encoding="utf-8", errors="replace")
    file_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    rel_path = str(path.relative_to(root_path)).replace("\\", "/")

    conn = get_connection()
    with conn:
        row = conn.execute(
            "SELECT id, hash FROM documents WHERE path=?", (str(path),)
        ).fetchone()

        # Vérifier si réindexation nécessaire
        if row and row["hash"] == file_hash and not force:
            conn.close()
            return "skipped"

        meta, body = _parse_frontmatter(text)
        title = _extract_title(meta, body, path)
        tags_json = json.dumps(meta.get("tags", []))
        fm_json = json.dumps({k: v for k, v in meta.items() if k != "tags"})

        is_update = row is not None
        doc_id = row["id"] if row else str(uuid.uuid4())

        _radar(type="document.parsing.started", level="info", module="documents.indexer",
               document_id=doc_id, message=f"Parsing: {rel_path}",
               metadata={"path": rel_path, "size_bytes": size})
        _t_parse = _time.perf_counter()

        if is_update:
            # Supprimer les anciens chunks (les triggers FTS s'en chargent)
            conn.execute("DELETE FROM document_chunks WHERE document_id=?", (doc_id,))
            conn.execute(
                """UPDATE documents SET title=?, hash=?, size_bytes=?, mtime=?,
                   tags=?, frontmatter=?, updated_at=datetime('now')
                   WHERE id=?""",
                (title, file_hash, size, mtime, tags_json, fm_json, doc_id),
            )
        else:
            conn.execute(
                """INSERT INTO documents(id,path,rel_path,title,hash,size_bytes,
                   mtime,extension,tags,frontmatter)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc_id, str(path), rel_path, title,
                    file_hash, size, mtime,
                    path.suffix.lower(), tags_json, fm_json,
                ),
            )

        # Insérer les nouveaux chunks
        _t_chunk = _time.perf_counter()
        chunks = chunk_markdown(body, chunk_size=chunk_size, overlap=chunk_overlap)
        for idx, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO document_chunks(id,document_id,chunk_index,heading,
                   content,token_estimate) VALUES(?,?,?,?,?,?)""",
                (
                    chunk_id, doc_id, idx,
                    chunk["heading"], chunk["content"], chunk["token_estimate"],
                ),
            )

        _log(conn, "INFO", f"{'Mis à jour' if is_update else 'Indexé'} : {rel_path} ({len(chunks)} chunks)", str(path))

    conn.close()

    action = "updated" if is_update else "indexed"
    _radar(type=f"document.indexing.completed", level="info", module="documents.indexer",
           document_id=doc_id,
           duration_ms=int((_time.perf_counter() - _t_parse) * 1000),
           message=f"{action.capitalize()}: {rel_path}",
           metadata={"chunks": len(chunks), "size_bytes": size, "action": action,
                     "chunk_ms": int((_time.perf_counter() - _t_chunk) * 1000)})
    return action


def remove_missing_files() -> int:
    """Supprime les documents dont le fichier source n'existe plus."""
    from core.documents.documents_db import get_connection

    conn = get_connection()
    removed = 0
    with conn:
        rows = conn.execute("SELECT id, path FROM documents").fetchall()
        for row in rows:
            if not Path(row["path"]).exists():
                conn.execute("DELETE FROM documents WHERE id=?", (row["id"],))
                removed += 1
    conn.close()
    return removed


def _walk(
    root: Path,
    extensions: list[str],
    ignore_dirs: list[str],
) -> Generator[Path, None, None]:
    """Parcourt récursivement root en ignorant certains dossiers."""
    for item in sorted(root.iterdir()):
        if item.is_symlink():
            continue
        if item.is_dir():
            if item.name not in ignore_dirs:
                yield from _walk(item, extensions, ignore_dirs)
        elif item.is_file() and item.suffix.lower() in extensions:
            yield item
