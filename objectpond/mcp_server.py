import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


from . import __version__

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "objectpond-mcp", "version": __version__}

OBJECTPOND_GUIDE = """ObjectPond is a live Morphic / Morphic development environment implemented in Python.

Key Concepts:
- Language: All classes, methods, and evaluations use standard Python (not Smalltalk-80 syntax).
- Live Image & Hot-Patching: `Smalltalk` (SystemDictionary) manages categories, classes, and `ChangesLog`.
  - `objectpond_define_class` compiles a Python `class ...` and migrates existing live instances in memory.
  - `objectpond_compile_method` hot-patches a single `def method(self, ...):` onto a live class immediately.
- Morphic Desktop: `World` (WorldMorph) is the root desktop containing `Morph` and `SystemWindowMorph` instances.
  - Globals available in `objectpond_evaluate`: `World`, `Smalltalk`, `Transcript` (`Transcript.show(...)`), `Morph`, `Form`, `DisplayCanvas`, and all registered classes.
  - Custom `Morph` lifecycle:
    - `__init__(self, x=100, y=100, width=160, height=100, ...)` calling `super().__init__(x, y, width, height, ...)`
    - `draw_on(self, canvas)` using `canvas.fill_rect`, `stroke_rect`, `fill_round_rect`, `fill_circle`, `draw_line`, `draw_text`, `blit_form`
    - `wants_steps(self) -> bool` and `step(self)` for animations/simulations (call `self.changed()` to trigger redraw)
    - `on_mouse_down(self, px, py, button)`, `on_mouse_move(self, px, py, dx, dy)`, `on_mouse_up(self, px, py, button)`, `on_key_down(self, key, ...)`

Recommended Workflow:
1. Inspect the environment with `objectpond_status`, `objectpond_screenshot`, `objectpond_list_morphs`, and `objectpond_list_classes`.
2. Inject or modify classes with `objectpond_define_class` / `objectpond_compile_method`, then instantiate with `objectpond_spawn_instance`.
3. Inspect or mutate live instances with `objectpond_inspect_object`, `objectpond_mutate_object`, and `objectpond_evaluate`.
4. Debug errors with `objectpond_get_exceptions`, `objectpond_get_exception_detail`, `objectpond_open_debugger`, and `objectpond_control_stepping`.
5. Operate the UI with `objectpond_mouse_event`, `objectpond_key_event`, `objectpond_type_text`, `objectpond_open_tool`, and `objectpond_save_image`.
"""


def _tool_def(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


MCP_TOOLS: List[Dict[str, Any]] = [
    _tool_def("objectpond_status", "Get current ObjectPond World status (extent, morph count, class count, exceptions, stepping state).", {}),
    _tool_def("objectpond_screenshot", "Capture a PNG screenshot of the live ObjectPond Morphic desktop.", {}),
    _tool_def(
        "objectpond_define_class",
        "Define or redefine a Python class in SystemDictionary and migrate live instances in memory.",
        {
            "category": {"type": "string", "description": "System category name (e.g. 'User-Objects')."},
            "source": {"type": "string", "description": "Full Python class definition source."},
            "author": {"type": "string", "description": "Author stamp for ChangesLog."},
        },
        required=["category", "source"],
    ),
    _tool_def(
        "objectpond_compile_method",
        "Hot-patch or add a single method on a registered class; live instances immediately use it.",
        {
            "class_name": {"type": "string", "description": "Target registered class name."},
            "source": {"type": "string", "description": "Python 'def method_name(self, ...):' source."},
            "protocol": {"type": "string", "description": "Method protocol/category (default: 'operations')."},
            "author": {"type": "string", "description": "Author stamp for ChangesLog."},
        },
        required=["class_name", "source"],
    ),
    _tool_def(
        "objectpond_list_classes",
        "List registered categories and classes in SystemDictionary.",
        {"category": {"type": "string", "description": "Optional category filter."}},
    ),
    _tool_def(
        "objectpond_get_source",
        "Get the full class definition or a specific method's source code.",
        {
            "class_name": {"type": "string", "description": "Registered class name."},
            "method_name": {"type": "string", "description": "Optional method name."},
        },
        required=["class_name"],
    ),
    _tool_def(
        "objectpond_evaluate",
        "Evaluate Python code in the live World workspace context (with World, Smalltalk, Transcript).",
        {"code": {"type": "string", "description": "Python expression or statements to execute."}},
        required=["code"],
    ),
    _tool_def(
        "objectpond_spawn_instance",
        "Instantiate a class, optionally add it to the WorldMorph desktop, and optionally bind it to a workspace global.",
        {
            "class_name": {"type": "string", "description": "Class name to instantiate."},
            "args": {"type": "array", "description": "Positional constructor arguments."},
            "kwargs": {"type": "object", "description": "Keyword constructor arguments."},
            "add_to_world": {"type": "boolean", "description": "Add Morph instance to World (default: true)."},
            "bind_name": {"type": "string", "description": "Optional global variable name in workspace_globals."},
        },
        required=["class_name"],
    ),
    _tool_def(
        "objectpond_list_morphs",
        "List the live WorldMorph submorph hierarchy with object IDs, bounds, and titles.",
        {"max_depth": {"type": "integer", "description": "Maximum tree depth (default: 6)."}},
    ),
    _tool_def(
        "objectpond_inspect_object",
        "Inspect a live object's class, fields, object IDs, and methods.",
        {
            "object_id": {"type": "string", "description": "Object ID (e.g. 'world', 'obj:3')."},
            "global_name": {"type": "string", "description": "Workspace global name."},
        },
    ),
    _tool_def(
        "objectpond_mutate_object",
        "Set an attribute on a live object by evaluating a Python expression.",
        {
            "attr": {"type": "string", "description": "Attribute name to set."},
            "value_expr": {"type": "string", "description": "Python expression for the new value."},
            "object_id": {"type": "string", "description": "Object ID."},
            "global_name": {"type": "string", "description": "Workspace global name."},
        },
        required=["attr", "value_expr"],
    ),
    _tool_def("objectpond_get_exceptions", "List captured runtime exceptions from stepping and evaluations.", {}),
    _tool_def(
        "objectpond_get_exception_detail",
        "Get full traceback, stack frames, locals, and self object IDs for a captured exception.",
        {"exc_id": {"type": "integer", "description": "Exception ID (defaults to latest)."}},
    ),
    _tool_def(
        "objectpond_open_debugger",
        "Open a Morphic DebuggerWindow on the desktop for a captured exception.",
        {"exc_id": {"type": "integer", "description": "Exception ID (defaults to latest)."}},
    ),
    _tool_def(
        "objectpond_control_stepping",
        "Pause, resume, or step WorldMorph animation cycles.",
        {
            "action": {"type": "string", "enum": ["status", "pause", "resume", "step"], "description": "Stepping action."},
            "cycles": {"type": "integer", "description": "Number of cycles when action is 'step'."},
        },
        required=["action"],
    ),
    _tool_def(
        "objectpond_mouse_event",
        "Send a mouse event (down, move, up, wheel) to the WorldMorph desktop.",
        {
            "event_type": {"type": "string", "enum": ["down", "move", "up", "wheel"]},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "button": {"type": "integer"},
            "alt_key": {"type": "boolean"},
            "shift_key": {"type": "boolean"},
            "delta_y": {"type": "number"},
        },
        required=["event_type", "x", "y"],
    ),
    _tool_def(
        "objectpond_key_event",
        "Send a key_down event to the focused Morph.",
        {
            "key": {"type": "string"},
            "ctrl_key": {"type": "boolean"},
            "meta_key": {"type": "boolean"},
            "shift_key": {"type": "boolean"},
            "alt_key": {"type": "boolean"},
        },
        required=["key"],
    ),
    _tool_def(
        "objectpond_type_text",
        "Type a string of characters into the currently focused Morph.",
        {"text": {"type": "string"}},
        required=["text"],
    ),
    _tool_def(
        "objectpond_open_tool",
        "Open a development tool window on the desktop.",
        {
            "tool": {
                "type": "string",
                "enum": ["browser", "workspace", "inspector", "transcript", "changes", "debugger", "bouncing_atoms", "bitblt_paint"],
            },
            "target_id": {"type": "string", "description": "Target object_id for inspector."},
            "class_name": {"type": "string", "description": "Initial class for browser."},
            "text": {"type": "string", "description": "Initial text for workspace."},
            "exc_id": {"type": "integer", "description": "Exception ID for debugger."},
        },
        required=["tool"],
    ),
    _tool_def(
        "objectpond_get_transcript",
        "Read recent Transcript lines.",
        {"limit": {"type": "integer", "description": "Maximum lines to return (default: 100)."}},
    ),
    _tool_def(
        "objectpond_get_changes",
        "Read recent Smalltalk ChangesLog entries.",
        {"limit": {"type": "integer", "description": "Maximum entries to return (default: 50)."}},
    ),
    _tool_def("objectpond_save_image", "Save the current live image snapshot to objectpond.image.", {}),
]

_TOOL_TO_CONTROLLER_METHOD: Dict[str, str] = {
    t["name"]: t["name"][len("objectpond_"):] for t in MCP_TOOLS
}


class ObjectPondMCPServer:
    """Zero-dependency MCP JSON-RPC 2.0 protocol handler for ObjectPond."""

    def __init__(self, dispatch_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]]):
        self.dispatch_fn = dispatch_fn

    def handle_payload(self, payload: Any) -> Optional[Any]:
        if isinstance(payload, list):
            responses = [self._handle_one(item) for item in payload]
            filtered = [r for r in responses if r is not None]
            return filtered or None
        return self._handle_one(payload)

    def _handle_one(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        # Notifications have no id and expect no response
        if req_id is None and method.startswith("notifications/"):
            return None

        try:
            if method == "initialize":
                client_proto = params.get("protocolVersion") or MCP_PROTOCOL_VERSION
                result = {
                    "protocolVersion": client_proto,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                    },
                    "serverInfo": SERVER_INFO,
                    "instructions": OBJECTPOND_GUIDE,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": MCP_TOOLS}
            elif method == "tools/call":
                result = self._call_tool(params.get("name", ""), params.get("arguments") or {})
            elif method == "resources/list":
                result = {
                    "resources": [
                        {"uri": "objectpond://guide", "name": "ObjectPond Environment Guide", "mimeType": "text/markdown"},
                        {"uri": "objectpond://transcript", "name": "Transcript", "mimeType": "text/plain"},
                        {"uri": "objectpond://changes", "name": "ChangesLog", "mimeType": "application/json"},
                        {"uri": "objectpond://world/tree", "name": "World Morph Tree", "mimeType": "application/json"},
                    ]
                }
            elif method == "resources/read":
                result = self._read_resource(params.get("uri", ""))
            else:
                return self._error(req_id, -32601, f"Method not found: {method}")

            if req_id is None:
                return None
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:
            if req_id is None:
                return None
            return self._error(req_id, -32603, str(exc))

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ctrl_method = _TOOL_TO_CONTROLLER_METHOD.get(tool_name)
        if ctrl_method is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            }
        try:
            res = self.dispatch_fn(ctrl_method, arguments)
            if tool_name == "objectpond_screenshot":
                return {
                    "content": [
                        {
                            "type": "image",
                            "data": res["data_base64"],
                            "mimeType": res.get("mime_type", "image/png"),
                        },
                        {
                            "type": "text",
                            "text": f"Captured screenshot ({res.get('width')}x{res.get('height')})",
                        },
                    ]
                }
            return {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
            }
        except Exception as exc:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
            }

    def _read_resource(self, uri: str) -> Dict[str, Any]:
        if uri == "objectpond://guide":
            return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": OBJECTPOND_GUIDE}]}
        if uri == "objectpond://transcript":
            res = self.dispatch_fn("get_transcript", {"limit": 500})
            text = "\n".join(res.get("lines", []))
            return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]}
        if uri == "objectpond://changes":
            res = self.dispatch_fn("get_changes", {"limit": 200})
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(res, indent=2)}]}
        if uri == "objectpond://world/tree":
            res = self.dispatch_fn("list_morphs", {"max_depth": 8})
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(res, indent=2)}]}
        raise ValueError(f"Unknown resource URI: {uri}")

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def create_headless_controller(base_dir: Optional[Path] = None) -> Any:
    from objectpond.boot import create_default_environment
    from objectpond.kernel.image import ImageSerializer
    from objectpond.kernel.object_memory import ChangesLog, SystemDictionary
    from objectpond.runtime_bridge import ObjectPondController

    root = base_dir or Path(__file__).resolve().parent.parent
    image_path = root / "objectpond.image"
    if image_path.exists():
        smalltalk = SystemDictionary(changes_log=ChangesLog())
        serializer = ImageSerializer(smalltalk)
        world = serializer.load_image_bytes(image_path.read_bytes())
    else:
        smalltalk, world = create_default_environment(1280, 800)
    return ObjectPondController(smalltalk, world, image_save_path=image_path)


def run_stdio_server(bridge_url: Optional[str] = "http://localhost:8765", headless: bool = False) -> None:
    local_controller: Optional[Any] = None

    def dispatch(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal local_controller
        if not headless and bridge_url:
            endpoint = bridge_url.rstrip("/") + "/api/mcp/dispatch"
            body = json.dumps({"method": method, "params": params}).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=20.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if "error" in data:
                        raise RuntimeError(data["error"])
                    return data["result"]
            except urllib.error.URLError:
                pass
        if local_controller is None:
            local_controller = create_headless_controller()
        return local_controller.dispatch(method, params)

    mcp = ObjectPondMCPServer(dispatch)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue

        resp = mcp.handle_payload(payload)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ObjectPond MCP Stdio Server")
    parser.add_argument("--bridge-url", default="http://localhost:8765", help="Running ObjectPond server URL")
    parser.add_argument("--headless", action="store_true", help="Run standalone headless without connecting to server.py")
    args = parser.parse_args()
    run_stdio_server(bridge_url=args.bridge_url, headless=args.headless)
