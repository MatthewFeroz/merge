"""Tiny zero-dependency web server for the Merge Gateway chat UI.

Serves web/index.html and proxies two JSON endpoints to the Merge gateway,
reusing the client + helpers already defined in chat_demo.py so the API key
never leaves the server.

    pip install -r requirements.txt
    $env:MERGE_API_KEY="..."        # or a .env file in this folder
    python server.py                # -> http://127.0.0.1:8000
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from chat_demo import build_client, fetch_models, send_message

WEB_DIR = Path(__file__).parent / "web"
HOST = os.getenv("MERGE_WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("MERGE_WEB_PORT", "8000"))
DEFAULT_MODEL = os.getenv("MERGE_MODEL", "openai/gpt-4o")

_client = None
_catalog = None


def client():
    global _client
    if _client is None:
        _client = build_client()
    return _client


def catalog() -> dict:
    """Lazily fetch the live model catalog once, then cache it."""
    global _catalog
    if _catalog is None:
        _catalog = fetch_models(client())
    return _catalog


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            try:
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            except FileNotFoundError:
                return self._send(500, "web/index.html is missing", "text/plain")
            return self._send(200, html, "text/html; charset=utf-8")

        if self.path.startswith("/api/models"):
            try:
                cat = catalog()
                models = [
                    {"id": mid, "name": name}
                    for mid, name in sorted(cat.items(), key=lambda kv: kv[1].lower())
                ]
                return self._send(
                    200, json.dumps({"models": models, "default": DEFAULT_MODEL})
                )
            except Exception as exc:  # noqa: BLE001 - surface error to the client
                return self._send(502, json.dumps({"error": str(exc)}))

        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            return self._send(404, json.dumps({"error": "not found"}))

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
            model = payload.get("model") or DEFAULT_MODEL
            messages = payload.get("messages") or []
            text = send_message(client(), messages, model)
            return self._send(200, json.dumps({"text": text, "model": model}))
        except Exception as exc:  # noqa: BLE001 - surface error to the client
            return self._send(502, json.dumps({"error": str(exc)}))

    def log_message(self, *_args) -> None:  # keep the console quiet
        pass


def main() -> int:
    try:
        client()  # validate MERGE_API_KEY up front with a clear message
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"\n{exc}\n\n")
        return 1

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"\n  Merge chat UI  ->  http://{HOST}:{PORT}")
    print("  Ctrl+C to stop\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye\n")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
