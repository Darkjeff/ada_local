"""
Centralized i18n engine for ADA.

Usage:
    from core.i18n import tr, i18n
    label = tr("settings.theme")
    i18n.set_language("fr")
    i18n.language_changed.connect(my_widget.retranslate_ui)
"""

import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal

from core.settings_store import settings as _app_settings


class I18nEngine(QObject):
    language_changed = Signal(str)   # emits new lang code: "en" or "fr"

    SUPPORTED = {"en", "fr"}
    DEFAULT = "en"
    _LOCALES_DIR = Path(__file__).parent.parent / "locales"

    def __init__(self):
        super().__init__()
        self._lang: str = self.DEFAULT
        self._strings: dict = {}
        lang = _app_settings.get("app.language", self.DEFAULT)
        self._load(lang)

    # ── Internal ──────────────────────────────────────────────────────

    def _load(self, lang: str):
        lang = lang if lang in self.SUPPORTED else self.DEFAULT
        path = self._LOCALES_DIR / f"{lang}.json"
        try:
            with open(path, encoding="utf-8") as f:
                self._strings = json.load(f)
            self._lang = lang
        except FileNotFoundError:
            if lang != self.DEFAULT:
                self._load(self.DEFAULT)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str):
        """Switch language, persist, and notify all connected slots."""
        if lang == self._lang:
            return
        self._load(lang)
        _app_settings.set("app.language", lang)
        self.language_changed.emit(lang)

    def get(self, key: str, **kwargs) -> str:
        """
        Resolve a dotted key, e.g. 'settings.theme'.
        Falls back to the key itself if not found.
        Supports str.format() placeholders: tr('x', count=3).
        """
        parts = key.split(".")
        node = self._strings
        for part in parts:
            if not isinstance(node, dict):
                return key
            node = node.get(part, key)
        result = node if isinstance(node, str) else key
        if kwargs:
            try:
                result = result.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return result


# ── Module-level singleton ────────────────────────────────────────────
i18n = I18nEngine()


def tr(key: str, **kwargs) -> str:
    """Global shorthand for i18n.get()."""
    return i18n.get(key, **kwargs)


def ai_lang() -> str:
    """
    Returns the language code for AI responses ("fr" or "en"),
    based on the app.language setting.
    """
    return i18n.language


def ai_lang_instruction() -> str:
    """
    Returns a language directive to inject into LLM / vision prompts.
    Adapts automatically when the user switches language in Settings.
    """
    if i18n.language == "en":
        return "Respond in English. Be concise and precise."
    return "Réponds en français. Sois concis et précis."
