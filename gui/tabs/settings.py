"""
Comprehensive Settings Tab with model selection, connection settings, and preferences.
"""

from config import LOCAL_ROUTER_PATH, RESPONDER_MODEL

import requests
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont

from qfluentwidgets import (
    ScrollArea, ExpandLayout, SettingCardGroup, PushSettingCard, FluentIcon as FIF,
    setTheme, Theme, PrimaryPushSettingCard, ComboBox, LineEdit,
    PrimaryPushButton, InfoBar, InfoBarPosition, SettingCard, Slider,
    StrongBodyLabel, SwitchButton
)

from core.settings_store import settings
from core.i18n import tr, i18n


class ModelFetcher(QThread):
    """Background thread to fetch available Ollama models."""
    models_fetched = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, ollama_url: str):
        super().__init__()
        self.ollama_url = ollama_url

    def run(self):
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = [m['name'] for m in data.get('models', [])]
                self.models_fetched.emit(models)
            else:
                self.error_occurred.emit(f"HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("Cannot connect to Ollama")
        except Exception as e:
            self.error_occurred.emit(str(e))


class ConnectionTester(QThread):
    """Background thread to test Ollama connection."""
    success = Signal()
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=5)
            if response.status_code == 200:
                self.success.emit()
            else:
                self.failed.emit(f"HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.failed.emit("Connection refused")
        except Exception as e:
            self.failed.emit(str(e))


class ComboBoxCard(SettingCard):
    """Setting card with a ComboBox for selection."""

    value_changed = Signal(str)

    def __init__(self, icon, title, description, options: list, key_path: str, parent=None):
        super().__init__(icon, title, description, parent)
        self.key_path = key_path

        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(180)
        self.combo.addItems(options)

        current = settings.get(key_path, options[0] if options else "")
        if current in options:
            self.combo.setCurrentText(current)

        self.combo.currentTextChanged.connect(self._on_changed)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, text: str):
        settings.set(self.key_path, text)
        self.value_changed.emit(text)


class LanguageCard(SettingCard):
    """Setting card with EN / FR language selector."""

    _OPTIONS = [("English", "en"), ("Français", "fr")]

    def __init__(self, parent=None):
        super().__init__(
            FIF.LANGUAGE,
            tr("settings.language"),
            tr("settings.language_desc"),
            parent
        )
        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(140)
        for label, _ in self._OPTIONS:
            self.combo.addItem(label)

        current_lang = i18n.language
        for label, code in self._OPTIONS:
            if code == current_lang:
                self.combo.setCurrentText(label)
                break

        self.combo.currentTextChanged.connect(self._on_changed)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, label: str):
        for lbl, code in self._OPTIONS:
            if lbl == label:
                i18n.set_language(code)
                break


class ModelSelectCard(SettingCard):
    """Custom setting card with a ComboBox for model selection."""

    model_changed = Signal(str)

    def __init__(self, icon, title, description, key_path: str, parent=None):
        super().__init__(icon, title, description, parent)
        self.key_path = key_path

        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(180)
        self.combo.setPlaceholderText("Select model...")

        current = settings.get(key_path, "")
        if current:
            self.combo.addItem(current)
            self.combo.setCurrentText(current)

        self.combo.currentTextChanged.connect(self._on_changed)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, text: str):
        if text:
            settings.set(self.key_path, text)
            self.model_changed.emit(text)

    def update_models(self, models: list):
        current = self.combo.currentText()
        self.combo.clear()
        self.combo.addItems(models)
        if current in models:
            self.combo.setCurrentText(current)
        elif models:
            self.combo.setCurrentIndex(0)


class UrlInputCard(SettingCard):
    """Setting card with URL input and test button."""

    def __init__(self, icon, title, description, key_path: str, parent=None):
        super().__init__(icon, title, description, parent)
        self.key_path = key_path
        self.tester = None

        self.url_input = LineEdit(self)
        self.url_input.setMinimumWidth(250)
        self.url_input.setText(settings.get(key_path, "http://localhost:11434"))
        self.url_input.textChanged.connect(self._on_url_changed)

        self.test_btn = PrimaryPushButton(tr("settings.test_btn"), self)
        self.test_btn.setFixedWidth(70)
        self.test_btn.clicked.connect(self._test_connection)

        self.hBoxLayout.addWidget(self.url_input, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.test_btn, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_url_changed(self, text: str):
        settings.set(self.key_path, text)

    def _test_connection(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("...")
        self.tester = ConnectionTester(url)
        self.tester.success.connect(self._on_test_success)
        self.tester.failed.connect(self._on_test_failed)
        self.tester.finished.connect(self._on_test_done)
        self.tester.start()

    @Slot()
    def _on_test_success(self):
        InfoBar.success(
            title=tr("infobars.connected_title"),
            content=tr("infobars.connected_content"),
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3000, parent=self.window()
        )

    @Slot(str)
    def _on_test_failed(self, error: str):
        InfoBar.error(
            title=tr("infobars.conn_failed_title"),
            content=error,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=5000, parent=self.window()
        )

    @Slot()
    def _on_test_done(self):
        self.test_btn.setEnabled(True)
        self.test_btn.setText(tr("settings.test_btn"))


class SliderCard(SettingCard):
    """Setting card with a slider and value label."""

    value_changed = Signal(int)

    def __init__(self, icon, title, description, key_path: str,
                 min_val: int, max_val: int, parent=None):
        super().__init__(icon, title, description, parent)
        self.key_path = key_path

        self.value_label = StrongBodyLabel(self)
        self.value_label.setMinimumWidth(30)

        self.slider = Slider(Qt.Horizontal, self)
        self.slider.setMinimumWidth(150)
        self.slider.setRange(min_val, max_val)

        current = settings.get(key_path, min_val)
        self.slider.setValue(current)
        self.value_label.setText(str(current))

        self.slider.valueChanged.connect(self._on_changed)

        self.hBoxLayout.addWidget(self.value_label, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, value: int):
        self.value_label.setText(str(value))
        settings.set(self.key_path, value)
        self.value_changed.emit(value)


class SwitchCard(SettingCard):
    """Setting card with a switch toggle."""

    checked_changed = Signal(bool)

    def __init__(self, icon, title, description, key_path: str, parent=None):
        super().__init__(icon, title, description, parent)
        self.key_path = key_path

        self.switch = SwitchButton(self)
        self.switch.setChecked(settings.get(key_path, False))
        self.switch.checkedChanged.connect(self._on_changed)

        self.hBoxLayout.addWidget(self.switch, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, checked: bool):
        settings.set(self.key_path, checked)
        self.checked_changed.emit(checked)


class TextInputCard(SettingCard):
    """Setting card with a text input field."""

    value_changed = Signal(str)

    def __init__(self, icon, title, description, key_path: str,
                 placeholder: str = "", parent=None):
        super().__init__(icon, title, description, parent)
        self.key_path = key_path

        self.input = LineEdit(self)
        self.input.setMinimumWidth(200)
        self.input.setPlaceholderText(placeholder)

        current = settings.get(key_path, "")
        self.input.setText(str(current))

        self.input.textChanged.connect(self._on_changed)

        self.hBoxLayout.addWidget(self.input, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, text: str):
        try:
            value = float(text) if text else text
            settings.set(self.key_path, value)
            self.value_changed.emit(text)
        except ValueError:
            settings.set(self.key_path, text)
            self.value_changed.emit(text)


class HAUrlInputCard(UrlInputCard):
    """URL input card that tests a Home Assistant /api/ endpoint instead of Ollama."""

    def _test_connection(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("...")
        self.tester = ConnectionTester(url.rstrip("/") + "/api/")
        self.tester.success.connect(self._on_test_success)
        self.tester.failed.connect(self._on_test_failed)
        self.tester.finished.connect(self._on_test_done)
        self.tester.start()


class NavidromeUrlInputCard(UrlInputCard):
    """URL input card that tests Navidrome via Subsonic ping.view."""

    def _test_connection(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("...")
        user = settings.get("navidrome.user", "")
        password = settings.get("navidrome.password", "")
        ping_url = (
            f"{url.rstrip('/')}/rest/ping.view"
            f"?u={user}&p={password}&v=1.16.0&c=ada&f=json"
        )
        self.tester = ConnectionTester(ping_url)
        self.tester.success.connect(self._on_navidrome_success)
        self.tester.failed.connect(self._on_test_failed)
        self.tester.finished.connect(self._on_test_done)
        self.tester.start()

    @Slot()
    def _on_navidrome_success(self):
        # Subsonic returns 200 even on auth failure — check the JSON
        try:
            import requests as _req
            url = self.url_input.text().strip()
            user = settings.get("navidrome.user", "")
            password = settings.get("navidrome.password", "")
            r = _req.get(
                f"{url.rstrip('/')}/rest/ping.view",
                params={"u": user, "p": password, "v": "1.16.0", "c": "ada", "f": "json"},
                timeout=5,
            )
            body = r.json()
            if body.get("subsonic-response", {}).get("status") == "ok":
                self._on_test_success()
            else:
                err = body.get("subsonic-response", {}).get("error", {}).get("message", "auth failed")
                self._on_test_failed(err)
        except Exception as e:
            self._on_test_failed(str(e))


class SettingsTab(ScrollArea):
    """Comprehensive Settings Tab with model selection and preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        self.setStyleSheet("background-color: transparent;")
        self.scrollWidget.setObjectName("scrollWidget")

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        self.model_fetcher = None
        self._available_models = []

        self._init_ui()
        self._fetch_models()

    def _init_ui(self):
        # ── Personalization ───────────────────────────────────────────
        self.personal_group = SettingCardGroup(tr("settings.personalization"), self.scrollWidget)

        self.theme_card = ComboBoxCard(
            FIF.BRUSH,
            tr("settings.theme"),
            tr("settings.theme_desc"),
            ["Light", "Dark", "Auto"],
            "theme",
            self.personal_group
        )
        self.theme_card.value_changed.connect(self._on_theme_changed)
        self.personal_group.addSettingCard(self.theme_card)

        self.language_card = LanguageCard(self.personal_group)
        self.personal_group.addSettingCard(self.language_card)

        self.expandLayout.addWidget(self.personal_group)

        # ── AI Models ─────────────────────────────────────────────────
        self.ai_group = SettingCardGroup(tr("settings.ai_models"), self.scrollWidget)

        self.chat_model_card = ModelSelectCard(
            FIF.CHAT,
            tr("settings.chat_model"),
            tr("settings.chat_model_desc"),
            "models.chat",
            self.ai_group
        )
        self.ai_group.addSettingCard(self.chat_model_card)

        self.web_agent_model_card = ModelSelectCard(
            FIF.GLOBE,
            tr("settings.web_agent_model"),
            tr("settings.web_agent_model_desc"),
            "models.web_agent",
            self.ai_group
        )
        self.ai_group.addSettingCard(self.web_agent_model_card)

        self.router_model_card = SettingCard(
            FIF.ROBOT,
            tr("settings.router_model"),
            f"Local FunctionGemma model at: {LOCAL_ROUTER_PATH}",
            self.ai_group
        )
        self.ai_group.addSettingCard(self.router_model_card)

        self.refresh_models_card = PushSettingCard(
            tr("settings.refresh_btn"),
            FIF.SYNC,
            tr("settings.refresh_models"),
            tr("settings.refresh_models_desc"),
            self.ai_group
        )
        self.refresh_models_card.clicked.connect(self._fetch_models)
        self.ai_group.addSettingCard(self.refresh_models_card)
        self.expandLayout.addWidget(self.ai_group)

        # ── Connection ────────────────────────────────────────────────
        self.connection_group = SettingCardGroup(tr("settings.connection"), self.scrollWidget)

        self.ollama_url_card = UrlInputCard(
            FIF.LINK,
            tr("settings.ollama_url"),
            tr("settings.ollama_url_desc"),
            "ollama_url",
            self.connection_group
        )
        self.connection_group.addSettingCard(self.ollama_url_card)
        self.expandLayout.addWidget(self.connection_group)

        # ── Kasa ─────────────────────────────────────────────────────────
        self.kasa_group = SettingCardGroup(tr("settings.kasa"), self.scrollWidget)

        self.kasa_enabled_card = SwitchCard(
            FIF.WIFI,
            tr("settings.kasa_enabled"),
            tr("settings.kasa_enabled_desc"),
            "kasa.enabled",
            self.kasa_group
        )
        self.kasa_group.addSettingCard(self.kasa_enabled_card)

        self.kasa_test_card = PushSettingCard(
            tr("settings.kasa_test_btn"),
            FIF.SEARCH,
            tr("settings.kasa_test"),
            tr("settings.kasa_test_desc"),
            self.kasa_group
        )
        self.kasa_test_card.clicked.connect(self._on_kasa_scan)
        self.kasa_group.addSettingCard(self.kasa_test_card)
        self.expandLayout.addWidget(self.kasa_group)

        # ── Navidrome ─────────────────────────────────────────────────
        self.navidrome_group = SettingCardGroup(tr("settings.navidrome"), self.scrollWidget)

        self.navidrome_url_card = NavidromeUrlInputCard(
            FIF.MUSIC,
            tr("settings.navidrome_url"),
            tr("settings.navidrome_url_desc"),
            "navidrome.url",
            self.navidrome_group
        )
        self.navidrome_url_card.url_input.setText(
            settings.get("navidrome.url", "http://localhost:4533")
        )
        self.navidrome_group.addSettingCard(self.navidrome_url_card)

        self.navidrome_user_card = TextInputCard(
            FIF.PEOPLE,
            tr("settings.navidrome_user"),
            tr("settings.navidrome_user_desc"),
            "navidrome.user",
            "admin",
            self.navidrome_group
        )
        self.navidrome_group.addSettingCard(self.navidrome_user_card)

        self.navidrome_password_card = TextInputCard(
            FIF.HIDE,
            tr("settings.navidrome_password"),
            tr("settings.navidrome_password_desc"),
            "navidrome.password",
            "••••••••",
            self.navidrome_group
        )
        self.navidrome_password_card.input.setEchoMode(LineEdit.EchoMode.Password)
        self.navidrome_group.addSettingCard(self.navidrome_password_card)
        self.expandLayout.addWidget(self.navidrome_group)

        # ── Home Assistant ────────────────────────────────────────────
        self.ha_group = SettingCardGroup(tr("settings.ha"), self.scrollWidget)

        self.ha_enabled_card = SwitchCard(
            FIF.WIFI,
            tr("settings.ha_enabled"),
            tr("settings.ha_enabled_desc"),
            "home_assistant.enabled",
            self.ha_group
        )
        self.ha_group.addSettingCard(self.ha_enabled_card)

        self.ha_url_card = HAUrlInputCard(
            FIF.LINK,
            tr("settings.ha_url"),
            tr("settings.ha_url_desc"),
            "home_assistant.url",
            self.ha_group
        )
        self.ha_group.addSettingCard(self.ha_url_card)

        self.ha_token_card = TextInputCard(
            FIF.EDIT,
            tr("settings.ha_token"),
            tr("settings.ha_token_desc"),
            "home_assistant.token",
            "eyJ0eXAiOiJKV1Q...",
            self.ha_group
        )
        self.ha_group.addSettingCard(self.ha_token_card)
        self.expandLayout.addWidget(self.ha_group)

        # ── Voice & Audio ─────────────────────────────────────────────
        self.voice_group = SettingCardGroup(tr("settings.voice"), self.scrollWidget)
        piper_voices = self._discover_piper_voices()
        self.tts_voice_card = ComboBoxCard(
            FIF.VOLUME,
            tr("settings.tts_voice"),
            tr("settings.tts_voice_desc", count=len(piper_voices)),
            piper_voices,
            "tts.voice",
            self.voice_group
        )
        self.voice_group.addSettingCard(self.tts_voice_card)
        self.expandLayout.addWidget(self.voice_group)

        # ── Telegram ──────────────────────────────────────────────────
        self.telegram_group = SettingCardGroup(tr("settings.telegram"), self.scrollWidget)

        self.telegram_enabled_card = SwitchCard(
            FIF.SEND,
            tr("settings.telegram_enabled"),
            tr("settings.telegram_enabled_desc"),
            "telegram.enabled",
            self.telegram_group
        )
        self.telegram_enabled_card.checked_changed.connect(self._on_telegram_toggled)
        self.telegram_group.addSettingCard(self.telegram_enabled_card)

        self.telegram_token_card = TextInputCard(
            FIF.EDIT,
            tr("settings.telegram_token"),
            tr("settings.telegram_token_desc"),
            "telegram.token",
            "123456789:ABCdefGHIjklMNOpqrStUVwxYZ",
            self.telegram_group
        )
        self.telegram_group.addSettingCard(self.telegram_token_card)

        self.telegram_owner_card = TextInputCard(
            FIF.PEOPLE,
            tr("settings.telegram_owner"),
            tr("settings.telegram_owner_desc"),
            "telegram.owner_chat_id",
            "123456789",
            self.telegram_group
        )
        self.telegram_group.addSettingCard(self.telegram_owner_card)
        self.expandLayout.addWidget(self.telegram_group)

        # ── Morning Briefing ──────────────────────────────────────────
        self.briefing_group = SettingCardGroup(tr("settings.briefing"), self.scrollWidget)

        self.briefing_enabled_card = SwitchCard(
            FIF.CALENDAR,
            tr("settings.briefing_enabled"),
            tr("settings.briefing_enabled_desc"),
            "briefing.enabled",
            self.briefing_group
        )
        self.briefing_group.addSettingCard(self.briefing_enabled_card)

        self.briefing_hour_card = ComboBoxCard(
            FIF.HISTORY,
            tr("settings.briefing_hour"),
            tr("settings.briefing_hour_desc"),
            ["5h", "6h", "7h", "8h", "9h", "10h"],
            "briefing.hour_label",
            self.briefing_group
        )
        self.briefing_hour_card.value_changed.connect(self._on_briefing_hour_changed)
        self.briefing_group.addSettingCard(self.briefing_hour_card)

        self.briefing_test_card = PushSettingCard(
            tr("settings.briefing_test_btn"),
            FIF.SEND,
            tr("settings.briefing_test"),
            tr("settings.briefing_test_desc"),
            self.briefing_group
        )
        self.briefing_test_card.clicked.connect(self._on_briefing_test)
        self.briefing_group.addSettingCard(self.briefing_test_card)
        self.expandLayout.addWidget(self.briefing_group)

        # ── Weather Location ──────────────────────────────────────────
        self.weather_group = SettingCardGroup(tr("settings.weather"), self.scrollWidget)

        self.city_card = TextInputCard(
            FIF.PIN,
            tr("settings.city"),
            tr("settings.city_desc"),
            "weather.city",
            "New York, NY",
            self.weather_group
        )
        self.weather_group.addSettingCard(self.city_card)

        self.latitude_card = TextInputCard(
            FIF.PIN,
            tr("settings.latitude"),
            tr("settings.latitude_desc"),
            "weather.latitude",
            "40.7128",
            self.weather_group
        )
        self.weather_group.addSettingCard(self.latitude_card)

        self.longitude_card = TextInputCard(
            FIF.GLOBE,
            tr("settings.longitude"),
            tr("settings.longitude_desc"),
            "weather.longitude",
            "-74.0060",
            self.weather_group
        )
        self.weather_group.addSettingCard(self.longitude_card)
        self.expandLayout.addWidget(self.weather_group)

        # ── General ───────────────────────────────────────────────────
        self.general_group = SettingCardGroup(tr("settings.general"), self.scrollWidget)

        self.max_history_card = SliderCard(
            FIF.HISTORY,
            tr("settings.max_history"),
            tr("settings.max_history_desc"),
            "general.max_history",
            5, 50,
            self.general_group
        )
        self.general_group.addSettingCard(self.max_history_card)

        self.auto_news_card = SwitchCard(
            FIF.DOCUMENT,
            tr("settings.auto_news"),
            tr("settings.auto_news_desc"),
            "general.auto_fetch_news",
            self.general_group
        )
        self.general_group.addSettingCard(self.auto_news_card)
        self.expandLayout.addWidget(self.general_group)

        # ── About ─────────────────────────────────────────────────────
        self.about_group = SettingCardGroup(tr("settings.about"), self.scrollWidget)

        self.about_card = PrimaryPushSettingCard(
            tr("settings.about_btn"),
            FIF.INFO,
            "About A.D.A",
            tr("settings.about_desc"),
            self.about_group
        )
        self.about_group.addSettingCard(self.about_card)

        self.reset_card = PushSettingCard(
            tr("settings.reset_btn"),
            FIF.CANCEL,
            tr("settings.reset"),
            tr("settings.reset_desc"),
            self.about_group
        )
        self.reset_card.clicked.connect(self._on_reset)
        self.about_group.addSettingCard(self.reset_card)
        self.expandLayout.addWidget(self.about_group)

        # Connect language changes → retranslate in-place
        i18n.language_changed.connect(self.retranslate_ui)

    # ── Retranslation ─────────────────────────────────────────────────

    def retranslate_ui(self, _lang: str = ""):
        """Update all card labels in-place when language changes (no rebuild needed)."""
        self.personal_group.titleLabel.setText(tr("settings.personalization"))
        self.ai_group.titleLabel.setText(tr("settings.ai_models"))
        self.connection_group.titleLabel.setText(tr("settings.connection"))
        self.kasa_group.titleLabel.setText(tr("settings.kasa"))
        self.navidrome_group.titleLabel.setText(tr("settings.navidrome"))
        self.ha_group.titleLabel.setText(tr("settings.ha"))
        self.voice_group.titleLabel.setText(tr("settings.voice"))
        self.telegram_group.titleLabel.setText(tr("settings.telegram"))
        self.briefing_group.titleLabel.setText(tr("settings.briefing"))
        self.weather_group.titleLabel.setText(tr("settings.weather"))
        self.general_group.titleLabel.setText(tr("settings.general"))
        self.about_group.titleLabel.setText(tr("settings.about"))

        self.theme_card.titleLabel.setText(tr("settings.theme"))
        self.theme_card.contentLabel.setText(tr("settings.theme_desc"))
        self.language_card.titleLabel.setText(tr("settings.language"))
        self.language_card.contentLabel.setText(tr("settings.language_desc"))

        self.chat_model_card.titleLabel.setText(tr("settings.chat_model"))
        self.chat_model_card.contentLabel.setText(tr("settings.chat_model_desc"))
        self.web_agent_model_card.titleLabel.setText(tr("settings.web_agent_model"))
        self.web_agent_model_card.contentLabel.setText(tr("settings.web_agent_model_desc"))
        self.router_model_card.titleLabel.setText(tr("settings.router_model"))
        self.refresh_models_card.titleLabel.setText(tr("settings.refresh_models"))
        self.refresh_models_card.contentLabel.setText(tr("settings.refresh_models_desc"))
        self.refresh_models_card.button.setText(tr("settings.refresh_btn"))

        self.ollama_url_card.titleLabel.setText(tr("settings.ollama_url"))
        self.ollama_url_card.contentLabel.setText(tr("settings.ollama_url_desc"))
        self.ollama_url_card.test_btn.setText(tr("settings.test_btn"))

        self.kasa_enabled_card.titleLabel.setText(tr("settings.kasa_enabled"))
        self.kasa_enabled_card.contentLabel.setText(tr("settings.kasa_enabled_desc"))
        self.kasa_test_card.titleLabel.setText(tr("settings.kasa_test"))
        self.kasa_test_card.contentLabel.setText(tr("settings.kasa_test_desc"))
        self.kasa_test_card.button.setText(tr("settings.kasa_test_btn"))

        self.navidrome_url_card.titleLabel.setText(tr("settings.navidrome_url"))
        self.navidrome_url_card.contentLabel.setText(tr("settings.navidrome_url_desc"))
        self.navidrome_url_card.test_btn.setText(tr("settings.test_btn"))
        self.navidrome_user_card.titleLabel.setText(tr("settings.navidrome_user"))
        self.navidrome_user_card.contentLabel.setText(tr("settings.navidrome_user_desc"))
        self.navidrome_password_card.titleLabel.setText(tr("settings.navidrome_password"))
        self.navidrome_password_card.contentLabel.setText(tr("settings.navidrome_password_desc"))

        self.ha_enabled_card.titleLabel.setText(tr("settings.ha_enabled"))
        self.ha_enabled_card.contentLabel.setText(tr("settings.ha_enabled_desc"))
        self.ha_url_card.titleLabel.setText(tr("settings.ha_url"))
        self.ha_url_card.contentLabel.setText(tr("settings.ha_url_desc"))
        self.ha_url_card.test_btn.setText(tr("settings.test_btn"))
        self.ha_token_card.titleLabel.setText(tr("settings.ha_token"))
        self.ha_token_card.contentLabel.setText(tr("settings.ha_token_desc"))

        self.tts_voice_card.titleLabel.setText(tr("settings.tts_voice"))

        self.telegram_enabled_card.titleLabel.setText(tr("settings.telegram_enabled"))
        self.telegram_enabled_card.contentLabel.setText(tr("settings.telegram_enabled_desc"))
        self.telegram_token_card.titleLabel.setText(tr("settings.telegram_token"))
        self.telegram_token_card.contentLabel.setText(tr("settings.telegram_token_desc"))
        self.telegram_owner_card.titleLabel.setText(tr("settings.telegram_owner"))
        self.telegram_owner_card.contentLabel.setText(tr("settings.telegram_owner_desc"))

        self.briefing_enabled_card.titleLabel.setText(tr("settings.briefing_enabled"))
        self.briefing_enabled_card.contentLabel.setText(tr("settings.briefing_enabled_desc"))
        self.briefing_hour_card.titleLabel.setText(tr("settings.briefing_hour"))
        self.briefing_hour_card.contentLabel.setText(tr("settings.briefing_hour_desc"))
        self.briefing_test_card.titleLabel.setText(tr("settings.briefing_test"))
        self.briefing_test_card.contentLabel.setText(tr("settings.briefing_test_desc"))
        self.briefing_test_card.button.setText(tr("settings.briefing_test_btn"))

        self.city_card.titleLabel.setText(tr("settings.city"))
        self.city_card.contentLabel.setText(tr("settings.city_desc"))
        self.latitude_card.titleLabel.setText(tr("settings.latitude"))
        self.latitude_card.contentLabel.setText(tr("settings.latitude_desc"))
        self.longitude_card.titleLabel.setText(tr("settings.longitude"))
        self.longitude_card.contentLabel.setText(tr("settings.longitude_desc"))

        self.max_history_card.titleLabel.setText(tr("settings.max_history"))
        self.max_history_card.contentLabel.setText(tr("settings.max_history_desc"))
        self.auto_news_card.titleLabel.setText(tr("settings.auto_news"))
        self.auto_news_card.contentLabel.setText(tr("settings.auto_news_desc"))

        self.about_card.contentLabel.setText(tr("settings.about_desc"))
        self.about_card.button.setText(tr("settings.about_btn"))
        self.reset_card.titleLabel.setText(tr("settings.reset"))
        self.reset_card.contentLabel.setText(tr("settings.reset_desc"))
        self.reset_card.button.setText(tr("settings.reset_btn"))

        InfoBar.info(
            title=tr("infobars.lang_changed_title"),
            content=tr("infobars.lang_changed_content"),
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=4000,
            parent=self.window()
        )

    # ── Callbacks ─────────────────────────────────────────────────────

    def _on_theme_changed(self, value: str):
        theme_map = {"Dark": Theme.DARK, "Light": Theme.LIGHT, "Auto": Theme.AUTO}
        setTheme(theme_map.get(value, Theme.DARK))

    def _on_reset(self):
        settings.reset_to_defaults()
        InfoBar.success(
            title=tr("infobars.reset_title"),
            content=tr("infobars.reset_content"),
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=5000, parent=self.window()
        )

    def _fetch_models(self):
        url = settings.get("ollama_url", "http://localhost:11434")
        self.model_fetcher = ModelFetcher(url)
        self.model_fetcher.models_fetched.connect(self._on_models_fetched)
        self.model_fetcher.error_occurred.connect(self._on_models_error)
        self.model_fetcher.start()

    @Slot(list)
    def _on_models_fetched(self, models: list):
        self._available_models = models
        self.chat_model_card.update_models(models)
        self.web_agent_model_card.update_models(models)
        InfoBar.success(
            title=tr("infobars.models_loaded_title"),
            content=tr("infobars.models_loaded_content", count=len(models)),
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=2000, parent=self.window()
        )

    @Slot(str)
    def _on_models_error(self, error: str):
        InfoBar.warning(
            title=tr("infobars.models_error_title"),
            content=error,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=4000, parent=self.window()
        )

    def _on_briefing_hour_changed(self, label: str):
        hour = int(label.replace("h", ""))
        settings.set("briefing.hour", hour)

    def _on_briefing_test(self):
        self.briefing_test_card.button.setEnabled(False)
        self.briefing_test_card.button.setText(tr("settings.briefing_generating"))

        import threading
        def _run():
            from core.morning_briefing import generate_briefing, deliver_briefing
            text = generate_briefing()
            deliver_briefing(text)
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_on_briefing_test_done", Qt.QueuedConnection)

        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def _on_briefing_test_done(self):
        self.briefing_test_card.button.setEnabled(True)
        self.briefing_test_card.button.setText(tr("settings.briefing_test_btn"))
        InfoBar.success(
            title=tr("infobars.briefing_sent_title"),
            content=tr("infobars.briefing_sent_content"),
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3000, parent=self.window()
        )

    def _on_kasa_scan(self):
        self.kasa_test_card.button.setEnabled(False)
        self.kasa_test_card.button.setText(tr("settings.kasa_scanning"))

        import threading

        def _run():
            from core.providers.kasa_provider import kasa_provider
            result = kasa_provider.fetch_entities()
            self._kasa_scan_count = len(result)
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_on_kasa_scan_done", Qt.QueuedConnection)

        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def _on_kasa_scan_done(self):
        self.kasa_test_card.button.setEnabled(True)
        self.kasa_test_card.button.setText(tr("settings.kasa_test_btn"))
        count = getattr(self, "_kasa_scan_count", 0)
        if count > 0:
            InfoBar.success(
                title=tr("settings.kasa"),
                content=tr("settings.kasa_found", count=count),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self.window()
            )
        else:
            InfoBar.warning(
                title=tr("settings.kasa"),
                content=tr("settings.kasa_none"),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self.window()
            )

    def _on_telegram_toggled(self, enabled: bool):
        from core.telegram_adapter import telegram_adapter
        if enabled:
            telegram_adapter.restart()
            InfoBar.success(
                title=tr("infobars.telegram_on_title"),
                content=tr("infobars.telegram_on_content"),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window()
            )
        else:
            telegram_adapter.stop()
            InfoBar.info(
                title=tr("infobars.telegram_off_title"),
                content=tr("infobars.telegram_off_content"),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2000, parent=self.window()
            )

    def _discover_piper_voices(self) -> list:
        from pathlib import Path
        voices_dir = Path.home() / ".local" / "share" / "piper" / "voices"
        if not voices_dir.exists():
            return ["fr_FR-siwis-medium"]
        voices = sorted(p.stem for p in voices_dir.glob("*.onnx"))
        return voices if voices else ["fr_FR-siwis-medium"]
