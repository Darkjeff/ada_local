"""
core/documents/documents_search.py
Recherche FTS5 BM25 dans la base documentaire locale d'ADA Web.
"""
from __future__ import annotations

import json
from typing import Any


# ── Recherche FTS5 ─────────────────────────────────────────────────────────

def search_documents(
    query: str,
    limit: int | None = None,
    include_content: bool = True,
) -> list[dict]:
    """
    Recherche dans la base documentaire par FTS5 (BM25).
    Retourne une liste de résultats enrichis avec le doc parent.
    """
    from core.settings_store import settings
    from core.documents.documents_db import get_connection

    if limit is None:
        limit = int(settings.get("documents.max_context_chunks", 6))

    if not query or not query.strip():
        return []

    conn = get_connection()
    try:
        # bm25(document_chunks_fts, 2.0, 1.0) — poids heading > content
        rows = conn.execute(
            """
            SELECT
                fts.id       AS chunk_id,
                fts.document_id,
                fts.heading,
                fts.content,
                d.rel_path,
                d.title,
                d.tags,
                bm25(document_chunks_fts, 2.0, 1.0) AS score
            FROM document_chunks_fts fts
            JOIN documents d ON fts.document_id = d.id
            WHERE document_chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (_fts_query(query), limit),
        ).fetchall()

        results = []
        for row in rows:
            entry: dict[str, Any] = {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "heading": row["heading"],
                "rel_path": row["rel_path"],
                "title": row["title"],
                "tags": json.loads(row["tags"] or "[]"),
                "score": row["score"],
            }
            if include_content:
                entry["content"] = row["content"]
            results.append(entry)
        return results
    finally:
        conn.close()


def get_document(doc_id: str) -> dict | None:
    """Retourne un document avec tous ses chunks."""
    from core.documents.documents_db import get_connection

    conn = get_connection()
    try:
        doc = conn.execute(
            "SELECT * FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        if not doc:
            return None

        chunks = conn.execute(
            "SELECT * FROM document_chunks WHERE document_id=? ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()

        return {
            "id": doc["id"],
            "rel_path": doc["rel_path"],
            "title": doc["title"],
            "tags": json.loads(doc["tags"] or "[]"),
            "frontmatter": json.loads(doc["frontmatter"] or "{}"),
            "hash": doc["hash"],
            "size_bytes": doc["size_bytes"],
            "updated_at": doc["updated_at"],
            "chunks": [
                {
                    "id": c["id"],
                    "index": c["chunk_index"],
                    "heading": c["heading"],
                    "content": c["content"],
                    "token_estimate": c["token_estimate"],
                }
                for c in chunks
            ],
        }
    finally:
        conn.close()


def list_documents(
    offset: int = 0,
    limit: int = 50,
    tags: list[str] | None = None,
) -> list[dict]:
    """Liste les documents indexés."""
    from core.documents.documents_db import get_connection

    conn = get_connection()
    try:
        if tags:
            rows = conn.execute(
                """SELECT id, rel_path, title, tags, size_bytes, updated_at
                   FROM documents ORDER BY rel_path LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            # Filtrage post-query (tags stockés en JSON)
            results = []
            for row in rows:
                doc_tags = json.loads(row["tags"] or "[]")
                if any(t in doc_tags for t in tags):
                    results.append(dict(row))
            return results
        else:
            rows = conn.execute(
                """SELECT id, rel_path, title, tags, size_bytes, updated_at
                   FROM documents ORDER BY rel_path LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def stats() -> dict:
    """Retourne les statistiques de la base documentaire."""
    from core.documents.documents_db import get_connection

    conn = get_connection()
    try:
        n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        total_size = conn.execute("SELECT SUM(size_bytes) FROM documents").fetchone()[0] or 0
        last_update = conn.execute(
            "SELECT MAX(updated_at) FROM documents"
        ).fetchone()[0]
        return {
            "documents": n_docs,
            "chunks": n_chunks,
            "total_size_bytes": total_size,
            "last_update": last_update,
        }
    finally:
        conn.close()


def get_logs(limit: int = 100) -> list[dict]:
    """Retourne les derniers logs d'indexation."""
    from core.documents.documents_db import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT level, message, path, created_at
               FROM document_index_log ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_index() -> None:
    """Vide intégralement la base documentaire (ne touche pas aux sources)."""
    from core.documents.documents_db import get_connection

    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM document_index_log")
        conn.execute("DELETE FROM document_chunks")
        conn.execute("DELETE FROM documents")
    conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────

def _fts_query(query: str) -> str:
    """
    Construit une requête FTS5 robuste à partir d'une requête utilisateur libre.
    Chaque mot est mis en préfixe pour tolérer les mots partiels.
    """
    words = [w.strip() for w in query.split() if len(w.strip()) >= 2]
    if not words:
        return query
    # Quotes pour protéger les caractères spéciaux FTS5
    escaped = [f'"{w}"' for w in words]
    return " OR ".join(escaped)
