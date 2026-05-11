"""
Creality K1 printer control via SSH + Klipper JSON-RPC over Unix socket.
"""

import json

from core.settings_store import settings

try:
    import paramiko
    _PARAMIKO_AVAILABLE = True
except ImportError:
    _PARAMIKO_AVAILABLE = False


class K1Manager:
    """
    SSH client for Creality K1 running Klipper.
    Never raises; returns False/{} on failure.
    """

    def __init__(self):
        self._ip: str = ""
        self._password: str = ""
        self._connected: bool = False
        self._client = None
        self._load_config()

    # ------------------------------------------------------------------ #
    # Config                                                               #
    # ------------------------------------------------------------------ #

    def _load_config(self):
        self._ip = settings.get("k1.ip", "")
        self._password = settings.get("k1.password", "")

    def reload_config(self):
        """Re-read ip/password from settings; closes current SSH session."""
        self._disconnect()
        self._load_config()

    # ------------------------------------------------------------------ #
    # Connection                                                           #
    # ------------------------------------------------------------------ #

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _disconnect(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        """
        Opens SSH session to root@{ip} using password auth.
        Sets self._connected; returns True on success.
        """
        if not _PARAMIKO_AVAILABLE:
            print("[K1Manager] paramiko not installed — run: pip install paramiko")
            self._connected = False
            return False

        if not self._ip or not self._password:
            print("[K1Manager] ip or password not configured")
            self._connected = False
            return False

        self._disconnect()
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self._ip,
                username="root",
                password=self._password,
                timeout=5,
                allow_agent=False,
                look_for_keys=False,
            )
            self._client = client
            self._connected = True
        except Exception as e:
            print(f"[K1Manager] connect() failed: {e}")
            self._client = None
            self._connected = False

        return self._connected

    # ------------------------------------------------------------------ #
    # Low-level SSH                                                        #
    # ------------------------------------------------------------------ #

    def _exec(self, cmd: str, timeout: int = 5) -> str | None:
        """Execute shell command over SSH; returns stdout or None on failure."""
        if not self._client:
            return None
        try:
            _, stdout, _ = self._client.exec_command(cmd, timeout=timeout)
            return stdout.read().decode("utf-8", errors="replace").strip()
        except Exception as e:
            print(f"[K1Manager] _exec failed: {e}")
            self._connected = False
            return None

    # ------------------------------------------------------------------ #
    # Klipper JSON-RPC                                                     #
    # ------------------------------------------------------------------ #

    def _klipper_rpc(self, method: str, params: dict | None = None) -> dict:
        """
        Send JSON-RPC to Klipper's Unix socket via SSH + socat.
        Returns the result dict, or {} on failure.
        """
        payload = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params

        # Escape single quotes for the shell heredoc approach
        json_str = json.dumps(payload).replace("'", "'\\''")
        cmd = f"echo '{json_str}' | socat - UNIX-CONNECT:/tmp/klippy_uds"

        output = self._exec(cmd, timeout=10)
        if not output:
            return {}
        try:
            return json.loads(output).get("result", {})
        except json.JSONDecodeError as e:
            print(f"[K1Manager] JSON decode failed: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        """
        Query Klipper printer objects.
        Returns: state, filename, progress, bed_temp, bed_target,
                 nozzle_temp, nozzle_target.
        """
        if not self._connected:
            return {}

        result = self._klipper_rpc(
            "printer.objects.query",
            {
                "objects": {
                    "print_stats": None,
                    "heater_bed": None,
                    "extruder": None,
                    "display_status": None,
                }
            },
        )

        if not result:
            return {}

        s = result.get("status", {})
        ps = s.get("print_stats", {})
        hb = s.get("heater_bed", {})
        ex = s.get("extruder", {})
        ds = s.get("display_status", {})

        return {
            "state":         ps.get("state", "unknown"),
            "filename":      ps.get("filename", ""),
            "progress":      ds.get("progress", 0.0),
            "bed_temp":      hb.get("temperature", 0.0),
            "bed_target":    hb.get("target", 0.0),
            "nozzle_temp":   ex.get("temperature", 0.0),
            "nozzle_target": ex.get("target", 0.0),
        }

    # ------------------------------------------------------------------ #
    # Print control                                                        #
    # ------------------------------------------------------------------ #

    def send_gcode(self, cmd: str) -> bool:
        """Send arbitrary G-code to Klipper."""
        if not self._connected:
            return False
        result = self._klipper_rpc("printer.gcode.script", {"script": cmd})
        # Klipper returns {} on success for gcode.script
        return result is not None

    def pause_print(self) -> bool:
        return self.send_gcode("PAUSE")

    def resume_print(self) -> bool:
        return self.send_gcode("RESUME")

    def cancel_print(self) -> bool:
        return self.send_gcode("CANCEL_PRINT")


# Global singleton
k1_manager = K1Manager()
