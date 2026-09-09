"""Tests for the generic perception observation catalog (Feature 6)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.perception_observations import PERCEPTION_ITEMS, list_perception_items


class PerceptionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_catalog_contains_perception_pipeline(self):
        ids = [item["id"] for item in list_perception_items()]
        # The three perception stages must be present as generic items.
        for required in ("foot_contact", "heightfield", "depth_camera"):
            self.assertIn(required, ids)

    def test_items_endpoint(self):
        payload = self.client.get("/api/perception/items").json()
        self.assertTrue(payload["success"])
        items = payload["items"]
        self.assertGreaterEqual(payload["count"], 6)
        by_id = {item["id"]: item for item in items}
        self.assertEqual(by_id["depth_camera"]["width"], 6360)
        self.assertEqual(by_id["depth_camera"]["sensor"], "depth_camera")
        self.assertEqual(by_id["foot_contact"]["width"], 4)
        self.assertIn("106", str(by_id["depth_camera"].get("meta")))

    def test_single_item_endpoint(self):
        payload = self.client.get("/api/perception/items/depth_camera").json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["item"]["id"], "depth_camera")
        self.assertEqual(payload["item"]["sample_dot_path"], "environment.observations.actor.terms.depth_scan")

    def test_unknown_item_404(self):
        response = self.client.get("/api/perception/items/nope")
        self.assertEqual(response.status_code, 404)

    def test_required_items_have_width_and_scale(self):
        for item in PERCEPTION_ITEMS.values():
            self.assertGreater(item.width, 0)
            self.assertGreater(item.scale, 0)
            self.assertTrue(item.sample_dot_path)


if __name__ == "__main__":
    unittest.main()
