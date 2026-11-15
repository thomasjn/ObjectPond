import base64
from http.server import ThreadingHTTPServer
import json
import struct
import threading
import unittest
import urllib.error
import urllib.request

from objectpond.boot import create_default_environment
from objectpond.mcp_server import ObjectPondMCPServer
from objectpond.morphic.software_canvas import SoftwareCanvasBackend, render_world_png
from objectpond.runtime_bridge import ObjectPondController
from objectpond.tools.debugger import DebuggerWindow
from server import BridgeHub, ObjectPondHandler


class TestMCPControllerAndDebugger(unittest.TestCase):
    def setUp(self):
        self.smalltalk, self.world = create_default_environment(800, 600)
        self.ctrl = ObjectPondController(self.smalltalk, self.world)

    def test_define_class_spawn_inspect_mutate_and_evaluate(self):
        res_cls = self.ctrl.dispatch("define_class", {
            "category": "User-Objects",
            "source": (
                "class CounterMorph(Morph):\n"
                "    def __init__(self, x=50, y=50, width=80, height=40):\n"
                "        super().__init__(x, y, width, height, color='#4c566a')\n"
                "        self.count = 0\n"
                "    def wants_steps(self):\n"
                "        return True\n"
                "    def step(self):\n"
                "        self.count += 1\n"
            ),
        })
        self.assertEqual(res_cls["class_name"], "CounterMorph")

        spawned = self.ctrl.dispatch("spawn_instance", {
            "class_name": "CounterMorph",
            "bind_name": "my_counter",
        })
        oid = spawned["object_id"]
        self.assertTrue(spawned["added_to_world"])

        self.ctrl.dispatch("control_stepping", {"action": "step", "cycles": 3})
        inspected = self.ctrl.dispatch("inspect_object", {"object_id": oid})
        self.assertEqual(inspected["class"], "CounterMorph")
        self.assertEqual(inspected["fields"]["count"]["repr"], "3")

        self.ctrl.dispatch("mutate_object", {
            "global_name": "my_counter",
            "attr": "count",
            "value_expr": "42",
        })
        ev = self.ctrl.dispatch("evaluate", {"code": "my_counter.count * 2"})
        self.assertTrue(ev["ok"])
        self.assertEqual(ev["result_repr"], "84")

        tree = self.ctrl.dispatch("list_morphs", {"max_depth": 3})
        classes = [m["class"] for m in tree["world"]["submorphs"]]
        self.assertIn("CounterMorph", classes)

    def test_exception_capture_and_debugger_hot_patch(self):
        self.ctrl.dispatch("define_class", {
            "category": "User-Objects",
            "source": (
                "class BuggyMorph(Morph):\n"
                "    def __init__(self, x=10, y=10, width=50, height=50):\n"
                "        super().__init__(x, y, width, height)\n"
                "        self.value = 10\n"
                "    def wants_steps(self):\n"
                "        return True\n"
                "    def step(self):\n"
                "        divisor = 0\n"
                "        return self.value / divisor\n"
            ),
        })
        self.ctrl.dispatch("spawn_instance", {"class_name": "BuggyMorph", "bind_name": "buggy"})
        self.ctrl.dispatch("control_stepping", {"action": "step", "cycles": 1})

        excs = self.ctrl.dispatch("get_exceptions")["exceptions"]
        self.assertGreaterEqual(len(excs), 1)
        latest = excs[-1]
        self.assertEqual(latest["exc_type"], "ZeroDivisionError")

        detail = self.ctrl.dispatch("get_exception_detail", {"exc_id": latest["id"]})["exception"]
        self.assertTrue(any(f["function"] == "step" and f["locals"].get("divisor") == "0" for f in detail["frames"]))

        dbg_res = self.ctrl.dispatch("open_debugger", {"exc_id": latest["id"]})
        self.assertIsNotNone(dbg_res["window_id"])
        dbg_win = [m for m in self.world.submorphs if isinstance(m, DebuggerWindow)][-1]
        self.assertEqual(dbg_win._editing_class, "BuggyMorph")
        self.assertEqual(dbg_win._editing_method, "step")

        # Hot-patch the bug directly through DebuggerWindow
        fixed_src = (
            "def step(self):\n"
            "    divisor = 2\n"
            "    self.last = self.value / divisor\n"
        )
        dbg_win.on_accept_source(fixed_src)
        self.ctrl.dispatch("clear_exceptions")
        self.ctrl.dispatch("control_stepping", {"action": "step", "cycles": 1})
        self.assertEqual(self.ctrl.dispatch("get_exceptions")["exceptions"], [])
        self.assertEqual(self.world.workspace_globals["buggy"].last, 5.0)

    def test_headless_screenshot_and_mcp_protocol(self):
        png = render_world_png(self.world)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        w, h = struct.unpack(">II", png[16:24])
        self.assertEqual((w, h), (800, 600))

        # Verify pure-Python SoftwareCanvasBackend directly as well
        sw = SoftwareCanvasBackend(120, 60)
        sw.fill_rect(5, 5, 40, 20, "#88c0d0")
        sw.draw_text("Hi", 10, 20, "#ffffff")
        self.assertTrue(sw.to_png_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

        mcp = ObjectPondMCPServer(self.ctrl.dispatch)
        init_resp = mcp.handle_payload({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "objectpond-mcp")
        self.assertIn("Morphic", init_resp["result"]["instructions"])

        guide_resp = mcp.handle_payload({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "resources/read",
            "params": {"uri": "objectpond://guide"},
        })
        self.assertIn("draw_on", guide_resp["result"]["contents"][0]["text"])

        tools_resp = mcp.handle_payload({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("objectpond_screenshot", tool_names)
        self.assertIn("objectpond_define_class", tool_names)

        shot_resp = mcp.handle_payload({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "objectpond_screenshot", "arguments": {}},
        })
        content = shot_resp["result"]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["mimeType"], "image/png")
        decoded = base64.b64decode(content[0]["data"])
        self.assertTrue(decoded.startswith(b"\x89PNG\r\n\x1a\n"))

        res_resp = mcp.handle_payload({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "objectpond://transcript"},
        })
        from objectpond import __version__

        self.assertIn(f"ObjectPond {__version__} booted", res_resp["result"]["contents"][0]["text"])


class TestMCPServerHTTPAndBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ObjectPondHandler)
        cls.httpd.bridge_hub = BridgeHub()  # type: ignore[attr-defined]
        cls.httpd.mcp_server = ObjectPondMCPServer(cls.httpd.bridge_hub.execute)  # type: ignore[attr-defined]
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post_json(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_http_mcp_headless_and_browser_bridge_roundtrip(self):
        # 1. Headless fallback when no browser is connected
        resp = self._post_json("/mcp", {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "objectpond_status", "arguments": {}},
        })
        text = resp["result"]["content"][0]["text"]
        self.assertIn("morph_count", text)

        # 2. Simulated browser polling /api/bridge/poll and posting /api/bridge/result
        def fake_browser():
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/bridge/poll", timeout=10.0) as r:
                cmd = json.loads(r.read().decode("utf-8"))
            self._post_json("/api/bridge/result", {
                "id": cmd["id"],
                "result": {"from_browser": True, "method": cmd["method"]},
            })

        t = threading.Thread(target=fake_browser, daemon=True)
        t.start()
        # Wait briefly so fake_browser enters poll_command
        while not self.httpd.bridge_hub.is_browser_connected():  # type: ignore[attr-defined]
            pass

        bridged = self._post_json("/mcp", {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "objectpond_status", "arguments": {}},
        })
        t.join(timeout=5.0)
        self.assertIn('"from_browser": true', bridged["result"]["content"][0]["text"])

    def test_security_hardening_static_allowlist_cors_and_image_validation(self):
        # 1. Internal files outside static allowlist must return 404
        for blocked in ("/AGENTS.md", "/server.py", "/.gitignore"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}{blocked}", timeout=5.0)
            self.assertEqual(ctx.exception.code, 404)

        # 2. Cross-origin POST /mcp must be rejected with 403
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/mcp",
            data=b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5.0)
        self.assertEqual(ctx.exception.code, 403)

        # 3. Invalid image payload to /api/image/save must be rejected with 400
        bad_save = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/image/save",
            data=b"not-a-valid-image",
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(bad_save, timeout=5.0)
        self.assertEqual(ctx.exception.code, 400)

    def test_dunder_mutation_blocked_and_sensitive_locals_redacted(self):
        st, world = create_default_environment(640, 480)
        ctrl = ObjectPondController(st, world)
        with self.assertRaises(ValueError):
            ctrl.dispatch("mutate_object", {"object_id": "world", "attr": "__class__", "value_expr": "dict"})

        def fail_with_secret():
            api_token = "super-secret-123"
            _ = api_token
            raise RuntimeError("boom")

        try:
            fail_with_secret()
        except RuntimeError as exc:
            rec = st.record_exception(exc, context="test")
            self.assertEqual(rec["frames"][-1]["locals"]["api_token"], "<redacted>")

    def test_import_object_from_image_file(self):
        from objectpond.kernel.image import ImageSerializer

        src_st, src_world = create_default_environment(640, 480)
        badge_cls = src_st.define_class(
            "User-Objects",
            "class BadgeMorph(Morph):\n"
            "    def __init__(self, x=20, y=20, width=60, height=30):\n"
            "        super().__init__(x, y, width, height, color='#88c0d0')\n"
            "        self.tag = 'imported-ok'\n",
        )
        src_world.add_morph(badge_cls())
        img_bytes = ImageSerializer(src_st).save_image_bytes(src_world)

        dst_st, dst_world = create_default_environment(640, 480)
        self.assertIsNone(dst_st.get_class("BadgeMorph"))
        win = dst_world.open_image_object_importer(img_bytes, "badge.image")
        idx = next(i for i, c in enumerate(win.candidates) if c["class"] == "BadgeMorph")
        win.object_list.select_index(idx, notify=True)
        imported = win.on_import_clicked()

        self.assertIsNotNone(dst_st.get_class("BadgeMorph"))
        self.assertEqual(imported.tag, "imported-ok")
        self.assertIn(imported, dst_world.submorphs)


if __name__ == "__main__":
    unittest.main()
