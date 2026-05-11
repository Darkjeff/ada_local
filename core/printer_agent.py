"""
Printer Agent — REST API client for OctoPrint and Moonraker/Klipper printers.
Synchronous (uses requests), safe to call from QThread.
"""

import time
import requests
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

from core.settings_store import settings


class PrinterType(str, Enum):
    MOONRAKER = "moonraker"
    OCTOPRINT = "octoprint"
    K1_SSH = "k1_ssh"


@dataclass
class PrintStatus:
    state: str            # "printing", "paused", "idle", "standby", "error", "unknown"
    progress: float       # 0.0–1.0
    filename: str
    nozzle_temp: float
    nozzle_target: float
    bed_temp: float
    bed_target: float
    time_elapsed: Optional[int]    # seconds, may be None
    time_remaining: Optional[int]  # seconds, may be None

    def format_time(self, seconds: Optional[int]) -> str:
        if seconds is None:
            return "--:--:--"
        h, r = divmod(int(seconds), 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


class PrinterAgent:
    """
    REST API client for OctoPrint and Moonraker/Klipper.
    Never raises; returns False/None on failure.
    """

    def __init__(self):
        self._host: str = ""
        self._port: int = 80
        self._type: PrinterType = PrinterType.MOONRAKER
        self._api_key: str = ""
        self._connected: bool = False
        self._session = requests.Session()
        self._load_config()

    # ------------------------------------------------------------------ #
    # Config                                                               #
    # ------------------------------------------------------------------ #

    def _load_config(self):
        self._host = settings.get("printer.host", "")
        self._port = int(settings.get("printer.port", 80) or 80)
        raw_type = settings.get("printer.type", "moonraker")
        try:
            self._type = PrinterType(raw_type)
        except ValueError:
            self._type = PrinterType.MOONRAKER
        self._api_key = settings.get("printer.api_key", "")

    def reload_config(self):
        self._connected = False
        self._load_config()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _headers(self) -> dict:
        if self._api_key and self._type == PrinterType.OCTOPRINT:
            return {"X-Api-Key": self._api_key}
        return {}

    def _get(self, path: str) -> Optional[dict]:
        try:
            r = self._session.get(
                self._base_url() + path,
                headers=self._headers(),
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[PrinterAgent] GET {path} failed: {e}")
        return None

    def _post(self, path: str, json_data: Optional[dict] = None) -> bool:
        try:
            r = self._session.post(
                self._base_url() + path,
                headers=self._headers(),
                json=json_data,
                timeout=5,
            )
            return r.status_code in (200, 201, 202, 204)
        except Exception as e:
            print(f"[PrinterAgent] POST {path} failed: {e}")
        return False

    # ------------------------------------------------------------------ #
    # Connection                                                           #
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        if not self._host:
            print("[PrinterAgent] No host configured")
            self._connected = False
            return False
        try:
            if self._type == PrinterType.K1_SSH:
                from core.k1_control import K1Manager
                self._k1 = K1Manager()
                self._connected = self._k1.connect()
            elif self._type == PrinterType.MOONRAKER:
                data = self._get("/printer/info")
                self._connected = data is not None
            else:
                data = self._get("/api/version")
                self._connected = data is not None
        except Exception:
            self._connected = False
        return self._connected

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def get_status(self) -> Optional[PrintStatus]:
        if not self._connected:
            return None
        if self._type == PrinterType.K1_SSH:
            return self._status_k1_ssh()
        if self._type == PrinterType.MOONRAKER:
            return self._status_moonraker()
        return self._status_octoprint()

    def _status_k1_ssh(self) -> Optional[PrintStatus]:
        s = self._k1.get_status()
        if not s:
            return None
        return PrintStatus(
            state=s.get("state", "unknown"),
            progress=s.get("progress", 0.0),
            filename=s.get("filename", ""),
            nozzle_temp=s.get("nozzle_temp", 0.0),
            nozzle_target=s.get("nozzle_target", 0.0),
            bed_temp=s.get("bed_temp", 0.0),
            bed_target=s.get("bed_target", 0.0),
            time_elapsed=None,
            time_remaining=None,
        )

    def _status_moonraker(self) -> Optional[PrintStatus]:
        data = self._get(
            "/printer/objects/query"
            "?print_stats&display_status&extruder&heater_bed"
        )
        if not data:
            return None
        s = data.get("result", {}).get("status", {})
        ps = s.get("print_stats", {})
        ds = s.get("display_status", {})
        ex = s.get("extruder", {})
        bed = s.get("heater_bed", {})
        elapsed = ps.get("print_duration")
        return PrintStatus(
            state=ps.get("state", "unknown"),
            progress=ds.get("progress", 0.0),
            filename=ps.get("filename", ""),
            nozzle_temp=ex.get("temperature", 0.0),
            nozzle_target=ex.get("target", 0.0),
            bed_temp=bed.get("temperature", 0.0),
            bed_target=bed.get("target", 0.0),
            time_elapsed=int(elapsed) if elapsed else None,
            time_remaining=None,
        )

    def _status_octoprint(self) -> Optional[PrintStatus]:
        job = self._get("/api/job")
        printer = self._get("/api/printer")
        if not job:
            return None
        progress = job.get("progress", {})
        job_info = job.get("job", {})
        temps = (printer or {}).get("temperature", {})
        tool0 = temps.get("tool0", {})
        bed = temps.get("bed", {})

        raw_state = job.get("state", "unknown").lower()
        state_map = {"printing": "printing", "paused": "paused",
                     "operational": "idle", "ready": "idle"}
        state = state_map.get(raw_state, raw_state)

        completion = progress.get("completion") or 0
        return PrintStatus(
            state=state,
            progress=completion / 100.0,
            filename=job_info.get("file", {}).get("name", ""),
            nozzle_temp=tool0.get("actual", 0.0),
            nozzle_target=tool0.get("target", 0.0),
            bed_temp=bed.get("actual", 0.0),
            bed_target=bed.get("target", 0.0),
            time_elapsed=progress.get("printTime"),
            time_remaining=progress.get("printTimeLeft"),
        )

    # ------------------------------------------------------------------ #
    # Print control                                                        #
    # ------------------------------------------------------------------ #

    def pause_print(self) -> bool:
        if self._type == PrinterType.K1_SSH:
            return self._k1.pause_print()
        if self._type == PrinterType.MOONRAKER:
            return self._post("/printer/print/pause")
        return self._post("/api/job", {"command": "pause"})

    def resume_print(self) -> bool:
        if self._type == PrinterType.K1_SSH:
            return self._k1.resume_print()
        if self._type == PrinterType.MOONRAKER:
            return self._post("/printer/print/resume")
        return self._post("/api/job", {"command": "start"})

    def cancel_print(self) -> bool:
        if self._type == PrinterType.K1_SSH:
            return self._k1.cancel_print()
        if self._type == PrinterType.MOONRAKER:
            return self._post("/printer/print/cancel")
        return self._post("/api/job", {"command": "cancel"})

    # ------------------------------------------------------------------ #
    # Discovery (optional — needs zeroconf)                               #
    # ------------------------------------------------------------------ #

    def discover_printers(self, timeout: float = 5.0) -> List[dict]:
        """mDNS discovery. Returns list of {name, host, port, type}."""
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

            found: List[dict] = []

            class _Listener(ServiceListener):
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if not info:
                        return
                    addrs = info.parsed_addresses()
                    host = addrs[0] if addrs else (info.server or "").rstrip(".")
                    if not host:
                        return
                    ptype = (
                        "moonraker"
                        if any(k in type_ for k in ("moonraker", "klipper"))
                        else "octoprint"
                    )
                    found.append({
                        "name": name.split(".")[0],
                        "host": host,
                        "port": info.port or 80,
                        "type": ptype,
                    })

                def remove_service(self, zc, type_, name): pass
                def update_service(self, zc, type_, name): pass

            zc = Zeroconf()
            listener = _Listener()
            services = [
                "_octoprint._tcp.local.",
                "_moonraker._tcp.local.",
                "_klipper._tcp.local.",
            ]
            browsers = [ServiceBrowser(zc, s, listener) for s in services]
            time.sleep(timeout)
            zc.close()
            return found

        except ImportError:
            print("[PrinterAgent] zeroconf not installed — mDNS discovery unavailable")
            return []
        except Exception as e:
            print(f"[PrinterAgent] Discovery failed: {e}")
            return []


# Global singleton
printer_agent = PrinterAgent()
