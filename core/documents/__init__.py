# core/documents — Base documentaire RAG locale pour ADA Web.
# Séparée des skills (règles procédurales) — dédiée à la documentation projet.
from core.documents.documents_db import init_db
from core.documents.documents_search import search_documents, stats, list_documents
from core.documents.documents_indexer import index_all

__all__ = ["init_db", "search_documents", "stats", "list_documents", "index_all"]
