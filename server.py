from collections import deque
import hmac
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
import urllib.request
import uuid
import zlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, Optional

MAX_POST_BYTES = 32 * 1024 * 1024
MAX_REF_FETCH_BYTES = 16 * 1024 * 1024
MAX_BRIDGE_QUEUE = 64
ALLOWED_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/vm.js": ("vm.js", "application/javascript; charset=utf-8"),
}

BASE_DIR = Path(__file__).resolve().parent

# Ensure objectpond package is on sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from objectpond.boot import create_default_environment
from objectpond.kernel.image import ImageSerializer
from objectpond.mcp_server import ObjectPondMCPServer, create_headless_controller, run_stdio_server


def build_source_bundle() -> Dict[str, str]:
    """Scans all Python source files in the objectpond package and packs them into a single dict."""
    bundle: Dict[str, str] = {}
    pkg_dir = BASE_DIR / "objectpond"
    for root, _dirs, files in os.walk(pkg_dir):
        for f in files:
            if f.endswith(".py") and not f.startswith("."):
                full_path = Path(root) / f
                rel_path = full_path.relative_to(BASE_DIR).as_posix()
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        bundle[rel_path] = fp.read()
                except Exception as exc:
                    print(f"Warning reading {full_path}: {exc}", file=sys.stderr)
    return bundle


def get_default_image_bytes() -> bytes:
    """Returns saved objectpond.image bytes from disk or generates a fresh snapshot."""
    image_path = BASE_DIR / "objectpond.image"
    if image_path.exists():
        try:
            with open(image_path, "rb") as fp:
                return fp.read()
        except Exception as exc:
            print(f"Error reading {image_path}: {exc}", file=sys.stderr)

    # Generate a fresh default snapshot in memory (only POST /api/image/save writes objectpond.image to disk)
    smalltalk, world = create_default_environment(1280, 800)
    serializer = ImageSerializer(smalltalk)
    img_bytes = serializer.save_image_bytes(world)
    return img_bytes


class BridgeHub:
    """
    Coordinates live browser Pyodide bridge sessions with a lazy headless Python fallback.
    """

    def __init__(self, base_dir: Path = BASE_DIR):
        self.base_dir = base_dir
        self._cond = threading.Condition()
        self._queue: Deque[Dict[str, Any]] = deque()
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._active_polls: int = 0
        self._last_poll_ts: float = 0.0
        self._headless_lock = threading.Lock()
        self._headless_controller: Optional[Any] = None

    def is_browser_connected(self, max_idle_sec: float = 25.0) -> bool:
        with self._cond:
            if self._active_polls > 0:
                return True
            return (time.monotonic() - self._last_poll_ts) < max_idle_sec and self._last_poll_ts > 0.0

    def poll_command(self, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + timeout
        with self._cond:
            self._active_polls += 1
            self._last_poll_ts = time.monotonic()
            try:
                while not self._queue:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._last_poll_ts = time.monotonic()
                        return None
                    self._cond.wait(timeout=remaining)
                self._last_poll_ts = time.monotonic()
                return self._queue.popleft()
            finally:
                self._active_polls -= 1

    def submit_result(self, payload: Dict[str, Any]) -> None:
        req_id = payload.get("id")
        if not req_id:
            return
        with self._cond:
            entry = self._pending.get(req_id)
            if entry is not None:
                entry["payload"] = payload
                entry["event"].set()

    def _get_headless(self) -> Any:
        with self._headless_lock:
            if self._headless_controller is None:
                self._headless_controller = create_headless_controller(self.base_dir)
            return self._headless_controller

    def execute(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        if self.is_browser_connected():
            req_id = uuid.uuid4().hex
            evt = threading.Event()
            with self._cond:
                if len(self._queue) >= MAX_BRIDGE_QUEUE:
                    raise RuntimeError("Bridge command queue is full")
                self._pending[req_id] = {"event": evt, "payload": None}
                self._queue.append({"id": req_id, "method": method, "params": params or {}})
                self._cond.notify_all()
            if not evt.wait(timeout=timeout):
                with self._cond:
                    self._pending.pop(req_id, None)
                raise TimeoutError(f"Browser bridge timed out executing '{method}'")
            with self._cond:
                entry = self._pending.pop(req_id, {})
            payload = entry.get("payload") or {}
            if "error" in payload and payload["error"]:
                raise RuntimeError(str(payload["error"]))
            return payload.get("result") or {}

        with self._headless_lock:
            ctrl = self._headless_controller
            if ctrl is None:
                ctrl = create_headless_controller(self.base_dir)
                self._headless_controller = ctrl
            return ctrl.dispatch(method, params)


DEFAULT_BRIDGE_HUB = BridgeHub(BASE_DIR)


class ObjectPondHandler(SimpleHTTPRequestHandler):
    """HTTP Request handler serving static files + ObjectPond WebAssembly & MCP API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def _bridge_hub(self) -> BridgeHub:
        return getattr(self.server, "bridge_hub", DEFAULT_BRIDGE_HUB)

    def _mcp_server(self) -> ObjectPondMCPServer:
        srv = getattr(self.server, "mcp_server", None)
        if srv is None:
            hub = self._bridge_hub()
            srv = ObjectPondMCPServer(hub.execute)
            setattr(self.server, "mcp_server", srv)
        return srv

    def _send_json(self, status: int, obj: Any, extra_headers: Optional[Dict[str, str]] = None) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _is_allowed_origin(origin: str) -> bool:
        try:
            parsed = urlparse(origin)
            return parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1", "::1")
        except Exception:
            return False

    def _check_request_security(self, require_auth: bool = False) -> bool:
        origin = self.headers.get("Origin")
        if origin and not self._is_allowed_origin(origin):
            self._send_json(403, {"error": "Cross-origin request rejected"})
            return False
        expected_token = getattr(self.server, "auth_token", None)
        if require_auth and expected_token:
            auth = self.headers.get("Authorization", "")
            prefix = "Bearer "
            provided = auth[len(prefix):] if auth.startswith(prefix) else ""
            if not hmac.compare_digest(provided, expected_token):
                self._send_json(401, {"error": "Unauthorized"})
                return False
        return True

    def _read_body(self) -> Optional[bytes]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_len)
        except ValueError:
            self._send_json(400, {"error": "Invalid Content-Length header"})
            return None
        if length < 0:
            self._send_json(400, {"error": "Negative Content-Length header"})
            return None
        if length > MAX_POST_BYTES:
            self._send_json(413, {"error": f"Payload exceeds {MAX_POST_BYTES} bytes limit"})
            return None
        return self.rfile.read(length)

    def end_headers(self):
        origin = self.headers.get("Origin") if hasattr(self, "headers") else None
        if origin and self._is_allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id")
            self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_path = self.path.split("?")[0]

        if parsed_path == "/api/source-bundle":
            bundle = build_source_bundle()
            data = json.dumps(bundle).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed_path == "/api/image/default":
            img_bytes = get_default_image_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(img_bytes)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(img_bytes)
            return

        if parsed_path == "/api/changes":
            changes_path = BASE_DIR / "objectpond.changes"
            if changes_path.exists():
                with open(changes_path, "r", encoding="utf-8") as fp:
                    content = fp.read()
            else:
                smalltalk, _world = create_default_environment(1280, 800)
                content = smalltalk.changes_log.export_chunk_format()
            data = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed_path == "/api/fs/read":
            query = parse_qs(urlparse(self.path).query)
            anchor = (query.get("anchor") or ["assets"])[0]
            rel_path = (query.get("path") or [""])[0].lstrip("/")
            anchors = {
                "assets": (BASE_DIR / "assets").resolve(),
                "image_dir": BASE_DIR.resolve(),
                "workspace": BASE_DIR.resolve(),
            }
            root = anchors.get(anchor)
            if root is None or not rel_path:
                self._send_json(400, {"error": "Invalid anchor or path"})
                return
            try:
                target = (root / rel_path).resolve()
                if not target.is_relative_to(root) or any(part.startswith(".") for part in target.relative_to(root).parts):
                    self._send_json(403, {"error": "Access denied"})
                    return
                if not target.is_file():
                    self._send_json(404, {"error": "File not found"})
                    return
                if target.stat().st_size > MAX_REF_FETCH_BYTES:
                    self._send_json(413, {"error": "File exceeds 16 MB limit"})
                    return
                data = target.read_bytes()
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed_path == "/api/url/fetch":
            query = parse_qs(urlparse(self.path).query)
            target_url = (query.get("url") or [""])[0]
            parsed_url = urlparse(target_url)
            if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
                self._send_json(400, {"error": "Only http/https URLs are supported"})
                return
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "ObjectPond/1.1"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read(MAX_REF_FETCH_BYTES + 1)
                    if len(data) > MAX_REF_FETCH_BYTES:
                        self._send_json(413, {"error": "Remote payload exceeds 16 MB limit"})
                        return
                    ctype = resp.headers.get("Content-Type") or "application/octet-stream"
            except Exception as exc:
                self._send_json(502, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed_path == "/api/bridge/poll":
            if not self._check_request_security(require_auth=True):
                return
            cmd = self._bridge_hub().poll_command(timeout=20.0)
            if cmd is None:
                self.send_response(204)
                self.end_headers()
                return
            self._send_json(200, cmd)
            return

        if parsed_path == "/mcp":
            if not self._check_request_security(require_auth=True):
                return
            accept = self.headers.get("Accept", "")
            if "text/event-stream" in accept:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(b"event: endpoint\ndata: /mcp\n\n")
                self.wfile.flush()
                return
            self._send_json(200, {
                "name": "objectpond-mcp",
                "transport": "streamable-http",
                "endpoint": "/mcp",
                "browser_connected": self._bridge_hub().is_browser_connected(),
            })
            return

        if parsed_path in ALLOWED_STATIC_FILES:
            rel_file, content_type = ALLOWED_STATIC_FILES[parsed_path]
            file_path = BASE_DIR / rel_file
            if file_path.is_file():
                data = file_path.read_bytes()
                if rel_file == "index.html":
                    from objectpond import __version__

                    data = data.replace(
                        b'id="boot-logo-title">ObjectPond</div>',
                        f'id="boot-logo-title">ObjectPond {__version__}</div>'.encode("utf-8"),
                    )
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed_path = self.path.split("?")[0]

        if parsed_path == "/mcp":
            if not self._check_request_security(require_auth=True):
                return
            raw = self._read_body()
            if raw is None:
                return
            try:
                payload = json.loads(raw.decode("utf-8"))
                resp = self._mcp_server().handle_payload(payload)
                session_id = self.headers.get("Mcp-Session-Id") or uuid.uuid4().hex
                if resp is None:
                    self.send_response(202)
                    self.send_header("Mcp-Session-Id", session_id)
                    self.end_headers()
                    return
                self._send_json(200, resp, extra_headers={"Mcp-Session-Id": session_id})
            except Exception as exc:
                self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
            return

        if parsed_path == "/api/mcp/dispatch":
            if not self._check_request_security(require_auth=True):
                return
            raw = self._read_body()
            if raw is None:
                return
            try:
                body = json.loads(raw.decode("utf-8"))
                result = self._bridge_hub().execute(body["method"], body.get("params") or {})
                self._send_json(200, {"result": result})
            except Exception as exc:
                self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return

        if parsed_path == "/api/bridge/result":
            if not self._check_request_security(require_auth=True):
                return
            raw = self._read_body()
            if raw is None:
                return
            try:
                body = json.loads(raw.decode("utf-8"))
                self._bridge_hub().submit_result(body)
                self._send_json(200, {"status": "ok"})
            except Exception as exc:
                self._send_json(400, {"status": "error", "message": str(exc)})
            return

        if parsed_path == "/api/image/save":
            if not self._check_request_security(require_auth=True):
                return
            body = self._read_body()
            if body is None:
                return
            try:
                raw_json = (
                    ImageSerializer._safe_zlib_decompress(body, wbits=16 + zlib.MAX_WBITS)
                    if body[:2] == b"\x1f\x8b"
                    else body
                )
                snap = json.loads(raw_json.decode("utf-8"))
                if not isinstance(snap, dict) or "objects" not in snap or "world" not in snap:
                    raise ValueError("Invalid ObjectPond image snapshot structure")
            except Exception as exc:
                self._send_json(400, {"status": "error", "message": f"Invalid image payload: {exc}"})
                return
            try:
                image_path = BASE_DIR / "objectpond.image"
                with open(image_path, "wb") as fp:
                    fp.write(body)
                self._send_json(200, {"status": "ok", "bytes_saved": len(body)})
            except Exception as exc:
                self._send_json(500, {"status": "error", "message": str(exc)})
            return

        self.send_response(404)
        self.end_headers()


def run_server(
    port: int = 8000,
    host: str = "127.0.0.1",
    auth_token: Optional[str] = None,
) -> None:
    server = ThreadingHTTPServer((host, port), ObjectPondHandler)
    server.bridge_hub = BridgeHub(BASE_DIR)  # type: ignore[attr-defined]
    server.mcp_server = ObjectPondMCPServer(server.bridge_hub.execute)  # type: ignore[attr-defined]
    server.auth_token = auth_token  # type: ignore[attr-defined]
    print(f"==================================================")
    print(f" ObjectPond Server running at http://{host}:{port}")
    print(f" MCP HTTP endpoint at http://{host}:{port}/mcp")
    print(f"==================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ObjectPond Streaming Image & MCP Server")
    parser.add_argument("positional_port", nargs="?", type=int, default=None, help="Port number")
    parser.add_argument("-p", "--port", type=int, default=8765, help="Port number (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--auth-token", default=None, help="Optional Bearer token for API/MCP endpoints")
    parser.add_argument("--mcp-stdio", action="store_true", help="Run MCP server over stdio instead of HTTP")
    parser.add_argument("--bridge-url", default="http://localhost:8765", help="Bridge URL for --mcp-stdio")
    parser.add_argument("--headless", action="store_true", help="Force headless mode in --mcp-stdio")
    args = parser.parse_args()
    if args.mcp_stdio:
        run_stdio_server(bridge_url=args.bridge_url, headless=args.headless)
    else:
        run_server(
            port=args.positional_port if args.positional_port is not None else args.port,
            host=args.host,
            auth_token=args.auth_token,
        )
