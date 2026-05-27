"""Minimal HTTP server that serves a single M3U playlist file."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


class _M3UHandler(BaseHTTPRequestHandler):
    _content: bytes = b""
    _content_lock = threading.Lock()

    def do_GET(self):
        if self.path == "/playlist.m3u":
            with self.__class__._content_lock:
                data = self.__class__._content
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logs


class PlaylistServer:
    """Serves one M3U file over HTTP for a configurable TTL, then stops."""

    def __init__(self):
        self._server: Optional[HTTPServer] = None
        self._lock = threading.Lock()

    @staticmethod
    def _local_ip() -> str:
        """Detect the LAN IP of this machine (the address reachable by other devices)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def serve(self, m3u_content: str, ttl: int = 300,
              host: str = None, port: int = None) -> str:
        if host is None or port is None:
            from core.settings_store import settings
            configured_host = settings.get("music.playlist_server_host", "")
            host = host or configured_host or self._local_ip()
            port = port or int(settings.get("music.playlist_server_port", 8765))

        with _M3UHandler._content_lock:
            _M3UHandler._content = m3u_content.encode("utf-8")

        with self._lock:
            if self._server is not None:
                self._server.server_close()
                self._server = None

            server = HTTPServer(("0.0.0.0", port), _M3UHandler)
            server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.timeout = 1.0
            self._server = server

        deadline = time.time() + ttl
        t = threading.Thread(target=self._run, args=(server, deadline), daemon=True)
        t.start()

        return f"http://{host}:{port}/playlist.m3u"

    def _run(self, server: HTTPServer, deadline: float):
        while time.time() < deadline:
            try:
                server.handle_request()
            except (ValueError, OSError):
                break
        server.server_close()
        with self._lock:
            if self._server is server:
                self._server = None

    def stop(self):
        with self._lock:
            if self._server:
                self._server.server_close()
                self._server = None


playlist_server = PlaylistServer()
