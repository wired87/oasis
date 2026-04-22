"""Diary graph to movie-script and upload workflow."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from pprint import pprint
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from data import LocalGUtils


STATIC_PROMPT = "Generate movie script from given diary graph"


def _load_graph_factory() -> Any:
    """Load GUtils (or fallback) constructor."""
    try:
        from firegraph import GUtils  # type: ignore

        if hasattr(GUtils, "G") and callable(GUtils.G):
            return GUtils.G
        if callable(GUtils):
            return GUtils
    except Exception:
        pass
    return LocalGUtils


def _escape_for_ffmpeg_filter(path: Path) -> str:
    """Escape file path for ffmpeg drawtext filter."""
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


class DiaryYouTubeWorkflow:
    """Run the diary -> script -> video -> upload flow."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        """Set workflow paths."""
        self.project_root = Path(project_root or Path(__file__).resolve().parent)
        self.data_dir = self.project_root / "data"
        self.graph = None

    def _print_start(self, method_name: str) -> None:
        """Print start marker."""
        print(f"[START] {method_name}")

    def _print_end(self, method_name: str) -> None:
        """Print end marker."""
        print(f"[END] {method_name}")

    def load_youngest_diary_graph(self) -> tuple[Any, Path]:
        """Load youngest diary graph file from data dir."""
        method_name = "load_youngest_diary_graph"
        self._print_start(method_name)
        try:
            files = [path for path in self.data_dir.iterdir() if path.is_file()]
            if not files:
                raise FileNotFoundError(f"No files found in {self.data_dir}")
            youngest = max(files, key=lambda p: p.stat().st_mtime)
            payload = json.loads(youngest.read_text(encoding="utf-8"))
            graph = _load_graph_factory()()
            self._load_payload_into_graph(graph, payload)
            self.graph = graph
            return graph, youngest
        finally:
            self._print_end(method_name)

    def _load_payload_into_graph(self, graph: Any, payload: Any) -> None:
        """Hydrate graph object from JSON payload."""
        if not isinstance(payload, dict):
            if hasattr(graph, "add_node"):
                graph.add_node("diary:raw", {"node_type": "RAW", "content": payload})
            return

        nodes = payload.get("nodes")
        edges = payload.get("edges")

        if isinstance(nodes, dict) and hasattr(graph, "add_node"):
            for node_id, node_data in nodes.items():
                safe_node = node_data if isinstance(node_data, dict) else {"value": node_data}
                graph.add_node(str(node_id), safe_node)

        if isinstance(edges, list) and hasattr(graph, "add_edge"):
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                source = edge.get("source")
                target = edge.get("target")
                if source is None or target is None:
                    continue
                graph.add_edge(str(source), str(target), str(edge.get("relation", "related_to")))

        if hasattr(graph, "nodes") and not getattr(graph, "nodes", {}):
            graph.add_node("diary:payload", {"node_type": "PAYLOAD", "content": payload})

    def generate_script_with_ollama(self, graph: Any) -> tuple[str, str]:
        """Build prompt and ask local Ollama."""
        method_name = "generate_script_with_ollama"
        self._print_start(method_name)
        try:
            model = os.getenv("MODEL")
            if not model:
                return "MODEL environment variable not set.", STATIC_PROMPT

            graph_payload = graph.to_dict() if hasattr(graph, "to_dict") else {"graph": str(graph)}
            prompt = f"{STATIC_PROMPT}\n\n{json.dumps(graph_payload, ensure_ascii=False)}"

            request = Request(
                "http://localhost:11434/api/generate",
                data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=120) as response:
                    body = json.loads(response.read().decode("utf-8"))
                if not body.get("response"):
                    return "Ollama returned invalid response format.", prompt
                return str(body["response"]), prompt
            except HTTPError as exc:
                return f"Ollama HTTP error: {exc.code}", prompt
            except URLError:
                return "Ollama connection error.", prompt
            except TimeoutError:
                return "Ollama request timed out.", prompt
            except json.JSONDecodeError:
                return "Ollama returned non-JSON content.", prompt
        finally:
            self._print_end(method_name)

    def render_video(self, script_text: str) -> Path | None:
        """Render a simple video from the generated script."""
        method_name = "render_video"
        self._print_start(method_name)
        try:
            video_path = self.project_root / "diary_movie.mp4"
            text_path = self.project_root / "diary_movie.txt"
            text_path.write_text(script_text, encoding="utf-8")
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                print("ffmpeg not available; skipping video rendering.")
                return None

            textfile = _escape_for_ffmpeg_filter(text_path)
            cmd = [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=1280x720:d=8",
                "-vf",
                f"drawtext=textfile={textfile}:fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(video_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return video_path
        except subprocess.CalledProcessError as exc:
            print(f"ffmpeg failed: {exc.stderr.strip()}")
            return None
        except OSError as exc:
            print(f"ffmpeg OS error: {exc}")
            return None
        finally:
            self._print_end(method_name)

    def upload_video(self, video_path: Path | None, script_text: str) -> dict[str, Any]:
        """Upload generated video payload to configured YT endpoint."""
        method_name = "upload_video"
        self._print_start(method_name)
        try:
            upload_url = os.getenv("YT_UPLOAD_URL")
            channel = os.getenv("YT_CHANNEL")
            if not upload_url or not channel:
                return {"status": "skipped", "reason": "YT_UPLOAD_URL or YT_CHANNEL missing"}
            if not video_path or not video_path.exists():
                return {"status": "failed", "reason": "video file not available"}

            payload = {
                "channel": channel,
                "video_file": str(video_path),
                "script": script_text,
            }
            request = Request(
                upload_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=120) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return {"status": "uploaded", "response": body}
            except HTTPError as exc:
                return {"status": "failed", "reason": f"upload http error: {exc.code}"}
            except URLError:
                return {"status": "failed", "reason": "upload connection error"}
            except TimeoutError:
                return {"status": "failed", "reason": "upload timeout"}
            except json.JSONDecodeError:
                return {"status": "failed", "reason": "upload non-json response"}
        finally:
            self._print_end(method_name)

    def run(self) -> dict[str, Any]:
        """Execute full workflow."""
        method_name = "run"
        self._print_start(method_name)
        try:
            graph, youngest_file = self.load_youngest_diary_graph()
            script_text, prompt = self.generate_script_with_ollama(graph)
            video_path = self.render_video(script_text)
            upload_result = self.upload_video(video_path, script_text)
            return {
                "youngest_file": str(youngest_file),
                "prompt": prompt,
                "script": script_text,
                "video_path": str(video_path) if video_path else None,
                "upload_result": upload_result,
            }
        finally:
            self._print_end(method_name)


if __name__ == "__main__":
    workflow = DiaryYouTubeWorkflow()
    pprint(workflow.run())
