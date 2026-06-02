"""
Morning Briefing — daily digest assembled from weather, news and memory,
formatted by the LLM and delivered via Telegram.

Runs automatically at a configurable hour (default 7:00 AM).
Can also be triggered manually from the Settings UI.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import OLLAMA_URL, RESPONDER_MODEL
from core.memory_store import memory_store
from core.settings_store import settings

def _system_prompt() -> str:
    name = settings.get("user.name", "vous")
    return (
        f"Tu es ADA, une assistante IA. Tu génères un briefing matinal concis et agréable pour {name}.\n"
        "Utilise des emojis appropriés, sois chaleureuse et directe.\n"
        "Structure : salutation personnalisée + météo + 3-4 actualités importantes + rappel mémoire si pertinent + mot motivant.\n"
        "Maximum 250 mots. Réponds uniquement en français."
    )


def _f_to_c(f: float) -> float:
    return round((f - 32) * 5 / 9, 1)


def generate_briefing() -> str:
    """
    Collect weather + news + memory, ask LLM to format a morning briefing.
    Falls back to plain-text assembly if LLM is unavailable.
    """
    sections: list[str] = []

    # ── Weather ───────────────────────────────────────────────────────────────
    try:
        from core.weather import weather_manager
        weather = weather_manager.get_weather()
        if weather:
            temp_c = _f_to_c(weather.get("temp", 0))
            high_c = _f_to_c(weather.get("high", 0))
            low_c  = _f_to_c(weather.get("low", 0))
            condition = weather_manager._code_to_text(weather.get("code", 0))
            city = settings.get("weather.city", "ta ville")
            sections.append(
                f"Météo à {city} : {temp_c}°C ({condition}), "
                f"min {low_c}°C / max {high_c}°C"
            )
            forecast = weather.get("forecast", [])
            if forecast:
                fcst = " | ".join(
                    f"{f['time']} {_f_to_c(f['temp']):.0f}°C"
                    for f in forecast[:3]
                )
                sections.append(f"Prévisions : {fcst}")
    except Exception as e:
        print(f"[Briefing] Weather error: {e}")

    # ── News ──────────────────────────────────────────────────────────────────
    try:
        import feedparser
        feed = feedparser.parse(
            "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr"
        )
        headlines = [e.get("title", "") for e in feed.entries[:5] if e.get("title")]
        if headlines:
            sections.append(
                "Actualités du jour :\n" + "\n".join(f"• {h}" for h in headlines)
            )
    except Exception as e:
        print(f"[Briefing] News error: {e}")

    # ── Memory ────────────────────────────────────────────────────────────────
    try:
        consolidated = memory_store.get_consolidated(days=3)
        if consolidated:
            recent = consolidated[0]
            sections.append(
                f"Dernière session mémorisée ({recent['date']}) : "
                f"{recent['summary'][:160]}"
            )
    except Exception as e:
        print(f"[Briefing] Memory error: {e}")

    # ── LLM formatting ────────────────────────────────────────────────────────
    now = datetime.now()
    day_fr = ["lundi", "mardi", "mercredi", "jeudi",
              "vendredi", "samedi", "dimanche"][now.weekday()]
    months = ["janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    date_str = f"{day_fr} {now.day} {months[now.month - 1]} {now.year}"

    context = "\n\n".join(sections) if sections else "(Aucune donnée disponible)"
    prompt = (
        f"Nous sommes le {date_str} à {now.strftime('%H:%M')}.\n\n"
        f"Données :\n{context}\n\n"
        f"Génère le briefing matinal pour {settings.get('user.name', 'moi')}."
    )

    try:
        r = requests.post(
            f"{OLLAMA_URL}/chat",
            json={
                "model": RESPONDER_MODEL,
                "messages": [
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "keep_alive": "5m",
            },
            timeout=120,
        )
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
        if text:
            return text
    except Exception as e:
        print(f"[Briefing] LLM error: {e}")

    # Fallback: plain assembly
    return f"🌅 Briefing du {date_str}\n\n" + "\n\n".join(sections)


def deliver_briefing(text: str):
    """Send briefing via Telegram DM to the configured owner chat ID."""
    if not settings.get("telegram.enabled", False):
        return
    owner_id = settings.get("telegram.owner_chat_id", "")
    if not owner_id:
        print("[Briefing] telegram.owner_chat_id not set — cannot deliver.")
        return
    try:
        from core.telegram_adapter import telegram_adapter
        telegram_adapter._send(int(owner_id), f"🌅 *Briefing matinal*\n\n{text}")
        print("[Briefing] Delivered via Telegram.")
    except Exception as e:
        print(f"[Briefing] Telegram delivery error: {e}")


# ── Scheduler ─────────────────────────────────────────────────────────────────

_scheduler_started = False


def start_morning_scheduler(hour: int = 7):
    """
    Start a daemon thread that fires the morning briefing every day at `hour:00`.
    Safe to call multiple times — only starts once.
    """
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _runner():
        print(f"[Briefing] Scheduler started — fires at {hour:02d}:00.")
        while True:
            now = datetime.now()
            next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            wait = (next_run - now).total_seconds()
            print(f"[Briefing] Next briefing in {wait / 3600:.1f}h "
                  f"({next_run.strftime('%d/%m %H:%M')})")
            time.sleep(wait)
            try:
                if not settings.get("briefing.enabled", False):
                    print("[Briefing] Disabled in settings — skipping.")
                    continue
                text = generate_briefing()
                deliver_briefing(text)
                print("[Briefing] ✓ Done.")
            except Exception as e:
                print(f"[Briefing] Scheduler error: {e}")

    t = threading.Thread(target=_runner, daemon=True, name="MorningBriefing")
    t.start()
