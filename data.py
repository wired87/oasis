"""
Workflow: Google history -> graph -> ranking -> service insights -> downstream workflows.

Dev TODOs:
- Set GOOGLE_PORTABILITY_TOKEN with a valid Google Data Portability API bearer token.
- Optionally provide MODEL for Ollama (for example: llama3.1).
- Ensure local Ollama server is running on http://localhost:11434 for LLM summaries.
- Optionally provide `mcp_master.py` and `blockchain.py` workflow modules in project root.
- Optionally install/clone wired87/brain so GUtils can be imported from brain.firegraph.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from pprint import pprint
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PORTABILITY_URL = "https://dataportability.googleapis.com/v1/portabilityArchive:initiate"


@dataclass
class LocalGUtils:
    """Minimal fallback graph utility with a GUtils-like interface."""

    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, str]] = field(default_factory=list)
    _neighbors: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_node(self, node_id: str, data: dict[str, Any]) -> None:
        self.nodes[node_id] = data

    def add_edge(self, source: str, target: str, relation: str) -> None:
        self.edges.append({"source": source, "target": target, "relation": relation})
        self._neighbors[source].add(target)
        self._neighbors[target].add(source)

    def neighbors(self, node_id: str) -> list[str]:
        if node_id not in self._neighbors:
            return []
        return sorted(self._neighbors[node_id])

    def nodes_by_type(self, node_type: str) -> list[str]:
        return sorted(
            node_id
            for node_id, payload in self.nodes.items()
            if payload.get("node_type") == node_type
        )

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges}

    def save_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def save_visualization(self, path: Path) -> None:
        path.write_text(json.dumps(self.edges, indent=2), encoding="utf-8")


def _load_gutils() -> type:
    try:
        from brain.firegraph import GUtils  # type: ignore

        return GUtils
    except (ImportError, AttributeError, TypeError):
        try:
            from firegraph import GUtils  # type: ignore

            return GUtils
        except (ImportError, AttributeError, TypeError):
            return LocalGUtils


class DataWorkflow:
    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or Path(__file__).resolve().parent)
        self.history_dir = self.project_root / "history"
        self.gutils = _load_gutils()()

    def fetch_last_24h_history(self) -> list[dict[str, Any]]:
        """
        Pull events from Data Portability API if credentials exist.
        Falls back to sample events for local/offline development.
        """
        token = os.getenv("GOOGLE_PORTABILITY_TOKEN")
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        until = datetime.now(UTC).isoformat()
        if not token:
            return self._sample_events(since, until)

        payload = {
            "resources": ["myactivity.search", "myactivity.youtube", "myactivity.maps"],
            "startTime": since,
            "endTime": until,
        }
        req = Request(
            PORTABILITY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            events = body.get("events")
            return events if isinstance(events, list) else self._sample_events(since, until)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return self._sample_events(since, until)

    @staticmethod
    def _sample_events(since: str, until: str) -> list[dict[str, Any]]:
        return [
            {
                "event_id": "evt_yt_1",
                "service": "YouTube",
                "timestamp": since,
                "action": "Watched tutorial",
                "metadata": {"duration_sec": 420, "topic": "graph ranking"},
            },
            {
                "event_id": "evt_maps_1",
                "service": "Maps",
                "timestamp": until,
                "action": "Searched location",
                "metadata": {"query": "coffee near me"},
            },
        ]

    @staticmethod
    def embed_payload(payload: dict[str, Any], dims: int = 16) -> list[float]:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(raw).digest()
        return [round((digest[i] / 255.0) * 2 - 1, 6) for i in range(dims)]

    def build_graph(self, events: list[dict[str, Any]]) -> Any:
        for event in events:
            event_id = str(event.get("event_id") or f"event_{len(self.gutils.nodes)}")
            service_name = str(event.get("service") or "unknown_service")
            service_id = f"service:{service_name.lower().replace(' ', '_')}"
            time_key = str(event.get("timestamp") or datetime.now(UTC).isoformat())
            time_id = f"time:{time_key}"

            if service_id not in self.gutils.nodes:
                self.gutils.add_node(service_id, {"node_type": "SERVICE", "name": service_name})
            if time_id not in self.gutils.nodes:
                self.gutils.add_node(time_id, {"node_type": "TIME", "time": time_key})

            event_data = dict(event)
            event_data["node_type"] = "EVENT"
            event_data["embedding"] = self.embed_payload(event_data)
            self.gutils.add_node(event_id, event_data)

            self.gutils.add_edge(time_id, event_id, "happened_at")
            self.gutils.add_edge(event_id, service_id, "used_service")
        return self.gutils

    def rank_event_nodes(self) -> dict[str, float]:
        event_ids = self.gutils.nodes_by_type("EVENT")
        event_ranks: dict[str, float] = {}
        for event_id in event_ids:
            event = self.gutils.nodes[event_id]
            metadata = event.get("metadata", {})
            metadata_count = len(metadata) if isinstance(metadata, dict) else 0
            embedding = event.get("embedding", [])
            embedding_norm = (
                math.sqrt(sum(v * v for v in embedding if isinstance(v, (int, float))))
                if embedding
                else 0.0
            )
            node_type_count = len({self.gutils.nodes[n].get("node_type") for n in self.gutils.neighbors(event_id)})
            serialized_size = len(json.dumps(event, sort_keys=True))
            relation_bonus = self._time_relation_bonus(event_id)
            score = (
                (metadata_count * 1.5)
                + (embedding_norm * 0.75)
                + (node_type_count * 2.0)
                + (math.log1p(serialized_size) * 0.5)
                + relation_bonus
            )
            event["rank"] = round(score, 6)
            event_ranks[event_id] = event["rank"]
        return event_ranks

    def _time_relation_bonus(self, event_id: str) -> float:
        bonus = 0.0
        time_nodes = [
            n for n in self.gutils.neighbors(event_id) if self.gutils.nodes.get(n, {}).get("node_type") == "TIME"
        ]
        for time_node in time_nodes:
            for neighbor in self.gutils.neighbors(time_node):
                if neighbor != event_id and self.gutils.nodes.get(neighbor, {}).get("node_type") == "EVENT":
                    bonus += 1.25
        return bonus

    def summarize_services(self) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        for service_id in self.gutils.nodes_by_type("SERVICE"):
            event_nodes = [
                self.gutils.nodes[n]
                for n in self.gutils.neighbors(service_id)
                if self.gutils.nodes.get(n, {}).get("node_type") == "EVENT"
            ]
            summary = self._generate_service_summary(service_id, event_nodes)
            summary_embedding = self.embed_payload({"service_id": service_id, "summary": summary})
            payload[service_id] = {
                "service_embeddings": summary_embedding,
                "event_nodes": event_nodes,
                "summary": summary,
            }
        return payload

    def _generate_service_summary(self, service_id: str, event_nodes: list[dict[str, Any]]) -> str:
        model = os.getenv("MODEL")
        prompt = (
            "Write a short precise service activity overview based on event nodes:\n"
            f"service={service_id}\n"
            f"events={json.dumps(event_nodes, ensure_ascii=False)}"
        )
        if not model:
            return f"{service_id}: {len(event_nodes)} events in last 24h."

        req = Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return str(body.get("response") or f"{service_id}: {len(event_nodes)} events in last 24h.")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return f"{service_id}: {len(event_nodes)} events in last 24h."

    def _load_optional_module(self, file_name: str) -> Any | None:
        module_path = self.project_root / file_name
        if not module_path.exists():
            return None
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def dispatch_service_payload(self, service_payload: dict[str, dict[str, Any]]) -> None:
        for module_name, fn_candidates in (
            ("mcp_master.py", ("ingest_service_data", "create_new_routes", "run")),
            ("blockchain.py", ("ingest_service_data", "create_smart_contract", "run")),
        ):
            module = self._load_optional_module(module_name)
            if not module:
                continue
            for fn_name in fn_candidates:
                fn = getattr(module, fn_name, None)
                if callable(fn):
                    fn(service_payload)
                    break

    def save_outputs(self, graph_obj: Any) -> tuple[Path, Path]:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        graph_json = self.history_dir / f"graph_{stamp}.json"
        viz_file = self.project_root / f"graph_{stamp}.viz.json"
        if hasattr(graph_obj, "save_json"):
            graph_obj.save_json(graph_json)
        else:
            graph_json.write_text(json.dumps(getattr(graph_obj, "to_dict", lambda: {})(), indent=2), encoding="utf-8")
        if hasattr(graph_obj, "save_visualization"):
            graph_obj.save_visualization(viz_file)
        return graph_json, viz_file

    def pathway(self) -> Any:
        events = self.fetch_last_24h_history()
        graph_obj = self.build_graph(events)
        self.rank_event_nodes()
        service_payload = self.summarize_services()
        self.dispatch_service_payload(service_payload)
        return graph_obj

    def run(self) -> tuple[Any, Path, Path]:
        graph_obj = self.pathway()
        graph_json, viz_file = self.save_outputs(graph_obj)
        return graph_obj, graph_json, viz_file


if __name__ == "__main__":
    workflow = DataWorkflow()
    graph, json_path, viz_path = workflow.run()
    pprint(graph.to_dict() if hasattr(graph, "to_dict") else graph)
    print(f"Graph JSON: {json_path}")
    print(f"Graph visualization: {viz_path}")
