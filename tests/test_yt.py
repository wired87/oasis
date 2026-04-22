import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yt import DiaryYouTubeWorkflow


class _MockHTTPResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _MockGraph:
    def to_dict(self):
        return {"nodes": {}}


class TestDiaryYouTubeWorkflow(unittest.TestCase):
    def test_load_youngest_diary_graph_uses_latest_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            older = data_dir / "older.json"
            newer = data_dir / "newer.json"
            older.write_text(json.dumps({"nodes": {"a": {"node_type": "EVENT"}}, "edges": []}), encoding="utf-8")
            newer.write_text(json.dumps({"nodes": {"b": {"node_type": "EVENT"}}, "edges": []}), encoding="utf-8")
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))

            workflow = DiaryYouTubeWorkflow(project_root=root)
            graph, youngest = workflow.load_youngest_diary_graph()

            self.assertEqual(youngest.name, "newer.json")
            self.assertIn("b", graph.nodes)

    @patch("yt.urlopen")
    def test_generate_script_with_ollama_uses_static_prompt_and_model(self, mock_urlopen):
        mock_urlopen.return_value = _MockHTTPResponse({"response": "movie script"})
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "data").mkdir(parents=True, exist_ok=True)
            workflow = DiaryYouTubeWorkflow(project_root=root)

            with patch.dict(os.environ, {"MODEL": "llama3.1"}, clear=False):
                script, prompt = workflow.generate_script_with_ollama(_MockGraph())

            self.assertEqual(script, "movie script")
            self.assertIn("Generate movie script from given diary graph", prompt)
            called_request = mock_urlopen.call_args.args[0]
            request_data = json.loads(called_request.data.decode("utf-8"))
            self.assertEqual(request_data["model"], "llama3.1")


if __name__ == "__main__":
    unittest.main()
