"""H4 / H24：A 类感知绑定校验测试。

真实数据打样：`assets/robots/unitree_go2` 的 `go2-parkour` profile 是仓库里唯一
"策略真的吃深度相机"的 A 类样本（`obs_groups.actor=[actor,proprio_history,camera]`
+ `depth.shape=[2,60,86]`），所以用它做集成断言：要求 `depth_camera` 通过、要求
`heightfield` 必须**红**（该 profile 并没有声明高度场）。
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.perception_binding import (
    check_perception_binding,
    load_profile_for_policy,
    profile_declared_items,
    required_items,
)

PACKAGE = __import__("pathlib").Path("assets/robots/unitree_go2")
SIM_CFG = __import__("json").loads(
    (PACKAGE / "simulation" / "config.json").read_text(encoding="utf-8-sig")
)


class RequiredItemsTests(unittest.TestCase):
    def test_only_enabled_fields_count(self):
        self.assertEqual(required_items({"heightfield": True, "depth_camera": None, "foot_contact": False}),
                         ["heightfield"])
        self.assertEqual(required_items({"depth_camera": {"width": 106, "height": 60}}), ["depth_camera"])
        self.assertEqual(required_items({"depth_camera": {}}), [], "空对象不算启用")

    def test_accepts_pydantic_perception_spec(self):
        from contracts.scenario_contract import PerceptionSpec

        self.assertEqual(required_items(PerceptionSpec(heightfield=True)), ["heightfield"])


class ProfileDeclarationTests(unittest.TestCase):
    def test_go2_parkour_profile_declares_depth_camera(self):
        profile, profile_id = load_profile_for_policy(PACKAGE, SIM_CFG, "go2-pie-parkour")
        self.assertEqual(profile_id, "go2-parkour", "策略卡 go2-pie-parkour 的训练 profile 应为 go2-parkour")
        declared = profile_declared_items(profile)
        self.assertIn("depth_camera", declared["declared"])
        self.assertTrue(declared["evidence"]["depth_camera"], "必须给出命中位置供复核")

    def test_explicit_perception_items_wins(self):
        declared = profile_declared_items({"perception_items": ["heightfield", "foot_contact"]})
        self.assertEqual(declared["source"], "explicit")
        self.assertEqual(declared["declared"], ["foot_contact", "heightfield"])

    def test_missing_profile_is_not_treated_as_declared(self):
        declared = profile_declared_items(None)
        self.assertEqual(declared["declared"], [])
        self.assertEqual(declared["source"], "missing-profile")


class BindingVerdictTests(unittest.TestCase):
    def test_b_class_is_not_applicable(self):
        verdict = check_perception_binding({"route": "external", "heightfield": True}, None)
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["verdict"], "not_applicable")

    def test_no_perception_is_not_applicable(self):
        self.assertEqual(check_perception_binding(None, None)["verdict"], "not_applicable")

    def test_class_a_depth_camera_passes_with_go2_parkour(self):
        profile, profile_id = load_profile_for_policy(PACKAGE, SIM_CFG, "go2-pie-parkour")
        verdict = check_perception_binding(
            {"route": "obs", "depth_camera": {"width": 106, "height": 60}},
            profile, policy_id="go2-pie-parkour", profile_id=profile_id,
        )
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["verdict"], "ok")
        self.assertEqual(verdict["missing"], [])

    def test_class_a_heightfield_fails_with_go2_parkour(self):
        profile, profile_id = load_profile_for_policy(PACKAGE, SIM_CFG, "go2-pie-parkour")
        verdict = check_perception_binding(
            {"route": "obs", "heightfield": True}, profile,
            policy_id="go2-pie-parkour", profile_id=profile_id,
        )
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["verdict"], "missing")
        self.assertEqual(verdict["missing"], ["heightfield"])
        self.assertEqual(len(verdict["fix"]), 2, "必须给出两种修法")
        self.assertIn("external", verdict["fix"][1])

    def test_unknown_policy_fails_closed(self):
        profile, profile_id = load_profile_for_policy(PACKAGE, SIM_CFG, "no-such-policy")
        self.assertIsNone(profile)
        verdict = check_perception_binding({"route": "obs", "heightfield": True}, profile,
                                           policy_id="no-such-policy", profile_id=profile_id)
        self.assertFalse(verdict["ok"], "找不到 profile 不能当通过")

    def test_obs_route_without_items_is_not_applicable(self):
        verdict = check_perception_binding({"route": "obs"}, {"perception_items": ["heightfield"]})
        self.assertEqual(verdict["verdict"], "not_applicable")


class BindingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_endpoint_ok_for_depth_camera(self):
        response = self.client.post("/api/perception/binding", json={
            "robot_id": "unitree_go2",
            "policy_id": "go2-pie-parkour",
            "perception": {"route": "obs", "depth_camera": {"width": 106, "height": 60}},
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile_id"], "go2-parkour")

    def test_endpoint_flags_missing_heightfield(self):
        response = self.client.post("/api/perception/binding", json={
            "robot_id": "unitree_go2",
            "policy_id": "go2-pie-parkour",
            "perception": {"route": "obs", "heightfield": True},
        })
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["missing"], ["heightfield"])
        self.assertIn("reason", payload)

    def test_endpoint_external_route_is_not_applicable(self):
        response = self.client.post("/api/perception/binding", json={
            "robot_id": "unitree_go2",
            "policy_id": "go2-pie-parkour",
            "perception": {"route": "external", "heightfield": True},
        })
        self.assertEqual(response.json()["verdict"], "not_applicable")

    def test_endpoint_unknown_robot_404(self):
        response = self.client.post("/api/perception/binding", json={"robot_id": "no_such_robot"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
