"""批次 4 DoD：terrain 移植/场景库 API + 航点规划器测试。"""

from __future__ import annotations

import unittest

from backend.route_planner import plan_route
from backend.terrain_gen import SUPPORTED_ELEMENT_TYPES, SUPPORTED_TERRAIN_TYPES


class RoutePlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        # 8x8 空网格 + 一堵带缺口的墙
        self.grid = [[0] * 8 for _ in range(8)]
        for row in range(8):
            if row != 3:  # 缺口在第 3 行
                self.grid[row][4] = 1

    def test_astar_finds_gap_route(self) -> None:
        result = plan_route(self.grid, (0, 0), (0, 7), algorithm="astar")
        self.assertEqual(result.path[0], (0, 0))
        self.assertEqual(result.path[-1], (0, 7))
        self.assertIn((3, 4), result.path, "路径必须穿过第 3 行缺口")

    def test_dijkstra_same_cost_as_astar(self) -> None:
        astar = plan_route(self.grid, (0, 0), (0, 7), algorithm="astar")
        dijkstra = plan_route(self.grid, (0, 0), (0, 7), algorithm="dijkstra")
        self.assertAlmostEqual(astar.cost, dijkstra.cost, places=6)

    def test_start_on_obstacle_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_route(self.grid, (0, 4), (7, 7))

    def test_unreachable_goal_rejected(self) -> None:
        sealed = [[1] * 8 for _ in range(8)]
        sealed[0][0] = 0
        with self.assertRaises(ValueError):
            plan_route(sealed, (0, 0), (7, 7))


class TerrainCatalogTest(unittest.TestCase):
    def test_catalog_scope(self) -> None:
        self.assertEqual(len(SUPPORTED_TERRAIN_TYPES), 5)
        self.assertEqual(len(SUPPORTED_ELEMENT_TYPES), 11)


if __name__ == "__main__":
    unittest.main()
