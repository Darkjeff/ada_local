"""
PatternDispatcher — deterministic regex-based intent extraction.

Routes common user prompts to (action, params) without any LLM round-trip.
Returns None when no rule matches; the caller falls back to LLM intent parsing.
"""

import logging
import re
import sys
from typing import Optional

_IS_LINUX = sys.platform != "win32"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Room extraction
# ---------------------------------------------------------------------------

_ROOMS = [
    "bureau", "salon", "chambre", "cuisine", "couloir",
    "salle de bain", "garage", "extérieur", "jardin", "chillout",
]


def _extract_room(text: str) -> Optional[str]:
    """Return the first known room name found in *text*, or None."""
    text_lower = text.lower()
    return next((r for r in _ROOMS if r in text_lower), None)


# ---------------------------------------------------------------------------
# Duration extraction
# ---------------------------------------------------------------------------

def _extract_duration(text: str) -> str:
    """
    Extract a human-readable duration from *text*.

    Supports French and English: '10 minutes', '2 heures', '30 secondes'.
    Falls back to '5 minutes' when nothing is recognised.
    """
    text_lower = text.lower()

    m = re.search(r"(\d+)\s*(?:heure|heures|hour|hours|h)\b", text_lower)
    if m:
        n = int(m.group(1))
        return f"{n} heure{'s' if n > 1 else ''}"

    m = re.search(r"(\d+)\s*(?:minute|minutes|min|mn)\b", text_lower)
    if m:
        n = int(m.group(1))
        return f"{n} minute{'s' if n > 1 else ''}"

    m = re.search(r"(\d+)\s*(?:seconde|secondes|second|seconds|sec|s)\b", text_lower)
    if m:
        n = int(m.group(1))
        return f"{n} seconde{'s' if n > 1 else ''}"

    return "5 minutes"


# ---------------------------------------------------------------------------
# Ordered pattern table
# (regex_str, extractor_fn(match, full_text) → (action, params))
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, object]] = [
    # Lights — off
    (
        r"\b(éteins?|désactiv\w+|coupe?|arrête?\s+l[ae]s?)\b.*(lumière|lampe|éclairage|led)",
        lambda m, t: ("control-light", {"action": "off",
                                         "device_name": _extract_room(t) or "all"}),
    ),
    # Lights — on
    (
        r"\b(allume?|activ\w+|mets?\s+l[ae]s?)\b.*(lumière|lampe|éclairage|led)",
        lambda m, t: ("control-light", {"action": "on",
                                         "device_name": _extract_room(t) or "all"}),
    ),
    # Lights — dim
    (
        r"\b(baisse?|réduis?|dimme?|atténue?)\b.*(lumière|lampe)",
        lambda m, t: ("control-light", {"action": "dim",
                                         "device_name": _extract_room(t) or "all",
                                         "brightness": 30}),
    ),
    # Timers
    (
        r"\b(minuterie|timer|chrono)\b",
        lambda m, t: ("set-timer", {"duration": _extract_duration(t), "label": "Timer"}),
    ),
    # Shell — disk
    (
        r"\b(espace|disque|disk|space|df|stockage|libre)\b",
        lambda m, t: ("shell-exec", {
            "command": "df -h" if _IS_LINUX else
            "Get-PSDrive | Where-Object {$_.Used -ne $null} | "
            "Select-Object Name,"
            "@{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}},"
            "@{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}}"
        }),
    ),
    # Shell — RAM
    (
        r"\b(ram|mémoire|memory)\b",
        lambda m, t: ("shell-exec", {
            "command": "free -h" if _IS_LINUX else
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object @{N='Total(GB)';E={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}},"
            "@{N='Free(GB)';E={[math]::Round($_.FreePhysicalMemory/1MB,1)}}"
        }),
    ),
    # Shell — CPU
    (
        r"\b(cpu|processeur|charge\s+système|load)\b",
        lambda m, t: ("shell-exec", {
            "command": "top -bn1 | head -15" if _IS_LINUX else
            "Get-Process | Sort-Object CPU -Descending | "
            "Select-Object -First 10 Name,CPU,WorkingSet"
        }),
    ),
    # Weather
    (
        r"\b(météo|temps\s+qu['’]?il\s+fait|weather|température\s+extérieure)\b",
        lambda m, t: ("weather", {}),
    ),
    # Web search  — must be last (greedy group 2 captures the rest of the prompt)
    (
        r"\b(cherche?|recherche?|search|trouve?)\b\s+(.+)",
        lambda m, t: ("web-search", {"query": m.group(2).strip()}),
    ),
]

# Compile once at import time
_COMPILED: list[tuple[re.Pattern, object]] = [
    (re.compile(pattern, re.IGNORECASE | re.UNICODE), extractor)
    for pattern, extractor in _PATTERNS
]


# ---------------------------------------------------------------------------
# PatternDispatcher
# ---------------------------------------------------------------------------

class PatternDispatcher:
    """
    Deterministic regex-based intent dispatcher.

    Call match(prompt) → (action, params) or None.
    Thread-safe: stateless after module import (compiled patterns are read-only).
    """

    def match(self, prompt: str) -> Optional[tuple[str, dict]]:
        """
        Try each rule in order. Return (action, params) for the first match,
        or None if no rule applies.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        for compiled_re, extractor in _COMPILED:
            m = compiled_re.search(prompt)
            if m:
                try:
                    result = extractor(m, prompt)
                    logger.debug("[PatternDispatcher] matched action=%s", result[0])
                    return result
                except Exception as exc:
                    logger.warning("[PatternDispatcher] extractor error: %s", exc)
                    continue
        return None


# Module-level singleton
pattern_dispatcher = PatternDispatcher()
