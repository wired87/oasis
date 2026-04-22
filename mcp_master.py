from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

try:
    import duckdb
except Exception:  # pragma: no cover - optional dependency
    duckdb = None

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover - optional dependency
    FastMCP = None


class _FallbackMCPServer:
    def __init__(self) -> None:
        self.routes: dict[str, Callable[..., Any]] = {}


class MCPMaster:
    def __init__(
        self,
        project_root: str | Path | None = None,
        server: Any | None = None,
        access_backend: Callable[[str, float], bool] | None = None,
    ) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parent)
        self.server = server or (FastMCP("oasis-mcp-master") if FastMCP else _FallbackMCPServer())
        self._access_backend = access_backend or self._duckdb_xternal_access
        self._service_payload: dict[str, dict[str, Any]] = {}
        self.routes: dict[str, Callable[..., Any]] = {}

    def ingest_service_data(self, service_payload: dict[str, dict[str, Any]]) -> None:
        if not isinstance(service_payload, dict):
            return
        self._service_payload.update(service_payload)

    def _load_payload_from_env(self) -> dict[str, dict[str, Any]]:
        combined: dict[str, dict[str, Any]] = {}
        for key, raw in os.environ.items():
            if not key.startswith("MCP_ROUTE"):
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue

            if "service_id" in payload:
                service_id = str(payload.get("service_id"))
                combined[service_id] = payload
                continue

            for service_id, route_payload in payload.items():
                if isinstance(route_payload, dict):
                    combined[str(service_id)] = route_payload
        return combined

    @staticmethod
    def _sanitize_service_id(service_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", service_id).strip("_") or "service"

    @staticmethod
    def _extract_event_data(payload: dict[str, Any]) -> list[dict[str, Any]]:
        events = payload.get("event_data")
        if isinstance(events, list):
            return [event for event in events if isinstance(event, dict)]
        event_nodes = payload.get("event_nodes")
        if isinstance(event_nodes, list):
            return [event for event in event_nodes if isinstance(event, dict)]
        return []

    @staticmethod
    def _embedding_docstring(embedding: Any) -> str:
        if isinstance(embedding, str):
            return embedding
        return json.dumps(embedding, ensure_ascii=False)

    @staticmethod
    def _score_sum(event_data: list[dict[str, Any]]) -> float:
        total = 0.0
        for node in event_data:
            value = node.get("score", node.get("rank", 0))
            if isinstance(value, (int, float)):
                total += float(value)
        return total

    def _duckdb_xternal_access(self, uid: str, total_score: float) -> bool:
        if not uid:
            return False
        if duckdb is None:
            return True

        db_path = Path(os.getenv("XTERNAL_ACCESS_DUCKDB") or self.project_root / "xternal_access.duckdb")
        with duckdb.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS xternal_access_log (
                    uid TEXT,
                    total_score DOUBLE,
                    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO xternal_access_log (uid, total_score) VALUES (?, ?)",
                [uid, total_score],
            )
        return True

    def _register_with_server(self, route_name: str, handler: Callable[..., Any], description: str) -> None:
        self.routes[route_name] = handler
        if hasattr(self.server, "routes") and isinstance(self.server.routes, dict):
            self.server.routes[route_name] = handler

        tool_fn = getattr(self.server, "tool", None)
        if callable(tool_fn):
            try:
                tool_fn(name=route_name, description=description)(handler)
            except TypeError:
                try:
                    tool_fn(route_name)(handler)
                except Exception:
                    pass
            except Exception:
                pass

    def create_new_routes(self, service_payload: dict[str, dict[str, Any]] | None = None) -> dict[str, Callable[..., Any]]:
        if service_payload:
            self.ingest_service_data(service_payload)

        payload = dict(self._service_payload)
        payload.update(self._load_payload_from_env())
        date_suffix = datetime.now(UTC).strftime("%Y%m%d")

        for service_id, service_data in payload.items():
            if not isinstance(service_data, dict):
                continue
            route_name = f"{self._sanitize_service_id(service_id)}_{date_suffix}"
            event_data = self._extract_event_data(service_data)
            description = self._embedding_docstring(service_data.get("service_embeddings", ""))

            def route(uid: str, _event_data: list[dict[str, Any]] = event_data) -> list[dict[str, Any]]:
                total_score = self._score_sum(_event_data)
                allowed = self._access_backend(uid, total_score)
                return _event_data if allowed else []

            route.__name__ = route_name
            route.__doc__ = description
            self._register_with_server(route_name, route, description)

        return self.routes

    def run(self, service_payload: dict[str, dict[str, Any]]) -> dict[str, Callable[..., Any]]:
        return self.create_new_routes(service_payload)

    def scan_env_forever(self, interval_seconds: float = 30.0, iterations: int | None = None) -> None:
        scanned = 0
        while iterations is None or scanned < iterations:
            self.create_new_routes()
            scanned += 1
            if iterations is not None and scanned >= iterations:
                break
            time.sleep(interval_seconds)


_MASTER = MCPMaster()


def ingest_service_data(service_payload: dict[str, dict[str, Any]]) -> dict[str, Callable[..., Any]]:
    return _MASTER.run(service_payload)


def create_new_routes(service_payload: dict[str, dict[str, Any]] | None = None) -> dict[str, Callable[..., Any]]:
    return _MASTER.create_new_routes(service_payload)


def run(service_payload: dict[str, dict[str, Any]]) -> dict[str, Callable[..., Any]]:
    return _MASTER.run(service_payload)
