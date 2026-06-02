"""
# MODULE_SOCIETE: Modèle de données SQLite pour les sociétés.
DB : data/societe.db
Tables : companies, company_metrics, company_timeline, company_documents
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ── Chemin base de données ────────────────────────────────────────────────────

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "societe.db"
_lock = threading.Lock()


@contextmanager
def _get_conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
-- MODULE_SOCIETE: table principale des sociétés
CREATE TABLE IF NOT EXISTS companies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    logo            TEXT DEFAULT '🏢',
    color           TEXT DEFAULT '#5E6AD2',
    type            TEXT DEFAULT 'SARL',         -- SARL | SAS | EI | SCI | Holding | Autre
    status          TEXT DEFAULT 'active',        -- active | archive
    address         TEXT DEFAULT '',
    phone           TEXT DEFAULT '',
    email           TEXT DEFAULT '',
    website         TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    connectors_json TEXT DEFAULT '{}',            -- {"dolibarr": {...}}
    skill_domain    TEXT DEFAULT NULL,            -- domaine skills FTS (ex: "margep"), NULL = utilise l'id
    created_at      REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
    updated_at      REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
);

-- MODULE_SOCIETE: métriques temps-réel (CA, impayés, tickets, devis)
CREATE TABLE IF NOT EXISTS company_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    metric_key      TEXT NOT NULL,   -- ca_ytd | unpaid | open_tickets | quotes_pending
    metric_value    REAL NOT NULL DEFAULT 0,
    currency        TEXT DEFAULT 'EUR',
    updated_at      REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
    UNIQUE(company_id, metric_key)
);

-- MODULE_SOCIETE: timeline des événements par société
CREATE TABLE IF NOT EXISTS company_timeline (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,   -- invoice | meeting | call | note | ticket | quote
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    amount      REAL,
    status      TEXT DEFAULT '',
    event_date  REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
    created_at  REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
);

-- MODULE_SOCIETE: documents liés à une société
CREATE TABLE IF NOT EXISTS company_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    doc_type    TEXT NOT NULL,   -- invoice | quote | contract | report | other
    file_path   TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    amount      REAL,
    status      TEXT DEFAULT '',
    doc_date    REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
    created_at  REAL NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
);
"""

_SEED_COMPANIES: list[dict] = [
    {"id": "opentechno", "name": "OpenTechno", "logo": "🔷", "color": "#5E6AD2", "type": "SAS",  "status": "active", "address": "", "email": "", "website": "", "notes": "", "connectors_json": '{"dolibarr": {"enabled": false}}', "skill_domain": "opentechno"},
    {"id": "uscss",      "name": "USCSS",      "logo": "🚀", "color": "#E86C3A", "type": "SARL", "status": "active", "address": "", "email": "", "website": "", "notes": "", "connectors_json": '{"dolibarr": {"enabled": false}}', "skill_domain": "uscss"},
    {"id": "margepro",  "name": "MargePro",  "logo": "💰", "color": "#16A349", "type": "EI",   "status": "active", "address": "", "email": "", "website": "", "notes": "", "connectors_json": '{"dolibarr": {"enabled": false}}', "skill_domain": "margep"},
    {"id": "nexagen",   "name": "NexaGen",   "logo": "🌐", "color": "#7C3AED", "type": "SAS",  "status": "active", "address": "", "email": "", "website": "", "notes": "", "connectors_json": '{"dolibarr": {"enabled": false}}', "skill_domain": "nexagen"},
]

_SEED_METRICS: list[dict] = [
    # Les métriques sont initialisées à zéro — elles sont mises à jour via Dolibarr ou l'interface
    {"company_id": "opentechno", "metric_key": "ca_ytd",         "metric_value": 0},
    {"company_id": "opentechno", "metric_key": "unpaid",         "metric_value": 0},
    {"company_id": "opentechno", "metric_key": "open_tickets",   "metric_value": 0},
    {"company_id": "opentechno", "metric_key": "quotes_pending", "metric_value": 0},
    {"company_id": "uscss",      "metric_key": "ca_ytd",         "metric_value": 0},
    {"company_id": "uscss",      "metric_key": "unpaid",         "metric_value": 0},
    {"company_id": "uscss",      "metric_key": "open_tickets",   "metric_value": 0},
    {"company_id": "uscss",      "metric_key": "quotes_pending", "metric_value": 0},
    {"company_id": "margepro",   "metric_key": "ca_ytd",         "metric_value": 0},
    {"company_id": "margepro",   "metric_key": "unpaid",         "metric_value": 0},
    {"company_id": "margepro",   "metric_key": "open_tickets",   "metric_value": 0},
    {"company_id": "margepro",   "metric_key": "quotes_pending", "metric_value": 0},
    {"company_id": "nexagen",    "metric_key": "ca_ytd",         "metric_value": 0},
    {"company_id": "nexagen",    "metric_key": "unpaid",         "metric_value": 0},
    {"company_id": "nexagen",    "metric_key": "open_tickets",   "metric_value": 0},
    {"company_id": "nexagen",    "metric_key": "quotes_pending", "metric_value": 0},
]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Company:
    id: str
    name: str
    logo: str = "🏢"
    color: str = "#5E6AD2"
    type: str = "SARL"
    status: str = "active"
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    notes: str = ""
    connectors: dict = field(default_factory=dict)
    skill_domain: str = ""  # MODULE_SOCIETE: domaine skill FTS, vide = utilise l'id comme domaine

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Company":
        return cls(
            id=row["id"],
            name=row["name"],
            logo=row["logo"],
            color=row["color"],
            type=row["type"],
            status=row["status"],
            address=row["address"],
            phone=row["phone"],
            email=row["email"],
            website=row["website"],
            notes=row["notes"],
            connectors=json.loads(row["connectors_json"] or "{}"),
            skill_domain=row["skill_domain"] or "",
        )


@dataclass
class CompanyMetric:
    company_id: str
    metric_key: str
    metric_value: float
    currency: str = "EUR"


@dataclass
class TimelineEvent:
    company_id: str
    event_type: str
    title: str
    description: str = ""
    amount: float | None = None
    status: str = ""
    event_date: float | None = None


@dataclass
class CompanyDocument:
    company_id: str
    title: str
    doc_type: str
    file_path: str = ""
    url: str = ""
    amount: float | None = None
    status: str = ""
    doc_date: float | None = None


# ── CompanyModel (singleton) ──────────────────────────────────────────────────

class CompanyModel:
    """
    # MODULE_SOCIETE: Accès base de données sociétés (thread-safe).
    Utiliser l'instance globale `company_model`.
    """

    _instance: "CompanyModel | None" = None

    def __new__(cls) -> "CompanyModel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def init(self) -> None:
        if self._initialized:
            return
        with _get_conn() as conn:
            conn.executescript(_DDL)
        self._migrate_type_field()
        self._migrate_skill_domain()
        self._maybe_seed()
        self._initialized = True
        print("[CompanyModel] ✓ Base de données societes.db initialisée")

    def _migrate_skill_domain(self) -> None:
        """Migration : ajoute la colonne skill_domain si absente."""
        with _get_conn() as conn:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(companies)").fetchall()]
            if "skill_domain" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN skill_domain TEXT DEFAULT NULL")
                # Seed initial pour margepro dont le domaine skill diffère de l'id
                conn.execute("UPDATE companies SET skill_domain='margep' WHERE id='margepro'")
                print("[CompanyModel] ↳ Migration skill_domain ajouté")

    def _migrate_type_field(self) -> None:
        """
        Migration : remplace les anciens types CRM (client/prospect/partenaire)
        par la forme juridique par défaut (SARL) si la DB existait avant la
        correction de design.
        """
        _old = ("client", "prospect", "partenaire")
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, type FROM companies WHERE type IN (?,?,?)", _old
            ).fetchall()
            if rows:
                conn.executemany(
                    "UPDATE companies SET type='SARL' WHERE id=?",
                    [(r["id"],) for r in rows],
                )
                print(f"[CompanyModel] ↳ Migration type CRM→SARL : {len(rows)} société(s)")

    def _maybe_seed(self) -> None:
        """Insère les données de démonstration si la table est vide."""
        with _get_conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            if n > 0:
                return
            for c in _SEED_COMPANIES:
                conn.execute(
                    """INSERT OR IGNORE INTO companies
                       (id, name, logo, color, type, status, address, email, website, notes, connectors_json, skill_domain)
                       VALUES (:id, :name, :logo, :color, :type, :status, :address, :email, :website, :notes, :connectors_json, :skill_domain)""",
                    c,
                )
            for m in _SEED_METRICS:
                conn.execute(
                    "INSERT OR IGNORE INTO company_metrics (company_id, metric_key, metric_value) VALUES (:company_id, :metric_key, :metric_value)",
                    m,
                )
        print("[CompanyModel] ✓ Données de seed insérées")

    # ── CRUD companies ────────────────────────────────────────────────────────

    def list_companies(self, status: str | None = "active") -> list[Company]:
        """Retourne toutes les sociétés (filtrables par status)."""
        with _get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM companies WHERE status = ? ORDER BY name", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM companies ORDER BY name"
                ).fetchall()
        return [Company.from_row(r) for r in rows]

    def get_company(self, company_id: str) -> Company | None:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE id = ?", (company_id,)
            ).fetchone()
        return Company.from_row(row) if row else None

    def create_company(self, company: Company) -> None:
        with _get_conn() as conn:
            conn.execute(
                    """INSERT INTO companies (id, name, logo, color, type, status,
                   address, phone, email, website, notes, connectors_json, skill_domain)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    company.id, company.name, company.logo, company.color,
                    company.type, company.status, company.address, company.phone,
                    company.email, company.website, company.notes,
                    json.dumps(company.connectors), company.skill_domain or None,
                ),
            )

    def update_company(self, company: Company) -> None:
        with _get_conn() as conn:
            conn.execute(
                """UPDATE companies SET name=?, logo=?, color=?, type=?, status=?,
                   address=?, phone=?, email=?, website=?, notes=?, connectors_json=?,
                   skill_domain=?,
                   updated_at=CAST(strftime('%s','now') AS INTEGER)
                   WHERE id=?""",
                (
                    company.name, company.logo, company.color, company.type,
                    company.status, company.address, company.phone, company.email,
                    company.website, company.notes, json.dumps(company.connectors),
                    company.skill_domain or None,
                    company.id,
                ),
            )

    def delete_company(self, company_id: str) -> None:
        with _get_conn() as conn:
            conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))

    # ── Metrics ───────────────────────────────────────────────────────────────

    def upsert_metrics(self, metrics: list[CompanyMetric]) -> None:
        with _get_conn() as conn:
            for m in metrics:
                conn.execute(
                    """INSERT INTO company_metrics (company_id, metric_key, metric_value, currency, updated_at)
                       VALUES (?, ?, ?, ?, CAST(strftime('%s','now') AS INTEGER))
                       ON CONFLICT(company_id, metric_key) DO UPDATE SET
                       metric_value=excluded.metric_value,
                       currency=excluded.currency,
                       updated_at=CAST(strftime('%s','now') AS INTEGER)""",
                    (m.company_id, m.metric_key, m.metric_value, m.currency),
                )

    def get_metrics(self, company_id: str) -> dict[str, float]:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT metric_key, metric_value FROM company_metrics WHERE company_id = ?",
                (company_id,),
            ).fetchall()
        return {r["metric_key"]: r["metric_value"] for r in rows}

    # ── Timeline ──────────────────────────────────────────────────────────────

    def add_timeline_event(self, event: TimelineEvent) -> int:
        import time
        with _get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO company_timeline
                   (company_id, event_type, title, description, amount, status, event_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.company_id, event.event_type, event.title,
                    event.description, event.amount, event.status,
                    event.event_date or time.time(),
                ),
            )
        return cursor.lastrowid

    def get_timeline(self, company_id: str, limit: int = 50) -> list[dict]:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM company_timeline
                   WHERE company_id = ?
                   ORDER BY event_date DESC LIMIT ?""",
                (company_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Documents ─────────────────────────────────────────────────────────────

    def add_document(self, doc: CompanyDocument) -> int:
        import time
        with _get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO company_documents
                   (company_id, title, doc_type, file_path, url, amount, status, doc_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc.company_id, doc.title, doc.doc_type, doc.file_path,
                    doc.url, doc.amount, doc.status,
                    doc.doc_date or time.time(),
                ),
            )
        return cursor.lastrowid

    def get_documents(self, company_id: str, doc_type: str | None = None) -> list[dict]:
        with _get_conn() as conn:
            if doc_type:
                rows = conn.execute(
                    """SELECT * FROM company_documents
                       WHERE company_id = ? AND doc_type = ?
                       ORDER BY doc_date DESC""",
                    (company_id, doc_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM company_documents
                       WHERE company_id = ?
                       ORDER BY doc_date DESC""",
                    (company_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_timeline_by_type(self, company_id: str, event_type: str) -> None:
        """# MODULE_SOCIETE: Supprime les événements d'un type précis (re-sync)."""
        with _get_conn() as conn:
            conn.execute(
                "DELETE FROM company_timeline WHERE company_id = ? AND event_type = ?",
                (company_id, event_type),
            )

    def delete_documents_by_type(self, company_id: str, doc_type: str) -> None:
        """# MODULE_SOCIETE: Supprime les documents d'un type précis (re-sync)."""
        with _get_conn() as conn:
            conn.execute(
                "DELETE FROM company_documents WHERE company_id = ? AND doc_type = ?",
                (company_id, doc_type),
            )


# MODULE_SOCIETE: instance singleton globale
company_model = CompanyModel()
