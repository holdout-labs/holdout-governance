"""Minimal HTTP JSON API for gov — Python stdlib only, no third-party deps.

Endpoints:

- ``GET  /health``            -> {"ok": true, "service": ..., "version": ...}
- ``POST /check``             body: {"manifest", "policy"?, "gate_inputs"?, "kind"?}
- ``POST /report``            body: {"manifest", "policy"?}
- ``POST /init``              body: {"dir", "kind"?, "name"?}

Errors are reported as HTTP 400 with {"error": "..."}. Responses are the
engine result dicts without the full ``artifact`` payload (use the CLI for
that). Run with: ``gov api --host 127.0.0.1 --port 8000``.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import __version__
from . import engine


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = 0
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        value = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


class GovHTTPHandler(BaseHTTPRequestHandler):
    server_version = "holdout-gov/" + __version__

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "holdout-gov", "version": __version__})
        else:
            self._send(404, {"error": f"unknown path {self.path}"})

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        body = _read_body(self)
        if self.path == "/check":
            result = engine.run_check(
                str(body.get("manifest", "")),
                policy=str(body["policy"]) if body.get("policy") else None,
                gate_inputs=str(body["gate_inputs"]) if body.get("gate_inputs") else None,
                kind=str(body["kind"]) if body.get("kind") else None,
            )
        elif self.path == "/report":
            result = engine.run_report(
                str(body.get("manifest", "")),
                policy=str(body["policy"]) if body.get("policy") else None,
            )
        elif self.path == "/init":
            result = engine.run_init(
                str(body.get("dir", ".")),
                kind=str(body.get("kind", "research_conclusion")),
                name=str(body["name"]) if body.get("name") else None,
            )
        else:
            self._send(404, {"error": f"unknown path {self.path}"})
            return
        if result.get("error"):
            self._send(400, {"error": result["error"]})
        else:
            self._send(200, {k: v for k, v in result.items() if k != "artifact"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # keep the server quiet in tests/logs


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), GovHTTPHandler)
    print(f"holdout-gov API listening on http://{host}:{port} "
          "(POST /check, /report, /init; GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
