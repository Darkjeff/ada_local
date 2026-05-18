"""Tests that the n8n settings block is present in DEFAULT_SETTINGS."""
import pytest
from core.settings_store import DEFAULT_SETTINGS


def test_n8n_block_exists():
    assert "n8n" in DEFAULT_SETTINGS


def test_n8n_url_default():
    assert DEFAULT_SETTINGS["n8n"]["url"] == "http://localhost:5678"


def test_n8n_timeout_default():
    assert DEFAULT_SETTINGS["n8n"]["timeout_s"] == 10.0


def test_n8n_fallback_default():
    assert DEFAULT_SETTINGS["n8n"]["fallback_enabled"] is True


def test_n8n_cooldown_default():
    assert DEFAULT_SETTINGS["n8n"]["cooldown_s"] == 30.0
