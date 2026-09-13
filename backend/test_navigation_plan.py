"""H3：导航计划装配（planner 命令来源）测试。

守什么：

1. **判据单一真值（H10）**：航点容差默认取 ``registry/arrival_criteria.json``；
   只有场景**显式**写了 ``tolerance`` 才用场景值，并标注 ``tolerance_source``；
2. **规划唯一实现**：``/api/navigation/plan`` 与 ``POST /api/simulation/sessions``
   返回的是同一份装配（同一路径、同一容差），两端不会各算一套；
3. **不许静默兜底**：无路可走时抛 400；地图不存在抛 404；航点不足抛 400
   —— 回退成"直线穿过障碍"比报错更糟；
4. **向后兼容**：``command_source=policy``（默认）时会话响应里 ``navigation`` 为 ``None``。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.arrival_criteria import waypoint_spec
from backend.navigation_plan import build_navigation_payload
from backend.scenario_maps import MAPS

REGISTRY_TOL = float(waypoint_spec()["tolerance_m"])


def _plan(map_id: str, waypoints, **kwargs):
    """在**独立工作线程**里跑协程。

    为什么不用 ``asyncio.run`` 直接跑：全量测试时同进程内可能已有别的用例启动过事件循环
    （FastAPI TestClient / anyio portal），此时主线程里 ``asyncio.run`` 会直接报
    "cannot be called from a running event loop"，被测协程因此**从未被 await**
    ——表现为"单跑通过、全量失败"的假象。工作线程里没有运行中的循环，天然免疫顺序影响。
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, build_navigation_payload(map_id, waypoints, **kwargs)).result()


class NavigationPlanBuilderTests(unittest.TestCase):
    def test_warehouse_plan_uses_registry_tolerance_by_default(self):
        payload = _plan("warehouse", MAPS["warehouse"]["default_waypoints"])
        self.assertEqual(payload["command_source"], "planner")
        self.assertGreaterEqual(len(payload["plan"]["combined_path"]), 2)
        self.assertEqual(payload["arrival"]["tolerance_m"], REGISTRY_TOL)
        self.assertEqual(payload["arrival"]["source"], "registry/arrival_criteria.json")
        for waypoint in payload["waypoints"]:
            with self.subTest(waypoint=waypoint):
                self.assertEqual(waypoint["tolerance_m"], round(REGISTRY_TOL, 4))
                self.assertEqual(waypoint["tolerance_source"], "registry/arrival_criteria.json")

    def test_explicit_tolerance_is_honoured_and_marked(self):
        payload = _plan("warehouse", [{"x": 0.0, "y": 0.0}, {"x": 6.0, "y": 0.0, "tolerance": 0.12}])
        self.assertEqual(payload["waypoints"][1]["tolerance_m"], 0.12)
        self.assertEqual(payload["waypoints"][1]["tolerance_source"], "scenario")
        # 未显式声明的那个仍用注册表
        self.assertEqual(payload["waypoints"][0]["tolerance_source"], "registry/arrival_criteria.json")

    def test_plan_avoids_map_obstacles(self):
        payload = _plan("warehouse", MAPS["warehouse"]["default_waypoints"])
        obstacles = payload["obstacles"]
        self.assertTrue(obstacles, "warehouse 应自带障碍")
        for x, y in payload["plan"]["combined_path"]:
            for cx, cy, half_w, half_h in obstacles:
                inside = abs(x - cx) < half_w and abs(y - cy) < half_h
                self.assertFalse(inside, f"路径点 ({x}, {y}) 落在障碍内部")

    def test_blocked_goal_raises_400_not_silent_fallback(self):
        wall = [[3.0, 0.0, 0.25, 4.0]]  # 竖墙把 x=3 整条封住
        with self.assertRaises(HTTPException) as ctx:
            _plan("warehouse", [[0.0, 0.0], [6.0, 0.0]], obstacles=wall)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_map_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            _plan("no_such_map", [[0.0, 0.0], [1.0, 0.0]])
        self.assertEqual(ctx.exception.status_code, 404)

    def test_too_few_waypoints_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            _plan("flat", [[0.0, 0.0]])
        self.assertEqual(ctx.exception.status_code, 400)


class NavigationPlanEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_plan_endpoint_returns_shared_payload(self):
        response = self.client.post(
            "/api/navigation/plan",
            json={"map_id": "warehouse", "waypoints": MAPS["warehouse"]["default_waypoints"]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["arrival"]["tolerance_m"], REGISTRY_TOL)
        self.assertGreaterEqual(len(payload["plan"]["combined_path"]), 2)

    def test_plan_endpoint_rejects_bad_waypoint_shape(self):
        response = self.client.post("/api/navigation/plan", json={"map_id": "warehouse", "waypoints": [[0.0, 0.0, 1.0], [1.0, 1.0]]})
        self.assertEqual(response.status_code, 422)

    def test_session_attaches_same_plan_for_planner_source(self):
        response = self.client.post(
            "/api/simulation/sessions",
            json={
                "robot_id": "unitree_go2",
                "map_id": "warehouse",
                "mode": "navigation",
                "scenario": {
                    "scenario_id": "nav_probe",
                    "mode": "navigation",
                    "command_source": "planner",
                    "waypoints": [{"x": 0.0, "y": 0.0}, {"x": 6.0, "y": 0.0}],
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        navigation = payload["navigation"]
        self.assertIsNotNone(navigation)
        self.assertEqual(navigation["arrival"]["tolerance_m"], REGISTRY_TOL)
        self.assertGreaterEqual(len(navigation["plan"]["combined_path"]), 2)
        # 与 /api/navigation/plan 同一份装配：路径点数与代价一致
        direct = self.client.post(
            "/api/navigation/plan",
            json={"map_id": "warehouse", "waypoints": [[0.0, 0.0], [6.0, 0.0]]},
        ).json()
        self.assertEqual(
            len(navigation["plan"]["combined_path"]),
            len(direct["plan"]["combined_path"]),
        )
        self.assertEqual(navigation["plan"]["total_cost_m"], direct["plan"]["total_cost_m"])
        self.client.delete(f"/api/simulation/sessions/{payload['session_id']}")

    def test_session_without_planner_source_has_no_navigation(self):
        response = self.client.post(
            "/api/simulation/sessions",
            json={"robot_id": "unitree_go2", "map_id": "flat", "mode": "basic"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIsNone(payload["navigation"])
        self.client.delete(f"/api/simulation/sessions/{payload['session_id']}")

    def test_session_rejects_planner_without_waypoints(self):
        response = self.client.post(
            "/api/simulation/sessions",
            json={
                "robot_id": "unitree_go2",
                "map_id": "warehouse",
                "mode": "navigation",
                "scenario": {"scenario_id": "nav_bad", "mode": "navigation", "command_source": "planner"},
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
