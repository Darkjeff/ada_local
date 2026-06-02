"""
skills_manager.py — CRUD, recherche cascade FTS5, maintenance
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .skills_db import get_connection

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────────────

MAX_SKILLS_IN_CONTEXT = 5
AUTO_PROMOTE_THRESHOLD = 2    # success_count >= 2 → priority 4 → 3
AUTO_ARCHIVE_DAYS = 30        # skills AUTO non utilisées depuis N jours
PROTECTED_PRIORITY = 3        # priorité ≤ 3 = protégé contre archivage auto


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────────────────────────────────────

def _build_fts_query(query: str) -> str:
    """Construit une requête FTS5 sûre depuis une chaîne libre."""
    # Séparer en tokens, ignorer les mots courts
    tokens = [t.strip('"') for t in query.split() if len(t) >= 2]
    if not tokens:
        return '""'
    # Échapper les guillemets doubles dans les tokens
    safe = [f'"{t.replace(chr(34), "")}"' for t in tokens]
    return " OR ".join(safe)


def _fts_search(query: str, domain: Optional[str], status: str = "active", limit: int = 5) -> list[dict]:
    """Recherche FTS5 avec filtre domaine + status."""
    conn = get_connection()
    try:
        fts_q = _build_fts_query(query)
        if domain and domain not in ("core", "global", "all"):
            rows = conn.execute(
                """SELECT s.*, bm25(skills_fts) AS score
                   FROM skills_fts
                   JOIN skills s ON skills_fts.id = s.id
                   WHERE skills_fts MATCH ? AND s.status = ? AND (s.domain = ? OR s.domain = 'core')
                   ORDER BY s.priority ASC, score ASC
                   LIMIT ?""",
                (fts_q, status, domain, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT s.*, bm25(skills_fts) AS score
                   FROM skills_fts
                   JOIN skills s ON skills_fts.id = s.id
                   WHERE skills_fts MATCH ? AND s.status = ?
                   ORDER BY s.priority ASC, score ASC
                   LIMIT ?""",
                (fts_q, status, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("[Skills] FTS search error: %s", e)
        return []
    finally:
        conn.close()


def _fetch_all_active(domain: Optional[str], limit: int = MAX_SKILLS_IN_CONTEXT) -> list[dict]:
    """Fallback : retourne les skills actives par priorité."""
    conn = get_connection()
    try:
        if domain and domain not in ("core", "global", "all"):
            rows = conn.execute(
                """SELECT * FROM skills WHERE status = 'active'
                   AND (domain = ? OR domain = 'core')
                   ORDER BY priority ASC, usage_count DESC LIMIT ?""",
                (domain, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skills WHERE status = 'active' ORDER BY priority ASC, usage_count DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────────

def search_skills(
    query: str,
    active_domain: Optional[str] = None,
    limit: int = MAX_SKILLS_IN_CONTEXT,
) -> list[dict]:
    """
    Recherche à 4 niveaux :
    1. FTS5 sur domaine actif
    2. FTS5 global (domaine=None)
    3. Skills de priorité ≤ 3 (toujours présentes)
    4. Fallback : toutes actives par priorité
    """
    results: list[dict] = []
    seen: set = set()

    def _add(rows: list[dict]) -> None:
        for r in rows:
            if r["id"] not in seen and len(results) < limit:
                seen.add(r["id"])
                results.append(r)

    # Niveau 1 — FTS domaine
    if query:
        _add(_fts_search(query, active_domain, limit=limit))

    # Niveau 2 — FTS global (si pas assez)
    if query and len(results) < limit:
        _add(_fts_search(query, None, limit=limit))

    # Niveau 3 — skills protégées (priority ≤ 3) toujours incluses
    conn = get_connection()
    try:
        protected = conn.execute(
            "SELECT * FROM skills WHERE status='active' AND priority <= ? ORDER BY priority ASC",
            (PROTECTED_PRIORITY,),
        ).fetchall()
        _add([dict(r) for r in protected])
    finally:
        conn.close()

    # Niveau 4 — fallback par priorité
    if not results:
        _add(_fetch_all_active(active_domain, limit=limit))

    return results[:limit]


def search_archive(query: str, limit: int = 5) -> list[dict]:
    """Recherche dans les skills archivées."""
    if not query:
        return []
    return _fts_search(query, domain=None, status="archived", limit=limit)


def get_skill(skill_id: str) -> Optional[dict]:
    """Récupère une skill par ID."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_skills(status: str = "active", domain: Optional[str] = None) -> list[dict]:
    """Liste toutes les skills selon status/domaine."""
    conn = get_connection()
    try:
        if domain:
            rows = conn.execute(
                "SELECT * FROM skills WHERE status=? AND domain=? ORDER BY priority ASC, name ASC",
                (status, domain),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skills WHERE status=? ORDER BY priority ASC, domain ASC, name ASC",
                (status,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_skill(
    name: str,
    content: str,
    domain: str = "core",
    source: str = "manual",
    summary: str = "",
    priority: int = 5,
    skill_id: Optional[str] = None,
) -> str:
    """Crée ou met à jour une skill. Retourne l'ID."""
    if skill_id is None:
        skill_id = str(uuid.uuid4())[:8]

    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE skills SET name=?, content=?, summary=?, domain=?, priority=?,
                   updated_at=datetime('now') WHERE id=?""",
                (name, content, summary, domain, priority, skill_id),
            )
        else:
            conn.execute(
                """INSERT INTO skills (id, name, domain, source, content, summary, priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, name, domain, source, content, summary, priority),
            )
        conn.commit()
        _history(conn, skill_id, "save", f"source={source}")
    finally:
        conn.close()

    return skill_id


def delete_skill(skill_id: str) -> bool:
    """Supprime une skill (refusé si priority ≤ PROTECTED_PRIORITY)."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT priority FROM skills WHERE id=?", (skill_id,)).fetchone()
        if not row:
            return False
        if row["priority"] <= PROTECTED_PRIORITY:
            logger.warning("[Skills] Suppression refusée : skill protégée %s (priority=%d)", skill_id, row["priority"])
            return False
        conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def archive_skill(skill_id: str) -> bool:
    """Archive une skill."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE skills SET status='archived', updated_at=datetime('now') WHERE id=?",
            (skill_id,),
        )
        conn.commit()
        _history(conn, skill_id, "archive")
        return True
    finally:
        conn.close()


def restore_skill(skill_id: str) -> bool:
    """Restaure une skill archivée."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE skills SET status='active', updated_at=datetime('now') WHERE id=?",
            (skill_id,),
        )
        conn.commit()
        _history(conn, skill_id, "restore")
        return True
    finally:
        conn.close()


def promote_skill(skill_id: str, new_priority: Optional[int] = None) -> bool:
    """Monte la priorité de 1 cran (ou fixe new_priority)."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT priority FROM skills WHERE id=?", (skill_id,)).fetchone()
        if not row:
            return False
        target = max(1, (new_priority if new_priority is not None else row["priority"] - 1))
        conn.execute(
            "UPDATE skills SET priority=?, updated_at=datetime('now') WHERE id=?",
            (target, skill_id),
        )
        conn.commit()
        _history(conn, skill_id, "promote", f"priority={target}")
        return True
    finally:
        conn.close()


def set_priority(skill_id: str, priority: int) -> bool:
    """Définit explicitement la priorité."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE skills SET priority=?, updated_at=datetime('now') WHERE id=?",
            (max(1, min(10, priority)), skill_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def record_success(skill_id: str) -> None:
    """Incrémente success_count + auto-promotion si threshold atteint."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE skills SET success_count=success_count+1, usage_count=usage_count+1,
               last_used=datetime('now'), updated_at=datetime('now') WHERE id=?""",
            (skill_id,),
        )
        # Auto-promotion
        row = conn.execute(
            "SELECT priority, success_count FROM skills WHERE id=?",
            (skill_id,),
        ).fetchone()
        if row and row["success_count"] >= AUTO_PROMOTE_THRESHOLD and row["priority"] == 4:
            conn.execute(
                "UPDATE skills SET priority=3, updated_at=datetime('now') WHERE id=?",
                (skill_id,),
            )
            _history(conn, skill_id, "auto_promote", "priority=3")
        conn.commit()
    finally:
        conn.close()


def run_maintenance() -> dict:
    """
    Maintenance automatique :
    - Archive les skills AUTO non utilisées depuis AUTO_ARCHIVE_DAYS
    - Retourne un résumé
    """
    conn = get_connection()
    archived = 0
    try:
        rows = conn.execute(
            f"""SELECT id FROM skills
                WHERE source='auto' AND status='active' AND priority > {PROTECTED_PRIORITY}
                AND (last_used IS NULL OR last_used < datetime('now', '-{AUTO_ARCHIVE_DAYS} days'))
                AND (updated_at < datetime('now', '-{AUTO_ARCHIVE_DAYS} days'))""",
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE skills SET status='archived', updated_at=datetime('now') WHERE id=?",
                (row["id"],),
            )
            archived += 1
        conn.commit()
    finally:
        conn.close()

    logger.info("[Skills] Maintenance : %d skill(s) archivée(s)", archived)
    return {"archived": archived}


# ──────────────────────────────────────────────────────────────────────────────
# Historique interne
# ──────────────────────────────────────────────────────────────────────────────

def _history(conn, skill_id: str, action: str, detail: str = "") -> None:
    try:
        conn.execute(
            "INSERT INTO skills_history (skill_id, action, detail) VALUES (?, ?, ?)",
            (skill_id, action, detail),
        )
    except Exception:
        pass
