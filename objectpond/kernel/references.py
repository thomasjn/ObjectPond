import io
import mimetypes
from pathlib import Path
from typing import Optional
import urllib.parse
import urllib.request


def _is_pyodide() -> bool:
    import sys
    return sys.platform == "emscripten"


def _browser_fetch_sync(url: str) -> bytes:
    """Synchronous binary fetch inside Pyodide browser via XMLHttpRequest."""
    import js  # type: ignore

    xhr = js.XMLHttpRequest.new()
    xhr.open("GET", url, False)
    xhr.overrideMimeType("text/plain; charset=x-user-defined")
    xhr.send(None)
    if xhr.status < 200 or xhr.status >= 300:
        raise IOError(f"HTTP {xhr.status} fetching {url}")
    txt = xhr.responseText or ""
    return bytes(ord(ch) & 0xFF for ch in txt)


class ExternalReference:
    """
    Portable descriptor for an external resource (file or URL).
    Persists only lightweight metadata in .image snapshots; fetched bytes and
    live stream handles are marked transient and loaded lazily on demand.
    """

    _transient_attrs = ("_cached_bytes", "_last_error")

    def __init__(self, label: str = "", mime_type: str = "application/octet-stream"):
        self.label = label
        self.mime_type = mime_type
        self._cached_bytes: Optional[bytes] = None
        self._last_error: Optional[str] = None

    def _fetch_bytes(self) -> bytes:
        raise NotImplementedError

    def read_bytes(self, force_refresh: bool = False) -> bytes:
        cached = getattr(self, "_cached_bytes", None)
        if cached is not None and not force_refresh:
            return cached
        try:
            data = self._fetch_bytes()
            self._cached_bytes = data
            self._last_error = None
            return data
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def open_stream(self, force_refresh: bool = False) -> io.BytesIO:
        return io.BytesIO(self.read_bytes(force_refresh=force_refresh))

    def read_text(self, encoding: str = "utf-8", force_refresh: bool = False) -> str:
        return self.read_bytes(force_refresh=force_refresh).decode(encoding, errors="replace")

    def invalidate(self) -> None:
        self._cached_bytes = None
        self._last_error = None

    def display_name(self) -> str:
        return self.label or "resource"

    def extension_badge(self) -> str:
        return "DAT"


class FileReference(ExternalReference):
    """
    Anchored file reference (e.g. anchor='assets', path='bwv565.mid').
    Resolves against host anchors in headless Python or via /api/fs/read in Pyodide.
    """

    ANCHORS = {
        "assets": Path(__file__).resolve().parents[2] / "assets",
        "image_dir": Path(__file__).resolve().parents[2],
        "workspace": Path(__file__).resolve().parents[2],
    }

    def __init__(
        self,
        anchor: str = "assets",
        path: str = "",
        label: Optional[str] = None,
        mime_type: Optional[str] = None,
    ):
        clean_path = str(path).lstrip("/")
        name = label or (Path(clean_path).name if clean_path else "file")
        guessed_mime = mime_type or mimetypes.guess_type(clean_path)[0] or "application/octet-stream"
        super().__init__(label=name, mime_type=guessed_mime)
        self.anchor = anchor
        self.path = clean_path

    def resolve_local_path(self) -> Path:
        root = self.ANCHORS.get(self.anchor)
        if root is None:
            raise ValueError(f"Unknown file anchor: {self.anchor!r}")
        resolved_root = root.resolve()
        candidate = (resolved_root / self.path).resolve()
        if not candidate.is_relative_to(resolved_root):
            raise PermissionError(f"Path escapes anchor {self.anchor!r}: {self.path!r}")
        return candidate

    def _fetch_bytes(self) -> bytes:
        if _is_pyodide():
            qs = urllib.parse.urlencode({"anchor": self.anchor, "path": self.path})
            return _browser_fetch_sync(f"/api/fs/read?{qs}")
        local_path = self.resolve_local_path()
        return local_path.read_bytes()

    def display_name(self) -> str:
        return self.label or Path(self.path).name or "file"

    def extension_badge(self) -> str:
        ext = Path(self.path).suffix.lstrip(".").upper()
        return (ext[:4] or "FILE")

    def __repr__(self) -> str:
        return f"FileReference(anchor={self.anchor!r}, path={self.path!r})"


class UrlReference(ExternalReference):
    """
    External HTTP/HTTPS URL reference.
    Fetches via urllib in Python or via /api/url/fetch proxy in Pyodide.
    """

    def __init__(
        self,
        url: str,
        label: Optional[str] = None,
        mime_type: Optional[str] = None,
    ):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
        name = label or (Path(parsed.path).name if parsed.path and parsed.path != "/" else parsed.netloc)
        guessed_mime = mime_type or mimetypes.guess_type(parsed.path)[0] or "application/octet-stream"
        super().__init__(label=name, mime_type=guessed_mime)
        self.url = url

    def _fetch_bytes(self) -> bytes:
        if _is_pyodide():
            qs = urllib.parse.urlencode({"url": self.url})
            return _browser_fetch_sync(f"/api/url/fetch?{qs}")
        req = urllib.request.Request(self.url, headers={"User-Agent": "ObjectPond/1.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(16 * 1024 * 1024)

    def display_name(self) -> str:
        return self.label or self.url

    def extension_badge(self) -> str:
        ext = Path(urllib.parse.urlparse(self.url).path).suffix.lstrip(".").upper()
        return (ext[:4] or "URL")

    def __repr__(self) -> str:
        return f"UrlReference(url={self.url!r})"
