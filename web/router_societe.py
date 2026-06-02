"""
# MODULE_SOCIETE: Router FastAPI pour l'API Société.
Endpoints CRUD companies, métriques, timeline, documents et contexte chat.

Guard : le router n'est inclus que si MODULES_ENABLED["societe"] = True.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from config import MODULES_ENABLED

# MODULE_SOCIETE: guard d'import
if not MODULES_ENABLED.get("societe", False):
    # Router vide — ne sera pas inclus par server.py
    router = APIRouter()
else:
    from core.societe.company_model import (
        Company,
        CompanyDocument,
        CompanyMetric,
        TimelineEvent,
        company_model,
    )
    from core.plugin_registry import plugin_registry

    router = APIRouter(prefix="/api/societe", tags=["societe"])

    # ── Initialisation DB ─────────────────────────────────────────────────────

    company_model.init()

    # ── Schémas Pydantic ──────────────────────────────────────────────────────

    class CompanyIn(BaseModel):
        id: str
        name: str
        logo: str = "🏢"
        color: str = "#5E6AD2"
        type: str = "client"
        status: str = "active"
        address: str = ""
        phone: str = ""
        email: str = ""
        website: str = ""
        notes: str = ""
        connectors: dict = Field(default_factory=dict)

    class CompanyUpdateIn(BaseModel):
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
        connectors: dict = Field(default_factory=dict)

    class MetricIn(BaseModel):
        metric_key: str
        metric_value: float
        currency: str = "EUR"

    class TimelineEventIn(BaseModel):
        event_type: str
        title: str
        description: str = ""
        amount: float | None = None
        status: str = ""
        event_date: float | None = None

    class DocumentIn(BaseModel):
        title: str
        doc_type: str
        file_path: str = ""
        url: str = ""
        amount: float | None = None
        status: str = ""
        doc_date: float | None = None

    class DolibarrConfigIn(BaseModel):
        """# MODULE_SOCIETE: Configuration du connecteur Dolibarr."""
        url: str
        api_key: str = ""            # vide = conserver l'existant
        company_id_field: str = "code_client"
        dolibarr_company_id: str = ""  # ID de la société dans Dolibarr
        timeout_s: int = 10

    # ── Companies ─────────────────────────────────────────────────────────────

    @router.get("/companies")
    async def list_companies(status: str | None = "active") -> list[dict]:
        """# MODULE_SOCIETE: Liste toutes les sociétés."""
        companies = company_model.list_companies(status=status)
        return [
            {
                "id": c.id,
                "name": c.name,
                "logo": c.logo,
                "color": c.color,
                "type": c.type,
                "status": c.status,
                "address": c.address,
                "phone": c.phone,
                "email": c.email,
                "website": c.website,
                "notes": c.notes,
                "connectors": c.connectors,
            }
            for c in companies
        ]

    @router.get("/companies/{company_id}")
    async def get_company(company_id: str) -> dict:
        """# MODULE_SOCIETE: Détail d'une société."""
        c = company_model.get_company(company_id)
        if not c:
            raise HTTPException(status_code=404, detail="Société introuvable")
        return {
            "id": c.id,
            "name": c.name,
            "logo": c.logo,
            "color": c.color,
            "type": c.type,
            "status": c.status,
            "address": c.address,
            "phone": c.phone,
            "email": c.email,
            "website": c.website,
            "notes": c.notes,
            "connectors": c.connectors,
        }

    @router.post("/companies", status_code=201)
    async def create_company(body: CompanyIn) -> dict:
        """# MODULE_SOCIETE: Crée une nouvelle société."""
        company_model.create_company(
            Company(
                id=body.id,
                name=body.name,
                logo=body.logo,
                color=body.color,
                type=body.type,
                status=body.status,
                address=body.address,
                phone=body.phone,
                email=body.email,
                website=body.website,
                notes=body.notes,
                connectors=body.connectors,
            )
        )
        return {"ok": True, "id": body.id}

    @router.put("/companies/{company_id}")
    async def update_company(company_id: str, body: CompanyUpdateIn) -> dict:
        """# MODULE_SOCIETE: Met à jour une société existante."""
        existing = company_model.get_company(company_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Société introuvable")
        company_model.update_company(
            Company(
                id=company_id,
                name=body.name,
                logo=body.logo,
                color=body.color,
                type=body.type,
                status=body.status,
                address=body.address,
                phone=body.phone,
                email=body.email,
                website=body.website,
                notes=body.notes,
                connectors=body.connectors,
            )
        )
        updated = company_model.get_company(company_id)
        if not updated:
            raise HTTPException(status_code=500, detail="Mise à jour échouée")
        return {
            "id": updated.id,
            "name": updated.name,
            "logo": updated.logo,
            "color": updated.color,
            "type": updated.type,
            "status": updated.status,
            "address": updated.address,
            "phone": updated.phone,
            "email": updated.email,
            "website": updated.website,
            "notes": updated.notes,
            "connectors": updated.connectors,
        }

    @router.delete("/companies/{company_id}")
    async def delete_company(company_id: str) -> dict:
        """# MODULE_SOCIETE: Supprime une société."""
        existing = company_model.get_company(company_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Société introuvable")
        company_model.delete_company(company_id)
        return {"ok": True}

    # ── Metrics ───────────────────────────────────────────────────────────────

    @router.get("/companies/{company_id}/metrics")
    async def get_metrics(company_id: str) -> dict:
        """# MODULE_SOCIETE: Métriques d'une société."""
        _check_exists(company_id)
        return company_model.get_metrics(company_id)

    @router.put("/companies/{company_id}/metrics")
    async def upsert_metrics(company_id: str, body: list[MetricIn]) -> dict:
        """# MODULE_SOCIETE: Met à jour les métriques d'une société."""
        _check_exists(company_id)
        company_model.upsert_metrics(
            [CompanyMetric(company_id=company_id, metric_key=m.metric_key,
                           metric_value=m.metric_value, currency=m.currency)
             for m in body]
        )
        return {"ok": True}

    # ── Timeline ──────────────────────────────────────────────────────────────

    @router.get("/companies/{company_id}/timeline")
    async def get_timeline(company_id: str, limit: int = 50) -> list[dict]:
        """# MODULE_SOCIETE: Timeline d'une société."""
        _check_exists(company_id)
        return company_model.get_timeline(company_id, limit=limit)

    @router.post("/companies/{company_id}/timeline", status_code=201)
    async def add_timeline_event(company_id: str, body: TimelineEventIn) -> dict:
        """# MODULE_SOCIETE: Ajoute un événement dans la timeline."""
        _check_exists(company_id)
        event_id = company_model.add_timeline_event(
            TimelineEvent(
                company_id=company_id,
                event_type=body.event_type,
                title=body.title,
                description=body.description,
                amount=body.amount,
                status=body.status,
                event_date=body.event_date,
            )
        )
        return {"ok": True, "id": event_id}

    # ── Documents ─────────────────────────────────────────────────────────────

    @router.get("/companies/{company_id}/documents")
    async def get_documents(company_id: str, doc_type: str | None = None) -> list[dict]:
        """# MODULE_SOCIETE: Documents d'une société."""
        _check_exists(company_id)
        return company_model.get_documents(company_id, doc_type=doc_type)

    @router.post("/companies/{company_id}/documents", status_code=201)
    async def add_document(company_id: str, body: DocumentIn) -> dict:
        """# MODULE_SOCIETE: Ajoute un document."""
        _check_exists(company_id)
        doc_id = company_model.add_document(
            CompanyDocument(
                company_id=company_id,
                title=body.title,
                doc_type=body.doc_type,
                file_path=body.file_path,
                url=body.url,
                amount=body.amount,
                status=body.status,
                doc_date=body.doc_date,
            )
        )
        return {"ok": True, "id": doc_id}

    # ── Connecteurs Dolibarr ──────────────────────────────────────────────────

    @router.put("/companies/{company_id}/connectors/dolibarr")
    async def set_dolibarr_config(company_id: str, body: DolibarrConfigIn) -> dict:
        """# MODULE_SOCIETE: Enregistre la config Dolibarr d'une société."""
        c = company_model.get_company(company_id)
        if not c:
            raise HTTPException(status_code=404, detail="Société introuvable")
        existing_key = (c.connectors or {}).get("dolibarr", {}).get("api_key", "")
        c.connectors["dolibarr"] = {
            "url": body.url.rstrip("/"),
            "api_key": body.api_key if body.api_key else existing_key,
            "company_id_field": body.company_id_field or "code_client",
            "dolibarr_company_id": body.dolibarr_company_id,
            "timeout_s": body.timeout_s,
        }
        company_model.update_company(c)
        return {"ok": True}

    @router.get("/companies/{company_id}/connectors/dolibarr/status")
    async def dolibarr_status(company_id: str) -> dict:
        """# MODULE_SOCIETE: Teste la connexion Dolibarr (ping /api/status)."""
        c = company_model.get_company(company_id)
        if not c:
            raise HTTPException(status_code=404, detail="Société introuvable")
        dol_cfg = (c.connectors or {}).get("dolibarr", {})
        if not dol_cfg.get("url") or not dol_cfg.get("api_key"):
            return {"ok": False, "connected": False, "error": "Non configuré"}
        from core.societe.connectors.dolibarr_connector import DolibarrConnector
        conn = DolibarrConnector(dol_cfg)
        ok = await conn.connect()
        return {"ok": True, "connected": ok, "url": dol_cfg["url"]}

    @router.post("/companies/{company_id}/sync/dolibarr")
    async def sync_dolibarr(company_id: str) -> dict:
        """
        # MODULE_SOCIETE: Sync Dolibarr → ADA.
        Factures → métriques (ca_ytd, unpaid) + timeline.
        Devis → documents.  Tickets → timeline.  Contacts → métrique contact_count.
        """
        c = company_model.get_company(company_id)
        if not c:
            raise HTTPException(status_code=404, detail="Société introuvable")
        dol_cfg = (c.connectors or {}).get("dolibarr", {})
        if not dol_cfg.get("url") or not dol_cfg.get("api_key"):
            raise HTTPException(status_code=400, detail="Connecteur Dolibarr non configuré")

        from core.societe.connectors.dolibarr_connector import DolibarrConnector
        from datetime import datetime, timezone

        conn = DolibarrConnector(dol_cfg)
        dol_id = dol_cfg.get("dolibarr_company_id", "").strip()

        # ── Résolution de l'ID numérique Dolibarr ────────────────────────────
        # MODULE_SOCIETE: On cherche l'ID numérique du tiers dans Dolibarr
        # pour filtrer correctement (thirdparty_ids= plutôt que code_client=).
        thirdparty_id: int | None = None
        if dol_id and dol_id.isdigit():
            thirdparty_id = int(dol_id)
        else:
            # Lookup par code_client (valeur alphanumérique saisie)
            lookup_code = dol_id or company_id
            thirdparty_id = await conn.get_thirdparty_id(lookup_code)
            if thirdparty_id:
                # Mettre en cache pour les prochaines syncs
                c.connectors["dolibarr"]["dolibarr_company_id"] = str(thirdparty_id)
                company_model.update_company(c)
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Société '{lookup_code}' introuvable dans Dolibarr. "
                           f"Vérifiez le code client ou renseignez l'ID numérique directement."
                )

        # ── Factures ─────────────────────────────────────────────────────────
        # MODULE_SOCIETE: filtrer dès l'API Dolibarr sur le 1er jan de l'année
        now_year = datetime.now().year
        year_start_ts = float(int(datetime(now_year, 1, 1).timestamp()))
        invoices = await conn.get_invoices(thirdparty_id=thirdparty_id, since_ts=year_start_ts)
        ca_ytd = 0.0
        unpaid = 0.0
        for inv in invoices:
            ca_ytd += float(inv.get("amount_ht", 0) or 0)
            if str(inv.get("status", "")) in ("1", "2"):   # impayée ou partiellement réglée
                unpaid += float(inv.get("amount", 0) or 0)

        company_model.upsert_metrics([
            CompanyMetric(company_id=company_id, metric_key="ca_ytd",        metric_value=ca_ytd),
            CompanyMetric(company_id=company_id, metric_key="unpaid",        metric_value=unpaid),
            CompanyMetric(company_id=company_id, metric_key="invoice_count", metric_value=float(len(invoices)), currency=""),
        ])
        company_model.delete_timeline_by_type(company_id, "dolibarr_invoice")
        for inv in invoices[:20]:
            due_ts = _parse_ts(inv.get("due_date"))
            due_str = _fmt_date(due_ts) if due_ts else "-"
            company_model.add_timeline_event(TimelineEvent(
                company_id=company_id,
                event_type="dolibarr_invoice",
                title=f"Facture {inv.get('ref', '')}",
                description=f"Échéance : {due_str}",
                amount=float(inv.get("amount", 0) or 0),
                status=_status_label(inv.get("status", ""), "invoice"),
                event_date=_parse_ts(inv.get("date")),
            ))

        # ── Devis ─────────────────────────────────────────────────────────────
        quotes = await conn.get_quotes(thirdparty_id=thirdparty_id)
        company_model.delete_documents_by_type(company_id, "dolibarr_devis")
        for q in quotes[:30]:
            company_model.add_document(CompanyDocument(
                company_id=company_id,
                title=f"Devis {q.get('ref', '')}",
                doc_type="dolibarr_devis",
                amount=float(q.get("amount", 0) or 0),
                status=_status_label(q.get("status", ""), "quote"),
                doc_date=_parse_ts(q.get("date")),
            ))
        company_model.upsert_metrics([
            CompanyMetric(company_id=company_id, metric_key="quotes_pending",
                          metric_value=float(sum(1 for q in quotes if str(q.get("status","")) in ("0","1"))),
                          currency=""),
            CompanyMetric(company_id=company_id, metric_key="quotes_total",
                          metric_value=float(len(quotes)), currency=""),
        ])

        # ── Tickets ────────────────────────────────────────────────────────────
        tickets = await conn.get_tickets(thirdparty_id=thirdparty_id)
        company_model.delete_timeline_by_type(company_id, "dolibarr_ticket")
        for t in tickets[:20]:
            company_model.add_timeline_event(TimelineEvent(
                company_id=company_id,
                event_type="dolibarr_ticket",
                title=f"Ticket {t.get('ref', '')} — {t.get('subject', '')}",
                description=t.get("subject", ""),
                status=_status_label(t.get("status", ""), "ticket"),
                event_date=_parse_ts(t.get("date")),
            ))

        # ── Contacts ───────────────────────────────────────────────────────────
        contacts = await conn.get_contacts(thirdparty_id=thirdparty_id)
        open_tickets = sum(1 for t in tickets if str(t.get("status", "")) in ("0", "1", "2"))
        company_model.upsert_metrics([
            CompanyMetric(company_id=company_id, metric_key="contact_count",
                          metric_value=float(len(contacts)), currency=""),
            CompanyMetric(company_id=company_id, metric_key="open_tickets",
                          metric_value=float(open_tickets), currency=""),
            CompanyMetric(company_id=company_id, metric_key="ticket_count",
                          metric_value=float(len(tickets)), currency=""),
        ])

        # ── MAJ last_sync ──────────────────────────────────────────────────────
        c.connectors["dolibarr"]["last_sync"] = datetime.now(timezone.utc).isoformat()
        company_model.update_company(c)

        return {
            "ok": True,
            "synced": {
                "invoices": len(invoices),
                "quotes":   len(quotes),
                "tickets":  len(tickets),
                "contacts": len(contacts),
            },
            "metrics": {"ca_ytd": ca_ytd, "unpaid": unpaid},
        }

    # ── Contexte chat ─────────────────────────────────────────────────────────

    @router.get("/companies/{company_id}/context")
    async def get_chat_context(company_id: str) -> dict:
        """
        # MODULE_SOCIETE: Retourne le bloc de contexte Mistral pour une société.
        Utilisé par le frontend pour injecter le contexte dans le chat.
        """
        _check_exists(company_id)
        plugin = plugin_registry.get("societe")
        if not plugin:
            return {"context": "", "quick_prompts": []}
        return {
            "context": plugin.get_chat_context(company_id),
            "quick_prompts": plugin.get_quick_prompts(company_id),
        }

    @router.get("/context")
    async def get_global_context() -> dict:
        """# MODULE_SOCIETE: Contexte global portefeuille (sans société ciblée)."""
        plugin = plugin_registry.get("societe")
        if not plugin:
            return {"context": "", "quick_prompts": []}
        return {
            "context": plugin.get_chat_context(None),
            "quick_prompts": plugin.get_quick_prompts(None),
        }

    # ── Helper ────────────────────────────────────────────────────────────────

    def _check_exists(company_id: str) -> None:
        if not company_model.get_company(company_id):
            raise HTTPException(status_code=404, detail="Société introuvable")

    def _fmt_date(ts: float) -> str:
        """# MODULE_SOCIETE: Formate un timestamp epoch en JJ/MM/AAAA."""
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m/%Y")
        except Exception:
            return str(int(ts))

    def _parse_ts(date_val: Any) -> float | None:
        """# MODULE_SOCIETE: Convertit une date Dolibarr (str ISO ou int epoch) en float epoch."""
        if not date_val:
            return None
        try:
            if isinstance(date_val, (int, float)):
                return float(date_val)
            from datetime import datetime
            return datetime.fromisoformat(str(date_val).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    def _status_label(status: Any, kind: str) -> str:
        """# MODULE_SOCIETE: Traduit les codes statut Dolibarr en labels lisibles."""
        s = str(status)
        if kind == "invoice":
            return {"0": "brouillon", "1": "impayée", "2": "partiellement réglée",
                    "3": "réglée", "-1": "annulée"}.get(s, s)
        if kind == "quote":
            return {"0": "brouillon", "1": "validé", "2": "signé",
                    "3": "facturé", "-1": "refusé"}.get(s, s)
        if kind == "ticket":
            return {"0": "nouveau", "1": "en cours", "2": "en attente",
                    "3": "résolu", "-1": "fermé"}.get(s, s)
        return s
