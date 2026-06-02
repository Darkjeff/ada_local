"""
# MODULE_SOCIETE: Plugin principal du module Société.
Hérite de BasePlugin. Gère le contexte chat, la navigation, les skills et
les quick-prompts liés aux sociétés gérées dans ADA.

Guard : ce fichier ne doit être importé QUE si MODULES_ENABLED["societe"] = True.
"""
from __future__ import annotations

from core.plugin_registry import BasePlugin
from core.societe.company_model import company_model


# MODULE_SOCIETE: guard — on initialise la DB dès le chargement du plugin
def _ensure_db() -> None:
    company_model.init()


class SocietePlugin(BasePlugin):
    """
    # MODULE_SOCIETE: Plugin qui expose les fonctionnalités de gestion
    de mes sociétés (entreprises propres) dans ADA.
    """

    plugin_id: str = "societe"
    display_name: str = "Sociétés"
    icon: str = "🏢"

    def on_enable(self) -> None:
        _ensure_db()
        print("[SocietePlugin] ✓ Module societe activé")

    def on_disable(self) -> None:
        print("[SocietePlugin] Module societe désactivé — nettoyage terminé")

    # ── Nav items ─────────────────────────────────────────────────────────────

    def get_nav_items(self) -> list[dict]:
        """
        # MODULE_SOCIETE: items de navigation.
        Retourne le dashboard sociétés + un item par société active.
        """
        items = [
            {
                "label": "Sociétés",
                "icon": "🏢",
                "route": "societeDashboardInterface",
            }
        ]
        try:
            companies = company_model.list_companies(status="active")
            for c in companies:
                items.append(
                    {
                        "label": c.name,
                        "icon": c.logo,
                        "route": f"societeDetail_{c.id}",
                        "color": c.color,
                        "company_id": c.id,
                    }
                )
        except Exception as exc:
            print(f"[SocietePlugin] Erreur chargement nav: {exc}")
        return items

    # ── Chat context ──────────────────────────────────────────────────────────

    def get_chat_context(self, company_id: str | None = None) -> str:
        """
        # MODULE_SOCIETE: construit le bloc système injecté dans Mistral
        pour donner le contexte de la société sélectionnée dans la chat bar.
        """
        if not company_id:
            # Contexte générique portefeuille
            companies = company_model.list_companies(status="active")
            names = ", ".join(c.name for c in companies)
            return (
                f"Tu es ADA, assistant de gestion des sociétés. "
                f"Les sociétés actives gérées sont : {names}. "
                f"Tu peux répondre à des questions sur chacune d'elles, "
                f"consulter leurs indicateurs, leurs documents et leur historique."
            )

        company = company_model.get_company(company_id)
        if not company:
            return ""

        metrics = company_model.get_metrics(company_id)
        timeline = company_model.get_timeline(company_id, limit=5)

        ctx_lines = [
            f"Tu es ADA, assistant dédié à la société {company.name} (forme : {company.type}).",
            f"Adresse : {company.address}" if company.address else "",
            f"Email : {company.email}" if company.email else "",
            f"Notes internes : {company.notes}" if company.notes else "",
            "",
            "=== Indicateurs clés ===",
        ]

        metric_labels = {
            "ca_ytd": "CA année en cours",
            "unpaid": "Impayés",
            "open_tickets": "Tickets ouverts",
            "quotes_pending": "Devis en attente",
        }
        for key, label in metric_labels.items():
            val = metrics.get(key, 0)
            if key in ("ca_ytd", "unpaid"):
                ctx_lines.append(f"{label} : {val:,.0f} €")
            else:
                ctx_lines.append(f"{label} : {int(val)}")

        if timeline:
            ctx_lines += ["", "=== Derniers événements ==="]
            for ev in timeline:
                ctx_lines.append(f"- [{ev['event_type']}] {ev['title']}")

        return "\n".join(l for l in ctx_lines if l is not None)

    # ── Skills ────────────────────────────────────────────────────────────────

    def get_skills(self) -> list[str]:
        """
        # MODULE_SOCIETE: noms des fichiers skill actifs pour ce plugin.
        Les fichiers doivent exister dans skills/societe/.
        """
        return ["societe_general", "dolibarr"]

    # ── Quick prompts ─────────────────────────────────────────────────────────

    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        """
        # MODULE_SOCIETE: prompts rapides affichés dans la barre de chat.
        """
        if not company_id:
            return [
                "Résume l'état de mes sociétés",
                "Quelles sociétés ont des impayés ?",
                "Quels devis sont en attente de validation ?",
            ]

        company = company_model.get_company(company_id)
        if not company:
            return []

        return [
            f"Résume l'état de {company.name}",
            f"Quels sont les impayés de {company.name} ?",
            f"Liste les derniers documents de {company.name}",
            f"Y a-t-il des alertes pour {company.name} ?",
        ]
