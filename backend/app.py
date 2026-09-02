"""Read-only control-plane API for the Legged Studio asset inventory.

FastAPI is used when installed.  The same handlers are exposed through the
stdlib ``http.server`` implementation so the inventory can still be browsed
in a clean Python environment.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


BACKEND_DIR = Path(__file__).resolve().parent
WEB_DIR = BACKEND_DIR.parent / "web"
PROJECT_ROOT = BACKEND_DIR.parent.parent
INVENTORY_PATH = Path(
    os.environ.get("LEGGED_STUDIO_INVENTORY", PROJECT_ROOT / "QUADRUPED_ASSET_INVENTORY.json")
).expanduser().resolve()
PYTHON_TARGET = "3.12"


class InventoryError(RuntimeError):
    """Raised when the read-only inventory cannot be loaded."""


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise InventoryError(f"Inventory not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InventoryError(f"Inventory is not valid JSON: {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise InventoryError("Inventory must be an object containing a records array")
    return value


def _records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for record in inventory["records"] if isinstance(record, dict)]


def filter_records(
    records: list[dict[str, Any]],
    *,
    readiness: str | None = None,
    size: str | None = None,
    locomotion: str | None = None,
    family: str | None = None,
) -> list[dict[str, Any]]:
    """Apply exact, case-insensitive filters used by both HTTP adapters."""
    def matches(record: dict[str, Any], key: str, expected: str | None) -> bool:
        return expected is None or str(record.get(key, "")).lower() == expected.lower()

    return [
        record
        for record in records
        if matches(record, "readiness", readiness)
        and matches(record, "size_class_by_mass", size)
        and matches(record, "locomotion", locomotion)
        and matches(record, "family", family)
    ]


def api_response(path: str, query: dict[str, list[str]]) -> tuple[int, dict[str, Any]]:
    """Return ``(status, payload)`` for a request without depending on FastAPI."""
    try:
        inventory = load_inventory()
    except InventoryError as exc:
        return 503, {"error": {"code": "inventory_unavailable", "message": str(exc)}}

    if path == "/api/health":
        runtime_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        return 200, {
            "status": "ok",
            "inventory": str(INVENTORY_PATH),
            "schema_version": inventory.get("schema_version"),
            "python_version": runtime_version,
            "python_target": PYTHON_TARGET,
            "python_target_match": sys.version_info[:2] == (3, 12),
        }
    if path == "/api/summary":
        summary = dict(inventory.get("summary", {}))
        summary.update(
            {
                "schema_version": inventory.get("schema_version"),
                "document_role": inventory.get("document_role"),
                "size_taxonomy": inventory.get("size_taxonomy", {}),
            }
        )
        return 200, summary
    if path == "/api/assets" or path.startswith("/api/assets/"):
        family_path = path[len("/api/assets/") :] if path.startswith("/api/assets/") else None
        requested_family = family_path or (query.get("family", [None])[0])
        all_records = _records(inventory)
        if family_path and not any(str(record.get("family", "")).lower() == family_path.lower() for record in all_records):
            return 404, {"error": {"code": "family_not_found", "message": f"Unknown asset family: {family_path}"}}
        records = filter_records(
            all_records,
            readiness=query.get("readiness", [None])[0],
            size=query.get("size", query.get("size_class", [None]))[0],
            locomotion=query.get("locomotion", [None])[0],
            family=requested_family,
        )
        try:
            offset = max(0, int(query.get("offset", ["0"])[0]))
            limit = min(500, max(1, int(query.get("limit", ["500"])[0])))
        except ValueError:
            return 400, {"error": {"code": "invalid_pagination", "message": "offset and limit must be integers"}}
        payload: dict[str, Any] = {
            "count": len(records),
            "offset": offset,
            "limit": limit,
            "records": records[offset : offset + limit],
        }
        if family_path:
            payload["family"] = family_path
        return 200, payload
    return 404, {"error": {"code": "not_found", "message": f"Unknown endpoint: {path}"}}


try:  # Optional dependency; stdlib fallback remains the supported baseline.
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Legged Studio Control Plane", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        status, payload = api_response("/api/health", {})
        return JSONResponse(payload, status_code=status)

    @app.get("/api/summary")
    def summary() -> dict[str, Any]:
        status, payload = api_response("/api/summary", {})
        return JSONResponse(payload, status_code=status)

    @app.get("/api/assets")
    def assets(
        readiness: str | None = Query(default=None),
        size: str | None = Query(default=None),
        locomotion: str | None = Query(default=None),
        family: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=500, ge=1, le=500),
    ) -> dict[str, Any]:
        query = {key: [str(value)] for key, value in {"readiness": readiness, "size": size, "locomotion": locomotion, "family": family, "offset": offset, "limit": limit}.items() if value is not None}
        status, payload = api_response("/api/assets", query)
        return JSONResponse(payload, status_code=status)

    @app.get("/api/assets/{family_name}")
    def asset_family(
        family_name: str,
        readiness: str | None = Query(default=None),
        size: str | None = Query(default=None),
        locomotion: str | None = Query(default=None),
    ) -> dict[str, Any]:
        query = {key: [str(value)] for key, value in {"readiness": readiness, "size": size, "locomotion": locomotion}.items() if value is not None}
        status, payload = api_response(f"/api/assets/{family_name}", query)
        return JSONResponse(payload, status_code=status)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "workbench.html")

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
except ImportError:  # pragma: no cover - exercised in environments without FastAPI
    app = None


class RequestHandler(BaseHTTPRequestHandler):
    """Minimal GET-only JSON adapter used when FastAPI is unavailable."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            relative = "workbench.html" if parsed.path in {"", "/"} else parsed.path.lstrip("/")
            target = (WEB_DIR / relative).resolve()
            web_root = WEB_DIR.resolve()
            if target == web_root or web_root not in target.parents or not target.is_file():
                self.send_error(404, "Static asset not found")
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        status, payload = api_response(parsed.path, parse_qs(parsed.query))
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the stdlib server (or use ``uvicorn backend.app:app`` for FastAPI)."""
    with ThreadingHTTPServer((host, port), RequestHandler) as server:
        print(f"Legged Studio backend listening on http://{host}:{port}")
        server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
