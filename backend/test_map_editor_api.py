"""Tests for the interactive map editor API (Feature 4)."""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.map_editor_api import _grid_from_obstacles, _world_to_cell, _grid_dims


class MapEditorApiTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory(prefix="legged-studio-maps-")
        self.previous_data = os.environ.get("LEGGED_STUDIO_DATA_DIR")
        os.environ["LEGGED_STUDIO_DATA_DIR"] = self.data_dir.name
        self.client = TestClient(app)

    def tearDown(self):
        if self.previous_data is None:
            os.environ.pop("LEGGED_STUDIO_DATA_DIR", None)
        else:
            os.environ["LEGGED_STUDIO_DATA_DIR"] = self.previous_data
        self.data_dir.cleanup()

    def test_catalog_lists_maps(self):
        payload = self.client.get("/api/navigation/maps").json()
        self.assertTrue(payload["success"])
        ids = [m["id"] for m in payload["maps"]]
        self.assertIn("warehouse", ids)
        self.assertIn("flat", ids)
        self.assertTrue(any(m["obstacles"] for m in payload["maps"]))

    def test_plan_route_through_warehouse_corridor(self):
        # Warehouse default obstacles: [[2.0,-1.2,0.6,2.4],[4.5,0.8,0.8,2.0]]
        # Plan from left to right across the corridor.
        response = self.client.post("/api/navigation/maps/plan", json={
            "map_id": "warehouse",
            "obstacles": [[2.0, -1.2, 0.6, 2.4], [4.5, 0.8, 0.8, 2.0]],
            "waypoints": [[0.0, 0.0], [6.0, 0.0]],
            "algorithm": "astar",
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["segments"]), 1)
        self.assertTrue(len(payload["combined_path"]) >= 2)
        self.assertGreater(payload["total_cost_m"], 0)

    def test_dijkstra_matches_astar_cost(self):
        response = self.client.post("/api/navigation/maps/plan", json={
            "map_id": "warehouse",
            "obstacles": [[2.0, -1.2, 0.6, 2.4]],
            "waypoints": [[0.0, 0.0], [6.0, 0.0]],
            "algorithm": "dijkstra",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["segments"][0]["algorithm"], "dijkstra")

    def test_waypoint_inside_obstacle_rejected(self):
        response = self.client.post("/api/navigation/maps/plan", json={
            "map_id": "warehouse",
            "obstacles": [[2.0, -1.2, 0.6, 2.4]],
            "waypoints": [[0.0, 0.0], [2.0, 0.0]],  # right on obstacle center
            "algorithm": "astar",
        })
        self.assertEqual(response.status_code, 400)

    def test_unknown_map_rejected(self):
        response = self.client.post("/api/navigation/maps/plan", json={
            "map_id": "nope", "obstacles": [], "waypoints": [[0, 0], [1, 1]],
        })
        self.assertEqual(response.status_code, 404)

    def test_save_and_load_custom_map(self):
        save = self.client.put("/api/navigation/maps/warehouse", json={
            "map_id": "warehouse",
            "obstacles": [[1.0, 0.0, 0.5, 0.5]],
            "waypoints": [[0.0, 0.0], [3.0, 3.0], [6.0, 0.0]],
            "label": "custom corridor",
        })
        self.assertEqual(save.status_code, 200)
        loaded = self.client.get("/api/navigation/maps/warehouse").json()
        self.assertEqual(loaded["map"]["obstacles"], [[1.0, 0.0, 0.5, 0.5]])
        self.assertEqual(loaded["map"]["waypoints"], [[0.0, 0.0], [3.0, 3.0], [6.0, 0.0]])

    def test_multi_segment_plan(self):
        response = self.client.post("/api/navigation/maps/plan", json={
            "map_id": "warehouse",
            "obstacles": [[2.0, -1.2, 0.6, 2.4]],
            "waypoints": [[0.0, 0.0], [3.0, 2.0], [6.0, 0.0]],
            "algorithm": "astar",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["segments"]), 2)


class MapRasterisationTests(unittest.TestCase):
    def test_grid_dims_square_and_non_square(self):
        cols, rows = _grid_dims([-5, 5, -5, 5], 48)
        self.assertEqual((cols, rows), (48, 48))
        cols2, rows2 = _grid_dims([-2, 8, -4, 4], 48)  # wider than tall
        self.assertEqual((cols2, rows2), (48, 38))

    def test_world_to_cell_mapping(self):
        bounds = [-5, 5, -5, 5]
        cx, cy = _world_to_cell(0.0, 0.0, bounds, 48)
        self.assertEqual((cx, cy), (24, 24))
        cx2, cy2 = _world_to_cell(5.0, 5.0, bounds, 48)
        self.assertEqual((cx2, cy2), (48 - 1, 48 - 1))

    def test_grid_from_obstacle_marks_cells(self):
        raster = _grid_from_obstacles("flat", [[0.0, 0.0, 1.0, 1.0]], 48)
        grid = raster["grid"]
        total_obstacle = sum(sum(row) for row in grid)
        self.assertGreater(total_obstacle, 0)
        # Center cell is an obstacle.
        self.assertEqual(grid[24][24], 1)


if __name__ == "__main__":
    unittest.main()
