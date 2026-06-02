"""
skills_db.py — SQLite FTS5 initialization and seeding
"""
import sqlite3
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Chemin vers la base de données (project_root/data/skills.db)
DB_PATH = Path(__file__).parent.parent.parent / "data" / "skills.db"

# ──────────────────────────────────────────────────────────────────────────────
# Connexion
# ──────────────────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Retourne une connexion avec row_factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ──────────────────────────────────────────────────────────────────────────────
# Initialisation du schéma
# ──────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    domain      TEXT NOT NULL DEFAULT 'core',
    source      TEXT NOT NULL DEFAULT 'manual',   -- 'seed' | 'manual' | 'auto'
    content     TEXT NOT NULL,
    summary     TEXT,
    priority    INTEGER NOT NULL DEFAULT 5,        -- 1 (always) → 10 (rare)
    status      TEXT NOT NULL DEFAULT 'active',   -- 'active' | 'archived'
    success_count INTEGER NOT NULL DEFAULT 0,
    usage_count   INTEGER NOT NULL DEFAULT 0,
    last_used   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
    id UNINDEXED,
    name,
    summary,
    content,
    tokenize = "unicode61"
);

CREATE TABLE IF NOT EXISTS skills_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT,
    ts          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Triggers de synchronisation FTS5
CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
    INSERT INTO skills_fts(id, name, summary, content)
    VALUES (new.id, new.name, COALESCE(new.summary, ''), new.content);
END;

CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills BEGIN
    DELETE FROM skills_fts WHERE id = old.id;
    INSERT INTO skills_fts(id, name, summary, content)
    VALUES (new.id, new.name, COALESCE(new.summary, ''), new.content);
END;

CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
    DELETE FROM skills_fts WHERE id = old.id;
END;

CREATE INDEX IF NOT EXISTS idx_skills_domain   ON skills(domain);
CREATE INDEX IF NOT EXISTS idx_skills_status   ON skills(status);
CREATE INDEX IF NOT EXISTS idx_skills_priority ON skills(priority);
CREATE INDEX IF NOT EXISTS idx_skills_source   ON skills(source);

-- Tables AutoSkills (traçabilité)
CREATE TABLE IF NOT EXISTS autoskill_observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        TEXT,
    session_id      TEXT NOT NULL,
    domain          TEXT,
    user_text       TEXT NOT NULL,
    assistant_text  TEXT NOT NULL,
    extracted_summary TEXT,
    confidence      REAL NOT NULL DEFAULT 0,
    action          TEXT NOT NULL, -- 'created' | 'updated' | 'skipped' | 'candidate'
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS autoskill_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    TEXT NOT NULL,
    session_id  TEXT,
    request_id  TEXT,
    feedback    TEXT NOT NULL, -- 'positive' | 'negative' | 'neutral'
    reason      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS autoskill_injections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    TEXT NOT NULL,
    session_id  TEXT,
    request_id  TEXT,
    query       TEXT NOT NULL,
    domain      TEXT,
    score       REAL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    """Crée les tables si elles n'existent pas encore."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        logger.info("[Skills] Base initialisée → %s", DB_PATH)
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Seeding depuis fichiers Markdown
# ──────────────────────────────────────────────────────────────────────────────

def _parse_seed_file(path: Path) -> Optional[dict]:
    """
    Parse un fichier Markdown seed.
    Frontmatter YAML minimal entre ---/---.
    Le reste est le contenu de la skill.
    """
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    content = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            header = parts[1]
            content = parts[2].strip()
            for line in header.splitlines():
                m = re.match(r'^(\w+):\s*(.+)$', line.strip())
                if m:
                    meta[m.group(1).lower()] = m.group(2).strip()

    # Inférer id/name depuis le nom de fichier si absent
    stem = path.stem
    skill_id = meta.get("id") or f"seed_{stem}"
    name     = meta.get("name") or stem.replace("_", " ").title()
    domain   = meta.get("domain") or path.parent.name  # parent dir = domain
    priority = int(meta.get("priority", 1))
    summary  = meta.get("summary") or ""

    if not content:
        return None

    return {
        "id": skill_id,
        "name": name,
        "domain": domain,
        "source": "seed",
        "content": content,
        "summary": summary,
        "priority": priority,
        "status": "active",
    }


def seed_from_files(seed_dir: Optional[Path] = None) -> int:
    """
    Charge les fichiers Markdown depuis seed_dir (idempotent).
    Crée ou met à jour si le contenu change.
    Retourne le nombre de skills insérées/mises à jour.
    """
    if seed_dir is None:
        seed_dir = Path(__file__).parent.parent.parent / "skills_seed"

    if not seed_dir.is_dir():
        logger.warning("[Skills] Répertoire seed introuvable : %s", seed_dir)
        return 0

    conn = get_connection()
    count = 0
    try:
        for md_file in sorted(seed_dir.rglob("*.md")):
            parsed = _parse_seed_file(md_file)
            if not parsed:
                continue

            existing = conn.execute(
                "SELECT id, content, priority FROM skills WHERE id = ?",
                (parsed["id"],)
            ).fetchone()

            if existing is None:
                conn.execute(
                    """INSERT INTO skills
                       (id, name, domain, source, content, summary, priority, status)
                       VALUES (:id, :name, :domain, :source, :content, :summary, :priority, :status)""",
                    parsed,
                )
                count += 1
            elif existing["content"] != parsed["content"]:
                # Mettre à jour si le contenu a changé (évolution des seed files)
                conn.execute(
                    """UPDATE skills SET content=:content, summary=:summary,
                       updated_at=datetime('now') WHERE id=:id""",
                    {"content": parsed["content"], "summary": parsed["summary"], "id": parsed["id"]},
                )
                count += 1

        conn.commit()
    finally:
        conn.close()

    if count:
        logger.info("[Skills] Seed : %d fichier(s) importé(s)/mis à jour", count)
    return count
