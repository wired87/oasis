import json
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from mcp_master import MCPMaster


class TestMCPMaster(unittest.TestCase):
    def test_create_route_from_service_payload(self):
        access_calls = []

        def access_backend(uid, total_score):
            access_calls.append((uid, total_score))
            return uid == "user-1"

        master = MCPMaster(project_root=Path.cwd(), access_backend=access_backend)
        payload = {
            "service:maps": {
                "service_embeddings": [0.1, 0.2],
                "event_nodes": [{"score": 1.5}, {"rank": 2.5}, {"score": 1.0, "rank": 9.0}, {"score": "x"}, {}],
            }
        }

        routes = master.create_new_routes(payload)
        today = datetime.now(UTC).strftime("%Y%m%d")
        route_name = f"service_maps_{today}"

        self.assertIn(route_name, routes)
        self.assertEqual(routes[route_name].__doc__, "[0.1, 0.2]")
        self.assertEqual(routes[route_name]("user-1"), payload["service:maps"]["event_nodes"])
        self.assertEqual(routes[route_name]("blocked"), [])
        self.assertEqual(access_calls, [("user-1", 5.0), ("blocked", 5.0)])

    def test_create_route_from_env_payload(self):
        original = os.environ.get("MCP_ROUTE_TEST")
        os.environ["MCP_ROUTE_TEST"] = json.dumps(
            {
                "service:test": {
                    "service_embeddings": "embedding-doc",
                    "event_data": [{"score": 5.0}],
                }
            }
        )
        try:
            master = MCPMaster(project_root=Path.cwd(), access_backend=lambda uid, total_score: True)
            routes = master.create_new_routes()
            today = datetime.now(UTC).strftime("%Y%m%d")
            route_name = f"service_test_{today}"

            self.assertIn(route_name, routes)
            self.assertEqual(routes[route_name].__doc__, "embedding-doc")
            self.assertEqual(routes[route_name]("u-1"), [{"score": 5.0}])
        finally:
            if original is None:
                os.environ.pop("MCP_ROUTE_TEST", None)
            else:
                os.environ["MCP_ROUTE_TEST"] = original


if __name__ == "__main__":
    unittest.main()
