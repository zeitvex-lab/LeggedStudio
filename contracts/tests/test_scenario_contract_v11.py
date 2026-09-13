"""scenario-contract-1.1 对齐测试（H1 / H24）。

守什么：

1. **模型与 schema 不再漂移**：``schema_version`` 默认值必须与
   ``contracts/schema/scenario-contract-1.1.schema.json`` 的 ``$id`` 尾号一致；
   1.1 的四组字段（terrain / termination / assessment / perception）必须真的进模型
   ——此前模型停在 1.0，写进场景的高级仿真字段被**静默丢弃**。
2. **感知分层是契约约束，不是约定**（H24）：``route=obs``（A 类）⇒ 策略自己吃感知
   ⇒ ``command_source=policy``；``planner`` / ``perception``（B 类外部决策）⇒ 必须有航点。
3. **后向兼容**：1.0 载荷（没有新字段）仍能构造并通过。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.scenario_contract import PerceptionSpec, ScenarioContract

SCHEMA = Path(__file__).resolve().parents[1] / "schema" / "scenario-contract-1.1.schema.json"


class SchemaAlignmentTests(unittest.TestCase):
    def test_default_version_matches_schema_id(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        expected = str(schema["$id"]).rsplit("/", 1)[-1]
        self.assertEqual(ScenarioContract(scenario_id="probe").schema_version, expected)

    def test_schema_advanced_properties_all_present_in_model(self):
        """schema 的每个高级仿真属性都必须在模型里有对应字段（漂移即红）。"""
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        advanced = {"terrain", "termination", "assessment", "perception"}
        declared = set((schema.get("properties") or {}).keys())
        self.assertTrue(advanced.issubset(declared), "schema 缺高级仿真字段")
        for name in sorted(advanced):
            with self.subTest(field=name):
                self.assertIn(name, ScenarioContract.model_fields)

    def test_v10_payload_still_valid(self):
        legacy = ScenarioContract(schema_version="scenario-contract-1.0", scenario_id="legacy_scene")
        self.assertEqual(legacy.schema_version, "scenario-contract-1.0")
        self.assertIsNone(legacy.terrain)

    def test_unknown_version_rejected(self):
        with self.assertRaises(ValueError):
            ScenarioContract(schema_version="scenario-contract-9.9", scenario_id="probe")


class AdvancedFieldsTests(unittest.TestCase):
    def test_advanced_fields_survive_to_payload(self):
        scenario = ScenarioContract(
            scenario_id="go2_nav_parkour",
            mode="navigation",
            terrain={"kind": "stairs", "elements": [{"type": "stairs", "params": {"step_height": 0.1}}]},
            termination={"fall_pitch": 0.8, "timeout": 30.0, "collision_count": 3},
            assessment={"route_completion_min": 0.9, "tracking_error_max": 0.15, "stability": True},
            perception={"heightfield": True, "depth_camera": {"width": 106, "height": 60}, "foot_contact": True},
        )
        payload = scenario.to_payload()
        self.assertEqual(payload["terrain"]["kind"], "stairs")
        self.assertEqual(payload["termination"]["collision_count"], 3)
        self.assertEqual(payload["assessment"]["route_completion_min"], 0.9)
        self.assertTrue(payload["perception"]["heightfield"])
        self.assertEqual(payload["perception"]["depth_camera"]["width"], 106)

    def test_depth_camera_bounds(self):
        with self.assertRaises(ValueError):
            PerceptionSpec(depth_camera={"width": 0, "height": 60})


class PerceptionRoutingTests(unittest.TestCase):
    """H24：感知分层（A 类 obs / B 类 external）必须是 fail-closed 的契约约束。"""

    def test_class_a_requires_policy_command_source(self):
        ok = ScenarioContract(
            scenario_id="a_class",
            perception={"depth_camera": {"width": 64, "height": 36}, "route": "obs"},
        )
        self.assertEqual(ok.command_source, "policy")
        self.assertEqual(ok.perception.route, "obs")
        with self.assertRaises(ValueError):
            ScenarioContract(
                scenario_id="a_class_bad",
                command_source="planner",
                waypoints=[{"x": 1.0, "y": 0.0}],
                perception={"route": "obs"},
            )

    def test_class_b_external_sensor_allows_planner_and_needs_waypoints(self):
        with self.assertRaises(ValueError):
            ScenarioContract(scenario_id="b_class_no_goal", command_source="planner")
        ok = ScenarioContract(
            scenario_id="b_class",
            command_source="planner",
            waypoints=[{"x": 2.0, "y": 1.0}],
            perception={"route": "external", "mount": "scene:corridor-1"},
        )
        self.assertEqual(ok.perception.route, "external")
        self.assertEqual(ok.perception.mount, "scene:corridor-1")

    def test_external_route_default(self):
        """未声明 route 时按 B 类（external）——策略不必吃传感器，这是 H 组的默认裁决。"""
        spec = PerceptionSpec()
        self.assertEqual(spec.route, "external")
        self.assertEqual(spec.mount, "base")

    def test_blank_mount_rejected(self):
        with self.assertRaises(ValueError):
            PerceptionSpec(mount="")


if __name__ == "__main__":
    unittest.main()
