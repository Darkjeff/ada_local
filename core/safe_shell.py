# core/safe_shell.py
"""
SafeShellExecutor — three-level shell command policy for ADA.

Levels:
  READ_ONLY     — pre-approved diagnostic commands, run immediately
  ADMIN_CONFIRM — system-management commands, require confirmed=True
  BLOCKED       — destructive / network commands, always refused

When allowlist_enabled=True (default), unknown commands fall into BLOCKED.
When allowlist_enabled=False, unknown commands fall into ADMIN_CONFIRM.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from enum import Enum

from core.settings_store import settings


class ShellLevel(str, Enum):
    READ_ONLY     = "read_only"
    ADMIN_CONFIRM = "admin_confirm"
    BLOCKED       = "blocked"


# ── Hard-coded lists (never overridable via settings) ─────────────────────

# READ_ONLY: command must match at least one of these patterns
_READ_ONLY_PATTERNS: list[re.Pattern] = [re.compile(p, re.I) for p in [
    r"^df(\s|$)",
    r"^free(\s|$)",
    r"^uptime$",
    r"^docker\s+ps(\s|$)",
    r"^docker\s+stats(\s|$)",
    r"^docker\s+logs(\s|$)",
    r"^docker\s+inspect(\s|$)",
    r"^lsblk(\s|$)",
    r"^ip\s+(a|addr|link|route)(\s|$)",
    r"^hostnamectl(\s|$)",
    r"^uname(\s|$)",
    r"^ps(\s|$)",
    r"^top\s+-bn?\d",
    r"^cat\s+/proc/(cpuinfo|meminfo|uptime|loadavg)",
    r"^cat\s+/etc/(os-release|hostname|hosts)",
    r"^ls(\s|$)",
    r"^pwd$",
    r"^echo\s+",
    r"^date$",
    r"^whoami$",
    r"^id$",
    r"^systemctl\s+status(\s|$)",
    r"^journalctl\s+",
    r"^du\s+",
    r"^lsof\s+",
    r"^netstat\s+",
    r"^ss\s+",
    r"^ping\s+-c\s+\d",
    r"^mount$",       # list only (no arguments)
    r"^env$",
    r"^printenv(\s|$)",
]]

# ADMIN_CONFIRM: these patterns promote to admin level (checked after READ_ONLY)
_ADMIN_CONFIRM_PATTERNS: list[re.Pattern] = [re.compile(p, re.I) for p in [
    r"systemctl\s+(restart|start|stop|enable|disable)\b",
    r"docker\s+(restart|start|stop|rm|rmi|pull|run|exec)\b",
    r"apt(-get)?\s+(update|upgrade|install|remove|purge)\b",
    r"pip\s+(install|uninstall)\b",
    r"mount\s+\S",    # mount with arguments
    r"umount\b",
    r"service\s+\w+\s+(restart|start|stop)\b",
    r"systemd-run\b",
    r"crontab\b",
]]

# BLOCKED: these patterns are always refused (checked first, highest priority)
_BLOCKED_PATTERNS: list[re.Pattern] = [re.compile(p, re.I) for p in [
    r"\brm\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bformat\b",
    r"curl[^|]*\|\s*bash",
    r"wget[^|]*\|\s*bash",
    r"chmod\s+-R\s+777",
    r"chown\s+-R\b",
    r"\bssh\b",
    r"\bscp\b",
    r"\bnc\b(?!\w)",  # netcat (not "nice" etc.)
    r"\bnmap\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bwipe\b",
    r"\btruncate\b",
    r"\bshred\b",
    r"\bsudo\s+su\b",
    r"\bpasswd\b",
    r"\buserdel\b",
    r">\s*/dev/(?!null)",  # redirect to device (but allow /dev/null)
    r"\bdiskpart\b",
    r"\bmkdir\s+-p\s+/(?!(tmp|mnt|home|opt)\b)",  # mkdir -p on system dirs
]]


class SafeShellExecutor:
    """Execute shell commands according to the three-level policy."""

    # ── Classification ────────────────────────────────────────────────────

    def classify(self, command: str) -> tuple[ShellLevel, str]:
        """
        Return (ShellLevel, reason_string) for a raw command string.
        Policy, from highest to lowest priority:
          1. BLOCKED  — hard-coded + settings blocked_patterns
          2. ADMIN_CONFIRM — hard-coded + settings confirm_required_patterns
          3. READ_ONLY — hard-coded allowlist
          4. BLOCKED (unknown) — when allowlist_enabled=True
             ADMIN_CONFIRM (unknown) — when allowlist_enabled=False
        """
        cmd = command.strip()

        # 1. Blocked — hard-coded
        for pat in _BLOCKED_PATTERNS:
            if pat.search(cmd):
                return ShellLevel.BLOCKED, f"Corresponds to blocked pattern: {pat.pattern!r}"

        # 1b. Blocked — from settings
        extra_blocked: list[str] = settings.get("shell_exec.blocked_patterns", []) or []
        for raw in extra_blocked:
            try:
                if re.search(raw, cmd, re.I):
                    return ShellLevel.BLOCKED, f"Blocked by settings pattern: {raw!r}"
            except re.error:
                pass

        # 2. Admin confirm — hard-coded
        for pat in _ADMIN_CONFIRM_PATTERNS:
            if pat.search(cmd):
                return ShellLevel.ADMIN_CONFIRM, f"Matches admin pattern: {pat.pattern!r}"

        # 2b. Admin confirm — from settings
        extra_confirm: list[str] = settings.get("shell_exec.confirm_required_patterns", []) or []
        for raw in extra_confirm:
            try:
                if re.search(raw, cmd, re.I):
                    return ShellLevel.ADMIN_CONFIRM, f"Admin confirm by settings pattern: {raw!r}"
            except re.error:
                pass

        # 3. Read-only allowlist
        for pat in _READ_ONLY_PATTERNS:
            if pat.match(cmd):
                return ShellLevel.READ_ONLY, "Matches read-only allowlist"

        # 4. Unknown command
        allowlist_enabled: bool = settings.get("shell_exec.allowlist_enabled", True)
        if allowlist_enabled:
            return ShellLevel.BLOCKED, "Not in allowlist (allowlist_enabled=True)"
        return ShellLevel.ADMIN_CONFIRM, "Unknown command — confirmation required (allowlist_enabled=False)"

    # ── Execution ─────────────────────────────────────────────────────────

    def execute(
        self,
        command: str,
        *,
        confirmed: bool = False,
        timeout: int = 30,
    ) -> dict:
        """
        Execute command according to policy.

        Returns standard result dict:
          success (bool), message (str), data (dict | None)
          needs_confirmation (bool) — present and True when admin_confirm and not confirmed
        """
        cmd = command.strip()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Guard: feature disabled
        if not settings.get("shell_exec.enabled", True):
            return {
                "success": False,
                "message": "shell_exec est désactivé dans les paramètres.",
                "data": None,
            }

        # Classify
        level, reason = self.classify(cmd)
        print(f"[SafeShell] {ts} | level={level.value} | cmd={cmd!r} | reason={reason}")

        # Blocked — always refuse
        if level == ShellLevel.BLOCKED:
            print(f"[SafeShell] BLOCKED: {cmd!r}")
            return {
                "success": False,
                "message": f"Commande bloquée pour des raisons de sécurité : `{cmd}`",
                "data": None,
            }

        # Admin confirm — needs explicit confirmation
        if level == ShellLevel.ADMIN_CONFIRM and not confirmed:
            print(f"[SafeShell] NEEDS_CONFIRMATION: {cmd!r}")
            return {
                "success": False,
                "needs_confirmation": True,
                "message": (
                    f"Cette commande nécessite une confirmation avant exécution :\n`{cmd}`\n"
                    "Répondez 'confirme' pour l'exécuter."
                ),
                "data": {"command": cmd, "level": level.value},
            }

        # Execute (READ_ONLY or ADMIN_CONFIRM + confirmed)
        timeout = min(timeout, 30)  # hard cap at 30s
        if sys.platform == "win32":
            cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd]
        else:
            cmd_args = ["bash", "-c", cmd]

        try:
            proc = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                errors="replace",
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            output = stdout or stderr or "(no output)"
            if len(output) > 3000:
                output = output[:3000] + "\n… (output truncated)"

            success = proc.returncode == 0
            print(
                f"[SafeShell] EXEC rc={proc.returncode} | "
                f"stdout={stdout[:120]!r} | stderr={stderr[:60]!r}"
            )
            return {
                "success": success,
                "message": output,
                "data": {
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout": stdout[:1500],
                    "stderr": stderr[:500],
                    "level": level.value,
                    "timestamp": ts,
                },
            }
        except subprocess.TimeoutExpired:
            print(f"[SafeShell] TIMEOUT after {timeout}s: {cmd!r}")
            return {
                "success": False,
                "message": f"Commande interrompue après {timeout}s (timeout).",
                "data": None,
            }
        except Exception as exc:
            print(f"[SafeShell] ERROR: {exc}")
            return {"success": False, "message": f"Erreur d'exécution : {exc}", "data": None}


# Global singleton
safe_shell_executor = SafeShellExecutor()
