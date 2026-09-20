"""S2②（服务端那一半）：场景声明 A 类感知时，与所选策略不匹配 ⇒ **拒绝启动仿真会话**。

`POST /api/simulation/sessions` 以前不看策略：场景写 `perception.route=obs` 只表达"策略
应该吃传感器"，而"到底吃没吃"只有该策略的训练 profile 知道。后果是两种静默假象
（该项被运行期忽略，或形状不一致查不出原因）——所以这里在**启动之前** fail-closed。

真实数据打样：`assets/robots/unitree_go2` 的 `go2-pie-parkour` 是仓库里唯一"策略真的吃
深度相机"的 A 类样本，故用它断言：
* 要求 `depth_camera` ⇒ 放行；
* 要求 `heightfield` ⇒ **400**（该 profile 并未声明高度场）；
* 不传 `policy_id` ⇒ 跳过校验（保持既有调用方向后兼容）。
"""

import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app


def _session_body(**overrides) -> dict:
    body = {
        "robot_id": "unitree_go2",
        "map_id": "flat",
        "mode": "basic",
        "scenario": {
            "scenario_id": "a_class_probe",
            "map_id": "flat",
            "mode": "basic",
            "command_source": "policy",
            "perception": {"route": "obs", "depth_camera": {"width": 106, "height": 60}},
        },
    }
    body.update(overrides)
    return body


class SessionAClassGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_matching_a_class_scenario_starts(self):
        response = self.client.post(
            "/api/simulation/sessions",
            json=_session_body(policy_id="go2-pie-parkour"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["success"])

    def test_unmet_a_class_requirement_refuses_to_start(self):
        body = _session_body(policy_id="go2-pie-parkour")
        body["scenario"]["perception"] = {"route": "obs", "heightfield": True}
        response = self.client.post("/api/simulation/sessions", json=body)
        self.assertEqual(response.status_code, 400, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["verdict"], "missing")
        self.assertIn("heightfield", detail["missing"])
        self.assertEqual(detail["policy_id"], "go2-pie-parkour")
        self.assertIn("fix", detail)

    def test_without_policy_id_the_check_is_skipped(self):
        """不传策略就无从对照 —— 跳过校验（既有调用方零改动）。"""
        body = _session_body()
        body["scenario"]["perception"] = {"route": "obs", "heightfield": True}
        response = self.client.post("/api/simulation/sessions", json=body)
        self.assertEqual(response.status_code, 200, response.text)

    def test_class_b_scenario_is_not_checked(self):
        """B 类（route=external）感知在策略外 ⇒ 不该因为"策略没声明"被拒。"""
        body = _session_body(policy_id="go2-pie-parkour")
        body["scenario"]["perception"] = {"route": "external", "heightfield": True}
        response = self.client.post("/api/simulation/sessions", json=body)
        self.assertEqual(response.status_code, 200, response.text)

    def test_unknown_policy_fails_closed(self):
        """策略找不到 ⇒ profile 读不到 ⇒ 按 fail-closed 判 missing（不放行）。"""
        response = self.client.post(
            "/api/simulation/sessions",
            json=_session_body(policy_id="no-such-policy"),
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["verdict"], "missing")


if __name__ == "__main__":
    unittest.main()
