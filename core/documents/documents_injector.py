"""
core/documents/documents_injector.py
Injection contrôlée des chunks documentaires dans le pipeline de chat.
"""
from __future__ import annotations


def inject_documentation(
    messages: list[dict],
    query: str,
    context_id: str | None = None,
) -> tuple[list[dict], dict]:
    """
    Recherche les chunks pertinents et les injecte dans le system prompt.

    Retourne (messages_modifiés, meta) où meta = {
        "injected": bool,
        "n_chunks": int,
        "total_chars": int,
        "sources": [str, ...],
    }
    """
    from core.settings_store import settings

    meta = {"injected": False, "n_chunks": 0, "total_chars": 0, "sources": []}

    if not settings.get("documents.enabled", False):
        return messages, meta

    min_query_len: int = int(settings.get("documents.min_query_length", 3))
    if not query or len(query.strip()) < min_query_len:
        return messages, meta

    max_chunks: int = int(settings.get("documents.max_context_chunks", 6))
    max_chars: int = int(settings.get("documents.max_context_chars", 9000))
    include_sources: bool = bool(settings.get("documents.include_sources_in_answer", True))

    from core.documents.documents_search import search_documents
    results = search_documents(query, limit=max_chunks)
    if not results:
        return messages, meta

    # Construire le bloc documentaire
    blocks: list[str] = []
    total_chars = 0
    sources: list[str] = []

    for chunk in results:
        heading = chunk.get("heading", "")
        content = chunk.get("content", "")
        rel_path = chunk.get("rel_path", "")
        title = chunk.get("title", rel_path)

        header = f"### {heading}" if heading else f"### {title}"
        block = f"{header}\n{content}\n(source: {rel_path})"

        if total_chars + len(block) > max_chars:
            break

        blocks.append(block)
        total_chars += len(block)
        if rel_path not in sources:
            sources.append(rel_path)

    if not blocks:
        return messages, meta

    sep = "\n\n---\n\n"
    doc_context = (
        "## Documentation de référence\n"
        "⚠ INSTRUCTION OBLIGATOIRE : tu DOIS citer les sources utilisées "
        "à la fin de ta réponse sous la forme \"📎 Sources : <nom_fichier>\".\n\n"
        + sep.join(blocks)
    )
    if include_sources:
        doc_context += (
            f"\n\n📎 Sources disponibles (à citer obligatoirement dans ta réponse) : {', '.join(sources)}"
        )

    # Injecter dans le system prompt (messages[0])
    if messages and messages[0]["role"] == "system":
        messages[0] = {
            "role": "system",
            "content": messages[0]["content"] + "\n\n" + doc_context,
        }
    else:
        messages.insert(0, {"role": "system", "content": doc_context})

    meta["injected"] = True
    meta["n_chunks"] = len(blocks)
    meta["total_chars"] = total_chars
    meta["sources"] = sources

    return messages, meta
