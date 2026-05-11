"""
Memory Consolidator — nightly LLM-based memory consolidation.

Like the brain during sleep:
  1. Gather raw conversation memories from the day
  2. Ask the LLM to summarize, extract facts, discard noise
  3. Save as a compact consolidated_memory record
  4. These summaries are injected as long-term context in future chats

Runs automatically at a configurable hour (default 3:00 AM).
Can also be triggered manually from the UI.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import OLLAMA_URL, RESPONDER_MODEL
from core.memory_store import memory_store

_CONSOLIDATION_HOUR = 3   # 3:00 AM local time

_SYSTEM_PROMPT = """\
Tu es un système de consolidation mémorielle. Tu reçois des échanges bruts d'une journée de conversations entre Jeff et son assistant ADA.

Ton travail :
1. RÉSUMER les sujets importants en 2-4 phrases concises
2. EXTRAIRE les faits utiles et durables (préférences, décisions, connaissances techniques, problèmes résolus)
3. IGNORER le bruit : salutations, questions banales, échanges sans valeur informationnelle, reformulations

Réponds UNIQUEMENT en JSON valide, sans markdown, sans explication :
{
  "résumé": "...",
  "faits": ["fait 1", "fait 2", ...],
  "sujets": ["sujet 1", "sujet 2"]
}"""


def consolidate_date(date_str: str, force: bool = False) -> Optional[dict]:
    """
    Consolidate all memories for a given date (YYYY-MM-DD).
    Returns the consolidated record or None on failure.
    Skips if already consolidated unless force=True.
    """
    if not force and memory_store.already_consolidated(date_str):
        print(f"[Consolidator] {date_str} already consolidated — skipping.")
        return None

    raw = memory_store.get_memories_for_date(date_str)
    if not raw:
        print(f"[Consolidator] No memories for {date_str} — skipping.")
        return None

    print(f"[Consolidator] Consolidating {len(raw)} memories for {date_str}…")

    # Build conversation transcript (user messages only for brevity)
    lines = []
    for r in raw:
        role = "Jeff" if r["role"] == "user" else "ADA"
        snippet = r["content"][:300].replace("\n", " ")
        lines.append(f"[{role}] {snippet}")

    transcript = "\n".join(lines)

    # Call the LLM
    payload = {
        "model": RESPONDER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Date : {date_str}\n\nConversations :\n{transcript}"},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "2m",
    }

    try:
        r = requests.post(f"{OLLAMA_URL}/chat", json=payload, timeout=120)
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")

        # Strip potential markdown fences
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        data = json.loads(content)
        summary = data.get("résumé", data.get("resume", ""))
        facts   = data.get("faits", data.get("facts", []))
        topics  = data.get("sujets", data.get("topics", []))

        if not summary:
            print("[Consolidator] Empty summary — skipping save.")
            return None

        memory_store.save_consolidated(date_str, summary, facts, topics, len(raw))
        print(f"[Consolidator] ✓ {date_str}: {len(facts)} facts, topics: {topics}")
        return {"date": date_str, "summary": summary, "facts": facts, "topics": topics}

    except json.JSONDecodeError as e:
        print(f"[Consolidator] JSON parse error: {e}\nContent: {content[:200]}")
        return None
    except Exception as e:
        print(f"[Consolidator] Error: {e}")
        return None


def consolidate_yesterday(force: bool = False) -> Optional[dict]:
    """Consolidate yesterday's memories."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return consolidate_date(yesterday, force=force)


def consolidate_today(force: bool = False) -> Optional[dict]:
    """Consolidate today's memories (for manual/test trigger)."""
    today = datetime.now().strftime("%Y-%m-%d")
    return consolidate_date(today, force=force)


# ── Nightly scheduler ─────────────────────────────────────────────────────────

_scheduler_started = False


def start_nightly_scheduler(hour: int = _CONSOLIDATION_HOUR):
    """
    Start a daemon thread that consolidates memories every night at `hour:00`.
    Safe to call multiple times — only starts once.
    """
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _runner():
        print(f"[Consolidator] Nightly scheduler started — runs at {hour:02d}:00.")
        while True:
            now = datetime.now()
            next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)

            wait = (next_run - now).total_seconds()
            print(f"[Consolidator] Next run in {wait/3600:.1f}h ({next_run.strftime('%d/%m %H:%M')})")
            time.sleep(wait)

            try:
                consolidate_yesterday()
            except Exception as e:
                print(f"[Consolidator] Nightly run failed: {e}")

    t = threading.Thread(target=_runner, daemon=True, name="MemoryConsolidator")
    t.start()
