"""
# MODULE_SOCIETE: Connecteurs ERP/CRM pour les sociétés.
Fournit BaseConnector (ABC), DolibarrConnector (httpx async) et
ConnectorFactory pour instancier le bon connecteur selon la config.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any


# ── BaseConnector ─────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    """
    # MODULE_SOCIETE: Interface minimale que tout connecteur doit implémenter.
    Chaque méthode retourne une liste de dicts normalisés.
    """

    connector_type: str = "base"

    @abstractmethod
    async def connect(self) -> bool:
        """Tester la connexion. Retourne True si OK."""
        ...

    @abstractmethod
    async def get_invoices(self, company_id: str | None = None) -> list[dict]:
        """Retourne les factures (normalisées)."""
        ...

    @abstractmethod
    async def get_quotes(self, company_id: str | None = None) -> list[dict]:
        """Retourne les devis (normalisés)."""
        ...

    @abstractmethod
    async def get_contacts(self, company_id: str | None = None) -> list[dict]:
        """Retourne les contacts (normalisés)."""
        ...

    @abstractmethod
    async def get_tickets(self, company_id: str | None = None) -> list[dict]:
        """Retourne les tickets/support (normalisés)."""
        ...


# ── DolibarrConnector ─────────────────────────────────────────────────────────

class DolibarrConnector(BaseConnector):
    """
    # MODULE_SOCIETE: Connecteur REST vers Dolibarr ERP.
    Utilise httpx (async). L'API key est passée via le header DOLAPIKEY.

    Config attendue :
    {
        "url": "https://dolibarr.example.com",
        "api_key": "VOTRE_API_KEY",
        "company_id_field": "code_client"   # champ Dolibarr ↔ id société ADA
    }
    """

    connector_type: str = "dolibarr"

    def __init__(self, config: dict) -> None:
        self._base_url = config.get("url", "").rstrip("/")
        self._api_key = config.get("api_key", "")
        self._company_id_field = config.get("company_id_field", "code_client")
        self._timeout = config.get("timeout_s", 10)

    @property
    def _headers(self) -> dict:
        return {
            "DOLAPIKEY": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        """Requête GET vers l'API Dolibarr."""
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx est requis pour DolibarrConnector : pip install httpx"
            ) from exc

        url = f"{self._base_url}/api/index.php/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self._timeout, verify=True) as client:
            resp = await client.get(url, headers=self._headers, params=params or {})
            resp.raise_for_status()
            return resp.json()

    async def connect(self) -> bool:
        """Ping l'API Dolibarr. Retourne True si connecté."""
        try:
            data = await self._get("status")
            return bool(data)
        except Exception as exc:
            print(f"[DolibarrConnector] Erreur connexion: {exc}")
            return False

    async def get_thirdparty_id(self, code_client: str) -> int | None:
        """Résout le code_client Dolibarr en ID numérique interne.
        Retourne None si non trouvé."""
        try:
            raw = await self._get("thirdparties", {
                "sqlfilters": f"(t.code_client:=:'{code_client}')",
                "limit": 1,
            })
            if raw and isinstance(raw, list) and raw[0].get("id"):
                return int(raw[0]["id"])
        except Exception as exc:
            print(f"[DolibarrConnector] get_thirdparty_id error: {exc}")
        return None

    async def get_invoices(self, company_id: str | None = None, since_ts: float | None = None,
                           thirdparty_id: int | None = None) -> list[dict]:
        """
        # MODULE_SOCIETE: récupère les factures depuis Dolibarr.
        Normalise en : {id, ref, company, amount, status, date}
        since_ts : epoch Unix — filtre les factures >= cette date (pour CA YTD).
        thirdparty_id : ID numérique Dolibarr (prioritaire sur company_id).
        """
        params = {"limit": 500, "sortfield": "t.datef", "sortorder": "DESC"}
        if thirdparty_id:
            params["thirdparty_ids"] = str(thirdparty_id)
        elif company_id:
            params[self._company_id_field] = company_id
        if since_ts is not None:
            # Combiner avec sqlfilters existant si présent
            params["sqlfilters"] = f"(t.datef:>=:{int(since_ts)})"
        try:
            raw = await self._get("invoices", params)
            return [self._normalize_invoice(r) for r in (raw or [])]
        except Exception as exc:
            print(f"[DolibarrConnector] get_invoices error: {exc}")
            return []

    def _normalize_invoice(self, raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "ref": raw.get("ref", ""),
            "company": raw.get("socid", ""),
            "amount": float(raw.get("total_ttc", 0) or 0),
            "amount_ht": float(raw.get("total_ht", 0) or 0),
            "status": raw.get("statut", ""),
            "date": raw.get("date", ""),
            "due_date": raw.get("date_lim_reglement", ""),
        }

    async def get_quotes(self, company_id: str | None = None,
                         thirdparty_id: int | None = None) -> list[dict]:
        """
        # MODULE_SOCIETE: récupère les devis depuis Dolibarr.
        Normalise en : {id, ref, company, amount, status, date}
        thirdparty_id : ID numérique Dolibarr (prioritaire sur company_id).
        """
        params = {"limit": 100, "sortfield": "t.datep", "sortorder": "DESC"}
        if thirdparty_id:
            params["thirdparty_ids"] = str(thirdparty_id)
        elif company_id:
            params[self._company_id_field] = company_id
        try:
            raw = await self._get("proposals", params)
            return [self._normalize_quote(r) for r in (raw or [])]
        except Exception as exc:
            print(f"[DolibarrConnector] get_quotes error: {exc}")
            return []

    def _normalize_quote(self, raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "ref": raw.get("ref", ""),
            "company": raw.get("socid", ""),
            "amount": float(raw.get("total_ttc", 0) or 0),
            "status": raw.get("statut", ""),
            "date": raw.get("date", ""),
        }

    async def get_contacts(self, company_id: str | None = None,
                           thirdparty_id: int | None = None) -> list[dict]:
        """
        # MODULE_SOCIETE: récupère les contacts Dolibarr.
        Normalise en : {id, name, email, phone, role}
        thirdparty_id : ID numérique Dolibarr (prioritaire sur company_id).
        """
        params = {"limit": 100}
        if thirdparty_id:
            params["socid"] = str(thirdparty_id)
        elif company_id:
            params["socid"] = company_id
        try:
            raw = await self._get("contacts", params)
            return [self._normalize_contact(r) for r in (raw or [])]
        except Exception as exc:
            print(f"[DolibarrConnector] get_contacts error: {exc}")
            return []

    def _normalize_contact(self, raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "name": f"{raw.get('firstname', '')} {raw.get('lastname', '')}".strip(),
            "email": raw.get("email", ""),
            "phone": raw.get("phone_pro", ""),
            "role": raw.get("poste", ""),
        }

    async def get_tickets(self, company_id: str | None = None,
                          thirdparty_id: int | None = None) -> list[dict]:
        """
        # MODULE_SOCIETE: récupère les tickets support Dolibarr.
        Normalise en : {id, ref, company, subject, status, date}
        thirdparty_id : ID numérique Dolibarr (prioritaire sur company_id).
        """
        params = {"limit": 200, "sortfield": "t.datec", "sortorder": "DESC"}
        if thirdparty_id:
            params["thirdparty_ids"] = str(thirdparty_id)
        elif company_id:
            params[self._company_id_field] = company_id
        try:
            raw = await self._get("tickets", params)
            return [self._normalize_ticket(r) for r in (raw or [])]
        except Exception as exc:
            print(f"[DolibarrConnector] get_tickets error: {exc}")
            return []

    def _normalize_ticket(self, raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "ref": raw.get("ref", ""),
            "company": raw.get("socid", ""),
            "subject": raw.get("subject", ""),
            "status": raw.get("status", ""),
            "date": raw.get("datec", ""),
            "severity": raw.get("severity", ""),
        }


# ── ConnectorFactory ──────────────────────────────────────────────────────────

_REGISTRY: dict[str, type[BaseConnector]] = {
    "dolibarr": DolibarrConnector,
}


class ConnectorFactory:
    """
    # MODULE_SOCIETE: instancie le bon connecteur selon le type.
    Usage : ConnectorFactory.get("dolibarr", {"url": ..., "api_key": ...})
    """

    @staticmethod
    def get(connector_type: str, config: dict) -> BaseConnector:
        cls = _REGISTRY.get(connector_type)
        if cls is None:
            raise ValueError(
                f"ConnectorFactory : type inconnu '{connector_type}'. "
                f"Types supportés : {list(_REGISTRY.keys())}"
            )
        return cls(config)

    @staticmethod
    def register_type(connector_type: str, cls: type[BaseConnector]) -> None:
        """Permet d'enregistrer un connecteur tiers."""
        _REGISTRY[connector_type] = cls
