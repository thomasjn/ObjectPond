/**
 * ObjectPond Browser WebAssembly Virtual Machine Host
 * Wires HTML5 Canvas + BitBlt bridge, loads Pyodide, mounts the ObjectPond kernel,
 * hydrates live .image snapshots, and connects DOM event handlers to Morphic.
 */

(function () {
    const canvas = document.getElementById("world-canvas");
    const ctx = canvas.getContext("2d", { alpha: false });
    const statusText = document.getElementById("status-text");
    const loadingOverlay = document.getElementById("loading-overlay");
    const dragOverlay = document.getElementById("drag-overlay");

    function setStatus(msg) {
        if (statusText) statusText.innerText = msg;
    }

    function hideLoading() {
        if (loadingOverlay) {
            loadingOverlay.style.opacity = "0";
            setTimeout(() => {
                loadingOverlay.style.display = "none";
            }, 400);
        }
    }

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        if (window.pyodideWorld) {
            try {
                window.pyodide.runPython(`world.set_extent(${canvas.width}, ${canvas.height}); world.changed()`);
            } catch (e) {
                console.error("Resize error:", e);
            }
        }
    }
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    // Offscreen canvas for Form BitBlt blitting
    const offscreenCanvas = document.createElement("canvas");
    const offscreenCtx = offscreenCanvas.getContext("2d");

    // 1. ObjectPondBridge implementing methods expected by JSCanvasBackend
    window.ObjectPondBridge = {
        saveClip(x, y, w, h) {
            ctx.save();
            ctx.beginPath();
            ctx.rect(x, y, w, h);
            ctx.clip();
        },

        restoreClip() {
            ctx.restore();
        },

        fillRect(x, y, w, h, color) {
            ctx.fillStyle = color;
            ctx.fillRect(x, y, w, h);
        },

        strokeRect(x, y, w, h, color, lineWidth) {
            ctx.strokeStyle = color;
            ctx.lineWidth = lineWidth || 1.0;
            ctx.strokeRect(x, y, w, h);
        },

        fillRoundRect(x, y, w, h, radius, fillColor, strokeColor, lineWidth) {
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(x, y, w, h, radius);
            } else {
                ctx.moveTo(x + radius, y);
                ctx.arcTo(x + w, y, x + w, y + h, radius);
                ctx.arcTo(x + w, y + h, x, y + h, radius);
                ctx.arcTo(x, y + h, x, y, radius);
                ctx.arcTo(x, y, x + w, y, radius);
                ctx.closePath();
            }
            if (fillColor && fillColor !== "") {
                ctx.fillStyle = fillColor;
                ctx.fill();
            }
            if (strokeColor && strokeColor !== "") {
                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = lineWidth || 1.0;
                ctx.stroke();
            }
        },

        fillCircle(cx, cy, radius, fillColor, strokeColor, lineWidth) {
            ctx.beginPath();
            ctx.arc(cx, cy, Math.max(0.1, radius), 0, Math.PI * 2);
            if (fillColor && fillColor !== "") {
                ctx.fillStyle = fillColor;
                ctx.fill();
            }
            if (strokeColor && strokeColor !== "") {
                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = lineWidth || 1.0;
                ctx.stroke();
            }
        },

        drawLine(x1, y1, x2, y2, color, lineWidth) {
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.strokeStyle = color;
            ctx.lineWidth = lineWidth || 1.0;
            ctx.stroke();
        },

        drawText(text, x, y, color, font) {
            ctx.font = font || "13px monospace";
            ctx.fillStyle = color || "#ffffff";
            ctx.fillText(text, x, y);
        },

        measureText(text, font) {
            if (font) ctx.font = font;
            return ctx.measureText(text).width;
        },

        blitForm(formBytes, width, height, x, y) {
            if (width <= 0 || height <= 0) return;
            if (offscreenCanvas.width < width || offscreenCanvas.height < height) {
                offscreenCanvas.width = Math.max(width, offscreenCanvas.width);
                offscreenCanvas.height = Math.max(height, offscreenCanvas.height);
            }
            const raw = formBytes.toJs ? formBytes.toJs() : new Uint8Array(formBytes);
            const imgData = offscreenCtx.createImageData(width, height);
            const dst = imgData.data;
            const total = width * height * 4;
            // Unpack little-endian 32-bit uints 0xAARRGGBB into RGBA bytes
            for (let i = 0; i < total; i += 4) {
                dst[i] = raw[i + 2];     // Red
                dst[i + 1] = raw[i + 1]; // Green
                dst[i + 2] = raw[i];     // Blue
                dst[i + 3] = raw[i + 3]; // Alpha
            }
            offscreenCtx.putImageData(imgData, 0, 0);
            ctx.drawImage(offscreenCanvas, 0, 0, width, height, x, y, width, height);
        },
    };

    // 2. IndexedDB Storage Helpers
    const DB_NAME = "ObjectPondDB";
    const STORE_NAME = "images";

    function openDatabase() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, 1);
            req.onupgradeneeded = (e) => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME);
                }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    async function loadSnapshotFromIndexedDB() {
        try {
            const db = await openDatabase();
            return new Promise((resolve) => {
                const tx = db.transaction(STORE_NAME, "readonly");
                const store = tx.objectStore(STORE_NAME);
                const req = store.get("current_image_v9");
                req.onsuccess = () => resolve(req.result || null);
                req.onerror = () => resolve(null);
            });
        } catch (e) {
            return null;
        }
    }

    async function saveSnapshotToIndexedDB(bytes) {
        try {
            const db = await openDatabase();
            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readwrite");
                const store = tx.objectStore(STORE_NAME);
                const req = store.put(bytes, "current_image_v9");
                req.onsuccess = () => resolve();
                req.onerror = () => reject(req.error);
            });
        } catch (e) {
            console.warn("Could not save snapshot to IndexedDB:", e);
        }
    }

    async function loadImageFromFile(file, statusPrefix) {
        if (!file || !window.pyodide) return;
        try {
            const buf = await file.arrayBuffer();
            const bytes = new Uint8Array(buf);
            window.pyodide.FS.writeFile("/tmp/loaded.image", bytes);
            const msgJson = JSON.stringify(`${statusPrefix} ${file.name}`);
            window.pyodide.runPython(`
with open("/tmp/loaded.image", "rb") as fp:
    world = boot_image(fp.read(), ${canvas.width}, ${canvas.height})
    world.status_message = ${msgJson}
    world.changed()
`);
            window.pyodideWorld = window.pyodide.globals.get("world");
            await saveSnapshotToIndexedDB(bytes);
        } catch (exc) {
            console.error("Load image failed:", exc);
            window.pyodide.runPython(`world.status_message = ${JSON.stringify("Load failed: " + exc.message)}; world.changed()`);
        }
    }

    // 3. Host Action Callback (Save Image, Export .image, Load .image)
    window.handleHostAction = async function (action, payload) {
        if (!window.pyodide) return;
        if (action === "save_image") {
            try {
                const raw = window.pyodide.runPython("serializer.save_image_bytes(world)");
                const bytes = raw.toJs();
                await saveSnapshotToIndexedDB(bytes);
                try {
                    await fetch("/api/image/save", {
                        method: "POST",
                        headers: { "Content-Type": "application/octet-stream" },
                        body: bytes,
                    });
                    window.pyodide.runPython("world.status_message = 'Saved image to IndexedDB and server!'");
                } catch (err) {
                    window.pyodide.runPython("world.status_message = 'Saved image to IndexedDB (offline)'");
                }
                window.pyodide.runPython("world.changed()");
            } catch (exc) {
                console.error("Save image failed:", exc);
            }
        } else if (action === "export_image") {
            try {
                const raw = window.pyodide.runPython("serializer.save_image_bytes(world)");
                const blob = new Blob([raw.toJs()], { type: "application/octet-stream" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "objectpond.image";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                window.pyodide.runPython("world.status_message = 'Exported objectpond.image'");
                window.pyodide.runPython("world.changed()");
            } catch (exc) {
                console.error("Export image failed:", exc);
            }
        } else if (action === "play_sound" && payload) {
            try {
                const p = typeof payload.toJs === "function"
                    ? Object.fromEntries(payload.toJs())
                    : payload;
                const pcmB64 = p.pcm_b64 || "";
                const sampleRate = Number(p.sample_rate || 44100);
                const channels = Number(p.channels || 1);
                if (!pcmB64) return;
                if (!window._objectPondAudioCtx) {
                    const Ctx = window.AudioContext || window.webkitAudioContext;
                    window._objectPondAudioCtx = new Ctx();
                }
                const audioCtx = window._objectPondAudioCtx;
                if (audioCtx.state === "suspended") {
                    audioCtx.resume();
                }
                const binStr = atob(pcmB64);
                const bytes = new Uint8Array(binStr.length);
                for (let i = 0; i < binStr.length; i++) {
                    bytes[i] = binStr.charCodeAt(i);
                }
                const int16 = new Int16Array(bytes.buffer);
                const frameCount = Math.floor(int16.length / channels);
                if (frameCount <= 0) return;
                const audioBuf = audioCtx.createBuffer(channels, frameCount, sampleRate);
                for (let ch = 0; ch < channels; ch++) {
                    const chData = audioBuf.getChannelData(ch);
                    for (let i = 0; i < frameCount; i++) {
                        chData[i] = int16[i * channels + ch] / 32768.0;
                    }
                }
                const src = audioCtx.createBufferSource();
                src.buffer = audioBuf;
                src.connect(audioCtx.destination);
                src.start();
            } catch (exc) {
                console.error("Audio playback failed:", exc);
            }
        } else if (action === "load_image" || action === "import_object") {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".image,application/octet-stream";
            input.style.display = "none";
            input.addEventListener("change", async () => {
                const file = input.files && input.files[0];
                if (file) {
                    if (action === "load_image") {
                        await loadImageFromFile(file, "Loaded snapshot from");
                    } else {
                        try {
                            const buf = await file.arrayBuffer();
                            const bytes = new Uint8Array(buf);
                            window.pyodide.FS.writeFile("/tmp/import_source.image", bytes);
                            const fnameJson = JSON.stringify(file.name);
                            window.pyodide.runPython(`
with open("/tmp/import_source.image", "rb") as fp:
    world.open_image_object_importer(fp.read(), ${fnameJson})
    world.changed()
`);
                        } catch (exc) {
                            console.error("Import object failed:", exc);
                            window.pyodide.runPython(`world.status_message = ${JSON.stringify("Import failed: " + exc.message)}; world.changed()`);
                        }
                    }
                }
                document.body.removeChild(input);
            });
            document.body.appendChild(input);
            input.click();
        }
    };

    // 4. Main Bootstrapping Workflow
    async function bootObjectPond() {
        try {
            setStatus("Loading Pyodide WASM runtime...");
            const pyodide = await loadPyodide();
            window.pyodide = pyodide;

            setStatus("Mounting ObjectPond Kernel...");
            const bundleResp = await fetch("/api/source-bundle");
            if (!bundleResp.ok) throw new Error("Failed to fetch /api/source-bundle");
            const bundle = await bundleResp.json();

            for (const [filePath, content] of Object.entries(bundle)) {
                const parts = filePath.split("/");
                let cur = "";
                for (let i = 0; i < parts.length - 1; i++) {
                    cur += (cur ? "/" : "") + parts[i];
                    try {
                        pyodide.FS.mkdir(cur);
                    } catch (e) {
                        // Directory already exists
                    }
                }
                pyodide.FS.writeFile(filePath, content, { encoding: "utf8" });
            }

            // Setup Python bridge harness
            pyodide.runPython(`
import json
import sys
import js
from objectpond.morphic.canvas import DisplayCanvas, JSCanvasBackend
from objectpond.kernel.image import ImageSerializer
from objectpond.kernel.object_memory import ChangesLog, SystemDictionary
from objectpond.boot import create_default_environment
from objectpond.runtime_bridge import ObjectPondController

backend = JSCanvasBackend(js.ObjectPondBridge)
canvas = DisplayCanvas(backend)
controller = None

def boot_image(raw_bytes, w, h):
    global smalltalk, world, serializer, controller
    changes = ChangesLog()
    smalltalk = SystemDictionary(changes_log=changes)
    serializer = ImageSerializer(smalltalk)
    world = serializer.load_image_bytes(raw_bytes)
    world.set_extent(w, h)
    world.set_host_action_callback(lambda act, pay=None: js.handleHostAction(act, pay))
    controller = ObjectPondController(smalltalk, world)
    return world

def boot_default(w, h):
    global smalltalk, world, serializer, controller
    smalltalk, world = create_default_environment(w, h)
    serializer = ImageSerializer(smalltalk)
    world.set_host_action_callback(lambda act, pay=None: js.handleHostAction(act, pay))
    controller = ObjectPondController(smalltalk, world)
    return world

def dispatch_bridge_json(method, params_json):
    params = json.loads(params_json) if params_json else {}
    res = controller.dispatch(method, params)
    return json.dumps(res)
`);

            setStatus("Checking for saved live snapshot...");
            let imageBytes = await loadSnapshotFromIndexedDB();
            if (!imageBytes) {
                setStatus("Streaming Live .image from server...");
                try {
                    const imgResp = await fetch("/api/image/default");
                    if (imgResp.ok) {
                        const buf = await imgResp.arrayBuffer();
                        imageBytes = new Uint8Array(buf);
                    }
                } catch (e) {
                    console.warn("Could not fetch /api/image/default:", e);
                }
            }

            if (imageBytes && imageBytes.length > 50) {
                pyodide.FS.writeFile("/tmp/snapshot.image", imageBytes);
                pyodide.runPython(`
with open("/tmp/snapshot.image", "rb") as fp:
    world = boot_image(fp.read(), ${canvas.width}, ${canvas.height})
`);
            } else {
                pyodide.runPython(`world = boot_default(${canvas.width}, ${canvas.height})`);
            }

            window.pyodideWorld = pyodide.globals.get("world");
            hideLoading();

            // Connect DOM Event Listeners
            canvas.addEventListener("mousedown", (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                pyodide.runPython(`world.handle_mouse_down(${x}, ${y}, ${e.button}, ${e.altKey ? "True" : "False"}, ${e.shiftKey ? "True" : "False"})`);
            });

            canvas.addEventListener("mousemove", (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                pyodide.runPython(`world.handle_mouse_move(${x}, ${y})`);
            });

            window.addEventListener("mouseup", (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                pyodide.runPython(`world.handle_mouse_up(${x}, ${y}, ${e.button})`);
            });

            canvas.addEventListener(
                "wheel",
                (e) => {
                    e.preventDefault();
                    const rect = canvas.getBoundingClientRect();
                    const x = e.clientX - rect.left;
                    const y = e.clientY - rect.top;
                    pyodide.runPython(`world.handle_mouse_wheel(${x}, ${y}, ${e.deltaY})`);
                },
                { passive: false }
            );

            window.addEventListener("keydown", (e) => {
                const cmd = e.ctrlKey || e.metaKey;
                const key = e.key.toLowerCase();
                if (cmd && key === "v") {
                    // Allow browser 'paste' event to fire synchronously with clipboardData
                    return;
                }
                if (
                    cmd ||
                    e.key === "Tab" ||
                    e.key === "Backspace" ||
                    e.key === "Delete" ||
                    e.key === "PageUp" ||
                    e.key === "PageDown" ||
                    e.key === "Home" ||
                    e.key === "End" ||
                    e.key.startsWith("Arrow")
                ) {
                    if (cmd && ["d", "p", "i", "s", "a", "c", "x", "z"].includes(key)) {
                        e.preventDefault();
                    } else if (
                        e.key === "Tab" ||
                        e.key === "PageUp" ||
                        e.key === "PageDown" ||
                        e.key === "Home" ||
                        e.key === "End" ||
                        e.key.startsWith("Arrow")
                    ) {
                        e.preventDefault();
                    }
                }
                const isCopyOrCut = cmd && (key === "c" || key === "x");
                const prevClipSeq = isCopyOrCut
                    ? pyodide.runPython("getattr(world, '_clipboard_seq', 0)")
                    : 0;
                const pyKey = JSON.stringify(e.key);
                pyodide.runPython(
                    `world.handle_key_down(${pyKey}, ctrl_key=${e.ctrlKey ? "True" : "False"}, meta_key=${e.metaKey ? "True" : "False"}, shift_key=${e.shiftKey ? "True" : "False"}, alt_key=${e.altKey ? "True" : "False"})`
                );
                if (isCopyOrCut) {
                    const nextClipSeq = pyodide.runPython("getattr(world, '_clipboard_seq', 0)");
                    if (nextClipSeq !== prevClipSeq && navigator.clipboard && navigator.clipboard.writeText) {
                        const clipText = pyodide.runPython("world.get_clipboard_text()");
                        navigator.clipboard.writeText(clipText).catch(() => {});
                    }
                }
            });

            window.addEventListener("paste", (e) => {
                const text = e.clipboardData ? e.clipboardData.getData("text/plain") : "";
                if (text !== undefined && text !== null) {
                    e.preventDefault();
                    const pyText = JSON.stringify(text);
                    pyodide.runPython(`world.handle_paste(${pyText})`);
                }
            });

            window.addEventListener("contextmenu", (e) => {
                e.preventDefault();
            });

            // Drag and drop .image files onto window
            window.addEventListener("dragover", (e) => {
                e.preventDefault();
                if (dragOverlay) dragOverlay.style.display = "flex";
            });

            window.addEventListener("dragleave", (e) => {
                if (e.relatedTarget === null && dragOverlay) {
                    dragOverlay.style.display = "none";
                }
            });

            window.addEventListener("drop", async (e) => {
                e.preventDefault();
                if (dragOverlay) dragOverlay.style.display = "none";
                const file = e.dataTransfer.files[0];
                if (file) {
                    await loadImageFromFile(file, "Restored snapshot from");
                }
            });

            // Main Animation & Stepping Loop
            function mainCycle() {
                try {
                    pyodide.runPython("world.do_one_cycle(canvas)");
                } catch (err) {
                    console.error("Error during world.do_one_cycle:", err);
                }
                requestAnimationFrame(mainCycle);
            }
            requestAnimationFrame(mainCycle);

            // Live MCP Bridge Loop (long-polls server.py for external AI commands)
            const bridgeFn = pyodide.globals.get("dispatch_bridge_json");
            async function bridgeLoop() {
                while (true) {
                    try {
                        const resp = await fetch("/api/bridge/poll");
                        if (resp.status === 204) continue;
                        if (!resp.ok) {
                            await new Promise((r) => setTimeout(r, 1500));
                            continue;
                        }
                        const cmd = await resp.json();
                        let payload = { id: cmd.id };
                        try {
                            if (cmd.method === "screenshot") {
                                pyodide.runPython("world.full_draw_on(canvas) if world.is_damaged else None");
                                const dataUrl = canvas.toDataURL("image/png");
                                const b64 = dataUrl.split(",")[1] || "";
                                payload.result = {
                                    mime_type: "image/png",
                                    width: canvas.width,
                                    height: canvas.height,
                                    data_base64: b64,
                                };
                            } else {
                                const rawJson = bridgeFn(cmd.method, JSON.stringify(cmd.params || {}));
                                payload.result = JSON.parse(rawJson);
                                pyodide.runPython("world.do_one_cycle(canvas)");
                            }
                        } catch (execErr) {
                            payload.error = execErr.message || String(execErr);
                        }
                        await fetch("/api/bridge/result", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(payload),
                        });
                    } catch (netErr) {
                        await new Promise((r) => setTimeout(r, 2000));
                    }
                }
            }
            bridgeLoop();
        } catch (exc) {
            console.error("Boot error:", exc);
            setStatus("Boot Failed: " + exc.message);
        }
    }

    window.addEventListener("DOMContentLoaded", bootObjectPond);
})();
