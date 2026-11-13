# ObjectPond

**ObjectPond** is a zero-dependency, live, image-based Python Morphic development environment. It runs interactively in the browser via Pyodide WebAssembly (`index.html` + `vm.js`) backed by a local Python HTTP + MCP server (`server.py`), with a headless Python + software/PNG canvas fallback (`objectpond/morphic/software_canvas.py`).

## Architecture
- `server.py`: Static asset server, `.image` / `.changes` / source-bundle APIs, `BridgeHub` (long-poll bridge to live browser Pyodide VM with headless fallback), and Streamable HTTP `/mcp` endpoint.
- `vm.js` & `index.html`: Browser Pyodide WASM host, HTML5 Canvas + BitBlt bridge (`ObjectPondBridge`), IndexedDB persistence (`ObjectPondDB`), and `bridgeLoop()` for live MCP control & canvas PNG screenshots.
- `objectpond/kernel/`: `SystemDictionary`, `ChangesLog`, `ClassRecord`, exception capture (`object_memory.py`), and `ImageSerializer` (`image.py`).
- `objectpond/morphic/`: `Morph`, `WorldMorph`, `HandMorph`, `HaloMorph`, `DisplayCanvas`, `Form`, widgets, and `SoftwareCanvasBackend` / `PILCanvasBackend`.
- `objectpond/tools/`: `SystemBrowserWindow`, `WorkspaceWindow`, `InspectorWindow`, `TranscriptWindow`, `ChangesViewerWindow`, `DebuggerWindow`, and demos.
- `objectpond/runtime_bridge.py`: `ObjectPondController` unified command facade used by both browser Pyodide and headless Python.
- `objectpond/mcp_server.py`: Zero-dependency MCP JSON-RPC 2.0 server (`objectpond_*` tools, `objectpond://*` resources) + stdio transport.

## Commands
- **Run server (and browser UI at `http://localhost:8765`)**:
  ```bash
  python3 server.py 8765
  ```
- **Run unit & integration tests**:
  ```bash
  python3 -m unittest discover -s tests -v
  ```
- **Run MCP stdio server**:
  ```bash
  python3 -m objectpond.mcp_server --bridge-url http://localhost:8765
  ```

## Conventions
- Keep core `objectpond` **zero-dependency** (Python standard library only; optional `PIL` enhancement when installed).
- All user-written classes, methods, and evaluations use standard Python (not Smalltalk-80 syntax).

