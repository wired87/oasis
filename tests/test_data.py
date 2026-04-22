import unittest
from pathlib import Path

from data import DataWorkflow


class TestDataWorkflow(unittest.TestCase):
    def test_build_graph_and_rank_events(self):
        workflow = DataWorkflow(project_root=Path.cwd())
        events = [
            {
                "event_id": "evt_a",
                "service": "YouTube",
                "timestamp": "2026-04-22T10:00:00Z",
                "action": "Watch",
                "metadata": {"k1": 1, "k2": 2},
            },
            {
                "event_id": "evt_b",
                "service": "YouTube",
                "timestamp": "2026-04-22T10:00:00Z",
                "action": "Like",
                "metadata": {"k1": "x"},
            },
        ]
        graph = workflow.build_graph(events)
        ranks = workflow.rank_event_nodes()

        self.assertIsNotNone(graph)
        self.assertIn("evt_a", ranks)
        self.assertIn("evt_b", ranks)
        self.assertGreater(ranks["evt_a"], 0)
        self.assertGreater(ranks["evt_b"], 0)

    def test_service_payload_shape(self):
        workflow = DataWorkflow(project_root=Path.cwd())
        workflow.build_graph(
            [
                {
                    "event_id": "evt_1",
                    "service": "Maps",
                    "timestamp": "2026-04-22T11:00:00Z",
                    "action": "Search",
                    "metadata": {"query": "restaurant"},
                }
            ]
        )
        workflow.rank_event_nodes()
        payload = workflow.summarize_services()
        service_id = "service:maps"

        self.assertIn(service_id, payload)
        self.assertIn("service_embeddings", payload[service_id])
        self.assertIn("event_nodes", payload[service_id])
        self.assertIsInstance(payload[service_id]["event_nodes"], list)
        self.assertEqual(len(payload[service_id]["event_nodes"]), 1)


if __name__ == "__main__":
    unittest.main()
