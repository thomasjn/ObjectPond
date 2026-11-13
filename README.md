# ObjectPond

**ObjectPond** is a zero-dependency, live, image-based Python Morphic development environment. It runs interactively in the browser via Pyodide WebAssembly (`index.html` + `vm.js`) backed by a local Python HTTP + MCP server (`server.py`), with a pure-Python headless fallback (`SoftwareCanvasBackend`).

## Features
- **Live Object Memory & Hot-Patching**: Define classes, compile and hot-patch methods on live instances, migrate objects in memory, and track every edit in a `.changes` audit log (`SystemDictionary`, `ChangesLog`).
- **Image-Based Persistence**: Snapshot and restore the entire live object graph, submorph hierarchy, pixel `Form`s, and bound callbacks as `.image` files (`ImageSerializer`), persisted to disk (`objectpond.image`) and browser IndexedDB (`ObjectPondDB`).
- **Morphic Desktop & Direct Manipulation**: Interactive `WorldMorph`, `HandMorph`, and Alt+Click `HaloMorph` handles (move, resize, duplicate, delete, recolor, inspect, browse), plus a 32-bit `Form` BitBlt engine.
- **Built-in Live Tools**: System Browser, Workspace (`Do it` / `Print it` / `Inspect it`), Object Inspector (with live field mutation), Transcript, Changes Viewer, Post-Mortem & Live-Patching Debugger, and interactive demos (`BouncingAtomsMorph`, `BitBltPaintMorph`).
- **Zero-Dependency MCP Server**: Built-in Model Context Protocol (`objectpond_*` tools and `objectpond://*` resources) over both Streamable HTTP (`/mcp`) and stdio (`python3 -m objectpond.mcp_server`), bridging to the live browser session when connected or falling back to headless PNG rendering.

## Quick Start

Start the server and open the live environment at `http://localhost:8765`:

```bash
python3 server.py 8765
```

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Connect an MCP client over stdio (attaches to a running `server.py` or runs headlessly):

```bash
python3 -m objectpond.mcp_server --bridge-url http://localhost:8765
```

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
