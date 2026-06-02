"""
web/router_documents.py
API FastAPI d'administration de la base documentaire RAG locale d'ADA Web.

Routes :
    GET  /api/documents/status      — état du module (montage, stats)
    GET  /api/documents             — liste des documents indexés
    GET  /api/documents/{id}        — détail d'un document
    POST /api/documents/search      — recherche FTS5
    POST /api/documents/reindex     — lancer une réindexation
    GET  /api/documents/logs        — logs d'indexation
    DELETE /api/documents/index     — vider l'index (pas les sources)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── Modèles Pydantic ───────────────────────────────────────────────────────

class _SearchRequest(BaseModel):
    query: str
    limit: int = 10


class _ReindexRequest(BaseModel):
    force: bool = False


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status() -> dict:
    """Retourne l'état du module documents (montage + statistiques)."""
    from core.settings_store import settings
    from core.documents.documents_search import stats

    enabled: bool = bool(settings.get("documents.enabled", False))
    root_path: str = (settings.get("documents.root_path") or "").strip()

    mount_info: dict = {}
    if enabled and root_path:
        from core.documents.documents_mount import get_mount_status
        mount_info = get_mount_status(
            root_path,
            expected_mount_path=settings.get("documents.expected_mount_path", ""),
            expected_device_hint=settings.get("documents.expected_device_hint", ""),
        )

    try:
        db_stats = stats()
    except Exception as e:
        db_stats = {"error": str(e)}

    return {
        "enabled": enabled,
        "root_path": root_path,
        "mount": mount_info,
        "stats": db_stats,
        "config": {
            "chunk_size": settings.get("documents.chunk_size", 1200),
            "chunk_overlap": settings.get("documents.chunk_overlap", 200),
            "max_context_chunks": settings.get("documents.max_context_chunks", 6),
            "max_context_chars": settings.get("documents.max_context_chars", 9000),
            "extensions": settings.get("documents.extensions", [".md"]),
            "auto_index_on_startup": settings.get("documents.auto_index_on_startup", True),
            "require_mount": settings.get("documents.require_mount", True),
        },
    }


@router.get("")
def list_docs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Liste les documents indexés."""
    from core.documents.documents_search import list_documents, stats

    docs = list_documents(offset=offset, limit=limit)
    total = stats().get("documents", 0)
    return {"total": total, "offset": offset, "limit": limit, "documents": docs}


@router.get("/logs")
def get_logs(limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Retourne les derniers logs d'indexation."""
    from core.documents.documents_search import get_logs
    return {"logs": get_logs(limit=limit)}


@router.get("/{doc_id}")
def get_doc(doc_id: str) -> dict:
    """Retourne le détail complet d'un document."""
    from core.documents.documents_search import get_document
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return doc


@router.post("/search")
def search(body: _SearchRequest) -> dict:
    """Recherche FTS5 dans la base documentaire."""
    from core.settings_store import settings

    if not settings.get("documents.enabled", False):
        raise HTTPException(status_code=503, detail="Module documents désactivé")

    from core.documents.documents_search import search_documents
    results = search_documents(body.query, limit=body.limit)
    return {"query": body.query, "results": results}


@router.post("/reindex")
def reindex(body: _ReindexRequest) -> dict:
    """Lance une réindexation complète (synchrone)."""
    from core.settings_store import settings

    if not settings.get("documents.enabled", False):
        raise HTTPException(status_code=503, detail="Module documents désactivé")

    root_path: str = (settings.get("documents.root_path") or "").strip()
    if not root_path:
        raise HTTPException(status_code=400, detail="root_path non configuré")

    from core.documents.documents_indexer import index_all
    result = index_all(force=body.force)
    return {"ok": True, "result": result}


@router.delete("/index")
def delete_index() -> dict:
    """Vide l'index SQLite sans toucher aux fichiers sources."""
    from core.documents.documents_search import delete_index as _delete
    _delete()
    return {"ok": True, "message": "Index vidé"}
