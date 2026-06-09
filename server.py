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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from chat_demo import DEFAULT_BASE_URL, build_client, extract_text, fetch_models

WEB_DIR = Path(__file__).parent / "web"
# Cloud platforms (Render, Railway, Fly, Heroku) inject PORT and need 0.0.0.0.
PORT = int(os.getenv("PORT", os.getenv("MERGE_WEB_PORT", "8000")))
HOST = os.getenv("MERGE_WEB_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
DEFAULT_MODEL = os.getenv("MERGE_MODEL", "openai/gpt-4o")

NO_KEY_MSG = (
    "No Merge API key. Click the \U0001f511 key button and paste your key "
    "(get one at https://app.merge.dev), or set MERGE_API_KEY on the server."
)

_clients: dict[str, httpx.Client] = {}  # "" -> server env key, else the BYOK key
_catalog = None
_pricing = None


def client(api_key: str = "") -> httpx.Client:
    """Client for the given browser-supplied key, or the server's env key."""
    cached = _clients.get(api_key)
    if cached is not None:
        return cached
    if api_key:
        c = httpx.Client(
            base_url=os.getenv("MERGE_BASE_URL", DEFAULT_BASE_URL),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
    else:
        try:
            c = build_client()  # env var or .env file
        except RuntimeError:
            raise PermissionError(NO_KEY_MSG) from None
    if len(_clients) > 64:  # bound memory if many visitors bring keys
        _clients.pop(next(iter(_clients)))
    _clients[api_key] = c
    return c


def catalog(api_key: str = "") -> dict:
    """Lazily fetch the live model catalog once, then cache it."""
    global _catalog
    if _catalog is None:
        found = fetch_models(client(api_key))
        if not found:  # bad key or gateway down — don't poison the cache
            raise RuntimeError(
                "The gateway returned no models — check that the API key is valid."
            )
        _catalog = found
    return _catalog


def pricing(api_key: str = "") -> dict:
    """Map model_id -> {'in': $/M input, 'out': $/M output}, cached for the process."""
    global _pricing
    if _pricing:
        return _pricing
    _pricing = {}
    raw = {}
    # /models paginates; union a couple of param sets to get the full catalog.
    for params in ({}, {"page_size": 1000}):
        try:
            data = client(api_key).get("/models", params=params).json().get("data", [])
        except Exception:  # noqa: BLE001
            continue
        for m in data:
            if m.get("model"):
                raw[m["model"]] = m
    for mid, rec in raw.items():
        for vendor in (rec.get("vendors") or {}).values():
            p = (vendor or {}).get("pricing") or {}
            if "input_per_million" in p or "output_per_million" in p:
                _pricing[mid] = {
                    "in": float(p.get("input_per_million") or 0.0),
                    "out": float(p.get("output_per_million") or 0.0),
                }
                break
    return _pricing


def cost_for(model: str, usage: dict, api_key: str = ""):
    """Dollar cost of one call from its token usage, or None if pricing is unknown."""
    p = pricing(api_key).get(model)
    if not p or not usage:
        return None
    return round(
        usage.get("input_tokens", 0) / 1e6 * p["in"]
        + usage.get("output_tokens", 0) / 1e6 * p["out"],
        6,
    )


def complete(messages: list, model: str, api_key: str = ""):
    """Post one turn to the gateway; return (text, usage dict)."""
    resp = client(api_key).post(
        "/responses",
        json={
            "model": model,
            "input": [
                {"type": "message", "role": m["role"], "content": m["content"]}
                for m in messages
            ],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return (extract_text(data) or str(data)), (data.get("usage") or {})


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_key(self) -> str:
        """Per-request key the browser sends; '' falls back to the server's env key."""
        return (self.headers.get("X-Merge-Key") or "").strip()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            try:
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            except FileNotFoundError:
                return self._send(500, "web/index.html is missing", "text/plain")
            return self._send(200, html, "text/html; charset=utf-8")

        if self.path.startswith("/api/health"):
            return self._send(200, json.dumps({"ok": True}))

        if self.path.startswith("/api/models"):
            try:
                key = self._api_key()
                cat = catalog(key)
                prices = pricing(key)
                models = [
                    {"id": mid, "name": name, "price": prices.get(mid)}
                    for mid, name in sorted(cat.items(), key=lambda kv: kv[1].lower())
                ]
                return self._send(
                    200, json.dumps({"models": models, "default": DEFAULT_MODEL})
                )
            except PermissionError as exc:
                return self._send(401, json.dumps({"error": str(exc), "need_key": True}))
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
            key = self._api_key()
            text, usage = complete(messages, model, key)
            cost = cost_for(model, usage, key)
            return self._send(
                200,
                json.dumps({"text": text, "model": model, "usage": usage, "cost": cost}),
            )
        except PermissionError as exc:
            return self._send(401, json.dumps({"error": str(exc), "need_key": True}))
        except Exception as exc:  # noqa: BLE001 - surface error to the client
            return self._send(502, json.dumps({"error": str(exc)}))

    def log_message(self, *_args) -> None:  # keep the console quiet
        pass


def main() -> int:
    try:
        client()  # warm up the server-side MERGE_API_KEY if one is configured
        mode = "server API key configured"
    except PermissionError:
        mode = "no server key — visitors paste their own (\U0001f511 button in the UI)"

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"\n  Merge chat UI  ->  http://{HOST}:{PORT}")
    print(f"  {mode}")
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
