"""
Plugin Registry — système de plugins pour ADA.

# MODULE_SOCIETE: ce fichier est le cœur du système de plugins.
# Chaque plugin hérite de BasePlugin et s'enregistre dans PluginRegistry.
# Guard : si MODULES_ENABLED["societe"] = False, le plugin SocietePlugin
# n'est pas enregistré et toute l'UI/logic societe est inactive.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ── Base ──────────────────────────────────────────────────────────────────────

class BasePlugin(ABC):
    """Interface commune à tous les plugins ADA."""

    # Identifiant unique (snake_case), ex : "societe"
    plugin_id: str = ""

    # Libellé affiché dans la nav
    display_name: str = ""

    # Icône (emoji ou chemin ressource)
    icon: str = "🔌"

    # Univers d'appartenance — "home" | "opent" | "uscss" | "margep" | "global"
    universe: str = "global"

    # Couleur d'accentuation hex pour l'UI
    color: str = "#8b9bb4"

    @abstractmethod
    def get_nav_items(self) -> list[dict]:
        """
        Retourne la liste des items à ajouter à la navigation.
        Chaque item : {"label": str, "icon": str, "route": str}
        """
        ...

    @abstractmethod
    def get_chat_context(self, company_id: str | None = None) -> str:
        """
        Retourne le bloc de contexte à injecter dans le system prompt du chat.
        """
        ...

    @abstractmethod
    def get_skills(self) -> list[str]:
        """
        Retourne les noms des fichiers skill à activer (dans skills/<plugin_id>/).
        """
        ...

    @abstractmethod
    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        """
        Retourne les quick-prompts à afficher dans la barre de chat.
        """
        ...

    def on_enable(self) -> None:
        """Appelé quand le plugin est activé (optionnel)."""

    def on_disable(self) -> None:
        """Appelé quand le plugin est désactivé (optionnel)."""

    # ── Nouvelles méthodes optionnelles ───────────────────────────────────────

    def get_function_definitions(self) -> list[dict]:
        """
        Définitions de fonctions au format JSON Schema Ollama injectées dans
        le tool-calling LLM quand le plugin est actif.
        """
        return []

    def get_semantic_utterances(self) -> dict[str, list[str]]:
        """
        Utterances à fusionner dans le semantic_router.
        Clé = route cible (ex: "function_gemma"), valeur = liste de phrases.
        """
        return {}

    def get_n8n_webhooks(self) -> dict[str, str]:
        """
        Mapping action (kebab-case) → URL de webhook n8n.
        """
        return {}

    def handle_action(self, action: str, params: dict) -> dict:
        """
        Exécution locale d'une action (fallback si n8n indisponible).
        Retourne { success: bool, message: str, data: Any }.
        N'est appelé que si l'action figure dans get_function_definitions()
        ET que n8n est indisponible ou ne couvre pas cette action.
        """
        return {"success": False, "message": f"Action {action} non implémentée", "data": None}

    def get_system_prompt_injection(self, context_id: str | None = None) -> str:
        """
        Bloc texte injecté dans le system prompt du LLM quand ce plugin est actif.
        Décrit les capacités d'action disponibles.
        """
        return ""

    def get_dashboard_kpis(self) -> list[dict]:
        """
        KPIs à afficher dans le dashboard global.
        Chaque KPI : { id, label, value, unit?, trend?, color?, tab_link? }
        """
        return []


# ── Registry ──────────────────────────────────────────────────────────────────

class PluginRegistry:
    """Registre singleton de tous les plugins actifs."""

    _instance: "PluginRegistry | None" = None

    def __new__(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: dict[str, BasePlugin] = {}
        return cls._instance

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, plugin: BasePlugin) -> None:
        """Enregistre un plugin. Idempotent."""
        if plugin.plugin_id in self._plugins:
            return
        self._plugins[plugin.plugin_id] = plugin
        plugin.on_enable()
        print(f"[PluginRegistry] ✓ Plugin '{plugin.plugin_id}' enregistré")

    def unregister(self, plugin_id: str) -> None:
        """Désenregistre un plugin proprement."""
        plugin = self._plugins.pop(plugin_id, None)
        if plugin:
            plugin.on_disable()
            print(f"[PluginRegistry] Plugin '{plugin_id}' désactivé")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, plugin_id: str) -> BasePlugin | None:
        return self._plugins.get(plugin_id)

    def all(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def is_active(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    # ── Aggregated helpers ────────────────────────────────────────────────────

    def all_nav_items(self) -> list[dict]:
        items = []
        for p in self._plugins.values():
            items.extend(p.get_nav_items())
        return items

    def combined_chat_context(self, company_id: str | None = None) -> str:
        parts = [p.get_chat_context(company_id) for p in self._plugins.values()]
        return "\n\n".join(p for p in parts if p.strip())

    def combined_function_definitions(self) -> list[dict]:
        """Agrège toutes les function definitions des plugins actifs."""
        definitions = []
        for p in self._plugins.values():
            definitions.extend(p.get_function_definitions())
        return definitions

    def combined_n8n_webhooks(self) -> dict[str, str]:
        """Agrège les webhooks de tous les plugins actifs."""
        webhooks: dict[str, str] = {}
        for p in self._plugins.values():
            webhooks.update(p.get_n8n_webhooks())
        return webhooks

    def combined_system_prompt_injection(self, context_id: str | None = None) -> str:
        """Agrège les injections system prompt de tous les plugins actifs."""
        parts = [p.get_system_prompt_injection(context_id) for p in self._plugins.values()]
        return "\n\n".join(p for p in parts if p.strip())

    def dispatch_action(self, action: str, params: dict) -> dict | None:
        """
        Cherche le plugin qui déclare cette action dans get_function_definitions().
        Retourne None si aucun plugin ne la reconnaît (fallback FunctionExecutor).
        """
        for p in self._plugins.values():
            func_names = [
                f["function"]["name"]
                for f in p.get_function_definitions()
            ]
            if action in func_names:
                return p.handle_action(action, params)
        return None

    def combined_semantic_utterances(self) -> dict[str, list[str]]:
        """Agrège les utterances de tous les plugins actifs pour le semantic_router."""
        result: dict[str, list[str]] = {}
        for p in self._plugins.values():
            for route, utterances in p.get_semantic_utterances().items():
                result.setdefault(route, []).extend(utterances)
        return result


# Singleton global
plugin_registry = PluginRegistry()


# ── Auto-registration ─────────────────────────────────────────────────────────

def register_enabled_plugins() -> None:
    """
    Enregistre les plugins dont le flag est True dans MODULES_ENABLED.
    settings_store.modules.<key> prend la priorité sur config.MODULES_ENABLED.
    """
    from config import MODULES_ENABLED  # import tardif pour éviter la circularité
    from core.settings_store import settings as _settings

    def _is_enabled(key: str) -> bool:
        store_val = _settings.get(f"modules.{key}")
        return store_val if store_val is not None else MODULES_ENABLED.get(key, False)

    # MODULE_SOCIETE
    if _is_enabled("societe"):
        from core.societe.plugin import SocietePlugin
        plugin_registry.register(SocietePlugin())
    else:
        print("[PluginRegistry] Module 'societe' désactivé")

    # MODULE_DOMOTIQUE
    if _is_enabled("domotique"):
        from core.domotique.plugin import DomotiquePlugin
        plugin_registry.register(DomotiquePlugin())
    else:
        print("[PluginRegistry] Module 'domotique' désactivé")

    # MODULE_PROXMOX
    if _is_enabled("proxmox"):
        from core.infra.plugin import ProxmoxPlugin
        plugin_registry.register(ProxmoxPlugin())
    else:
        print("[PluginRegistry] Module 'proxmox' désactivé")

    # MODULE_RMM
    if _is_enabled("rmm"):
        from core.rmm.plugin import RmmPlugin
        plugin_registry.register(RmmPlugin())
    else:
        print("[PluginRegistry] Module 'rmm' désactivé")

    # MODULE_TELEPHONY
    if _is_enabled("telephony"):
        from core.telephony.plugin import TelephonyPlugin
        plugin_registry.register(TelephonyPlugin())

    # MODULE_MARGEPRO
    if _is_enabled("margepro"):
        from core.margepro.plugin import MargeProPlugin
        plugin_registry.register(MargeProPlugin())
    else:
        print("[PluginRegistry] Module 'margepro' désactivé")
