"""任务插件（v2 高级仿真"任务即插件"）：注册表 / 实例化 / 诚实边界 的回归锁。

守三件事：

1. **声明 ⇄ 传感器目录对账**：插件只能引用 `contracts/sensor_plugin_contract` 里**真实存在**
   的传感器 id 与输出名（写错即 fail-closed）——否则"声明了却拿不到数据"会静默出现；
2. **实例化真的补齐**：`perception` / `command_source` / `checks` / `recorders` 被填上，
   且 recipe 观测项**委托** S2① 生成（不在这里另写一套 A/B 类语义）；
3. **readiness 不许跳级**：传感器插件当前全部止步 `registered` ⇒ `verified` 必须为 False
   并给出原因；命令来源没有执行器支持时（`command_source=perception`）必须进 blockers。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.task_plugin_contract import (  # noqa: E402
    TaskPluginError,
    validate_task_plugin_payload,
)
from backend import task_plugins as tp  # noqa: E402


class TaskPluginRegistryTest(unittest.TestCase):
    def test_registry_loads_and_every_sensor_id_exists(self):
        registry = tp.load_task_plugins()
        self.assertGreaterEqual(len(registry), 4, "内置任务插件至少 4 条（含零感知基线）")
        for plugin_id, plugin in registry.items():
            with self.subTest(plugin=plugin_id):
                self.assertTrue(plugin.evidence, "每条插件都要写「为什么需要这些传感器」")
                self.assertTrue(plugin.sensors)
                for requirement in plugin.sensors:
                    self.assertTrue(requirement.plugin_id)

    def test_unknown_sensor_id_fails_closed(self):
        with self.assertRaises(TaskPluginError) as ctx:
            validate_task_plugin_payload({
                "plugin_id": "x", "label": "x", "evidence": "e",
                "sensors": [{"plugin_id": "no_such_sensor"}],
            })
        self.assertIn("未知传感器插件", str(ctx.exception))

    def test_unknown_sensor_output_fails_closed(self):
        with self.assertRaises(TaskPluginError) as ctx:
            validate_task_plugin_payload({
                "plugin_id": "x", "label": "x", "evidence": "e",
                "sensors": [{"plugin_id": "depth", "outputs": ["no_such_output"]}],
            })
        self.assertIn("没有输出", str(ctx.exception))

    def test_missing_evidence_is_rejected(self):
        with self.assertRaises(TaskPluginError):
            validate_task_plugin_payload({
                "plugin_id": "x", "label": "x", "evidence": "",
                "sensors": [{"plugin_id": "imu"}],
            })

    def test_unknown_plugin_id_lists_available(self):
        with self.assertRaises(TaskPluginError) as ctx:
            tp.task_plugin("no_such_task")
        self.assertIn("可用", str(ctx.exception))


class TaskPluginInstantiateTest(unittest.TestCase):
    def test_depth_parkour_wires_perception_and_obs_items(self):
        result = tp.instantiate_task_plugin("depth-parkour", scenario={"scenario_id": "demo", "map_id": "rough"})
        scenario = result["scenario"]
        self.assertEqual("obs", scenario["perception"]["route"])          # 插件声明生效
        self.assertEqual(64, scenario["perception"]["depth_camera"]["width"])
        self.assertEqual("rough", scenario["map_id"], "基场景其余字段必须原样保留（插件不是第二个真相）")
        self.assertIn("perception.depth_camera", result["applied"])
        self.assertTrue(result["obs_items"]["items"], "depth 进观测 ⇒ 必须真的生成 obs 项（委托 S2①）")

    def test_external_route_reports_not_applicable(self):
        result = tp.instantiate_task_plugin("heightfield-nav", scenario={"scenario_id": "nav"})
        self.assertEqual("external", result["scenario"]["perception"]["route"])
        self.assertIn(result["obs_items"].get("verdict"), {"not_applicable", "generated"})
        self.assertEqual(["arrival", "route_completion"], result["scenario"]["checks"])
        self.assertEqual("planner", result["scenario"]["command_source"])

    def test_readiness_never_claims_verified(self):
        """传感器插件全在 `registered` ⇒ **不许**说这个任务能跑。"""

        result = tp.instantiate_task_plugin("blind-velocity", scenario={"scenario_id": "b"})
        readiness = result["readiness"]
        self.assertTrue(readiness["ok"])                     # 声明完整、可实例化
        self.assertFalse(readiness["verified"])              # 但没验证过
        self.assertIn("registered", readiness["reason"])

    def test_unsupported_command_source_becomes_a_blocker(self):
        """`command_source=perception` 两端都没执行器 ⇒ 进 blockers（A2 同一口径）。"""

        payload = {
            "schema_version": "task-plugin-1.0",
            "plugin_id": "perception-decision",
            "label": "感知决策（未支持）",
            "evidence": "用于验证：契约允许但执行器不支持时必须拦住",
            "sensors": [{"plugin_id": "depth", "outputs": ["policy_tensor"]}],
            "perception": {"route": "obs", "depth_camera": {"width": 32, "height": 18}},
            "command_source": "perception",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text(json.dumps({"schema_version": "task-plugin-registry-1.0", "plugins": [payload]}),
                            encoding="utf-8")
            result = tp.instantiate_task_plugin("perception-decision", load_path=path)
        self.assertFalse(result["readiness"]["ok"])
        self.assertTrue(result["readiness"]["blockers"])
        self.assertIn("perception", result["readiness"]["blockers"][0])

    def test_unconsumed_checks_are_reported_not_hidden(self):
        """声明了但今天没人执行的判据/记录器要**如实列出**，不能静默写进场景就算完。"""

        payload = {
            "schema_version": "task-plugin-1.0",
            "plugin_id": "custom-checks",
            "label": "自定义判据",
            "evidence": "用于验证：未消费的判据名要单独报出来",
            "sensors": [{"plugin_id": "imu"}],
            "perception": {"route": "external"},
            "checks": ["arrival", "some_future_check"],
            "recorders": ["metrics", "future_recorder"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text(json.dumps({"schema_version": "task-plugin-registry-1.0", "plugins": [payload]}),
                            encoding="utf-8")
            result = tp.instantiate_task_plugin("custom-checks", load_path=path)
        self.assertEqual(["some_future_check"], result["readiness"]["unconsumed_checks"])
        self.assertEqual(["future_recorder"], result["readiness"]["unconsumed_recorders"])


class TaskPluginApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        import backend.api_complete as api_complete

        self.client = TestClient(api_complete.app)

    def test_list_and_instantiate(self):
        listed = self.client.get("/api/task-plugins")
        self.assertEqual(200, listed.status_code)
        payload = listed.json()
        self.assertTrue(payload["success"])
        self.assertGreaterEqual(payload["count"], 4)
        ids = {item["plugin_id"] for item in payload["plugins"]}
        self.assertIn("depth-parkour", ids)

        response = self.client.post("/api/task-plugins/depth-parkour/instantiate",
                                    json={"scenario": {"scenario_id": "demo"}})
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual("obs", body["scenario"]["perception"]["route"])

    def test_unknown_plugin_is_400_with_available_ids(self):
        response = self.client.post("/api/task-plugins/no_such_task/instantiate", json={})
        self.assertEqual(400, response.status_code)
        self.assertIn("可用", response.json()["detail"])


class BuiltinTaskCatalogTest(unittest.TestCase):
    """**内置任务的取证与接线**（2026-09-22 第二批：里程计+航点 / 视觉 / 其他传感器）。

    为什么逐条钉：任务插件最容易退化成"名字好听、证据空口"——传感器 id 抄错会被契约挡住，
    但"这个任务凭什么需要这些传感器""上游谁这么干过"**只有证据能挡**。所以：
      · 每条必须有**可追溯的取证**（长度 + 至少一处路径/来源引用）；
      · `task_type` 必须是验收器**真有的判据族**（否则挂上去了却没人判）；
      · 视觉/接触类必须真的把传感器接到**观测**上（`route=obs` ⇒ S2① 生成 obs 项）。
    """

    def test_catalog_has_the_named_builtins(self):
        registry = tp.load_task_plugins()
        self.assertGreaterEqual(len(registry), 10)
        for plugin_id in ("odom-waypoint-nav", "depth-ts-locomotion", "depth-decoder-policy",
                          "wheel-leg-terrain", "lidar-terrain-avoid", "attitude-balance"):
            with self.subTest(plugin=plugin_id):
                self.assertIn(plugin_id, registry)

    def test_every_evidence_is_traceable(self):
        """取证不许空口：至少 80 字，且带一处路径/来源引用（上游工程或本仓文件）。"""

        for plugin_id, plugin in tp.load_task_plugins().items():
            with self.subTest(plugin=plugin_id):
                self.assertGreaterEqual(len(plugin.evidence), 80, f"{plugin_id} 的 evidence 太短，说不清凭什么")
                self.assertIn("/", plugin.evidence, f"{plugin_id} 的 evidence 没有一处可核对的路径")

    def test_task_type_is_a_known_criteria_family(self):
        """`task_type` 必须是 `tools/sim2sim_headless.py::DEFAULT_CRITERIA` 真有的族。

        否则会出现"任务声明了类型、验收器却没这一族"（`gait` 族当年就是这样缺的：
        三条 lainlab 策略在无头验收里直接 KeyError）。
        """

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location("sim2sim_headless_criteria",
                                                          ROOT / "tools" / "sim2sim_headless.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            families = set(module.DEFAULT_CRITERIA)
        except Exception as exc:  # pragma: no cover - 环境缺 mujoco 时如实跳过
            self.skipTest(f"读不到 DEFAULT_CRITERIA：{exc}")
        for plugin_id, plugin in tp.load_task_plugins().items():
            if plugin.task_type:
                with self.subTest(plugin=plugin_id):
                    self.assertIn(plugin.task_type, families)

    def test_odom_waypoint_nav_wires_planner_and_route_checks(self):
        plugin = tp.task_plugin("odom-waypoint-nav")
        self.assertEqual("planner", plugin.command_source)
        self.assertEqual(["arrival", "route_completion"], list(plugin.checks))
        self.assertEqual({"odom", "imu"}, {s.plugin_id for s in plugin.sensors})
        result = tp.instantiate_task_plugin("odom-waypoint-nav", scenario={"scenario_id": "nav"})
        self.assertEqual("planner", result["scenario"]["command_source"])
        self.assertEqual(["arrival", "route_completion"], result["scenario"]["checks"])
        # 规划器是两执行器都支持的取值 ⇒ 不该被 blockers 拦
        self.assertTrue(result["readiness"]["executor"]["supported"])
        self.assertFalse(result["readiness"]["blockers"])

    def test_depth_ts_uses_upstream_camera_size_and_generates_obs(self):
        """深度相机的 80×60 不是随手写的：取上游 `resolution=(60, 80)`（高, 宽）。"""

        result = tp.instantiate_task_plugin("depth-ts-locomotion", scenario={"scenario_id": "depth"})
        camera = result["scenario"]["perception"]["depth_camera"]
        self.assertEqual({"width": 80, "height": 60}, {"width": camera["width"], "height": camera["height"]})
        self.assertEqual("obs", result["scenario"]["perception"]["route"])
        self.assertTrue(result["obs_items"]["items"], "route=obs ⇒ 必须真的生成 obs 项（委托 S2①）")

    def test_low_resolution_depth_decoder_plugin(self):
        result = tp.instantiate_task_plugin("depth-decoder-policy", scenario={"scenario_id": "edge"})
        camera = result["scenario"]["perception"]["depth_camera"]
        self.assertEqual({"width": 16, "height": 16}, {"width": camera["width"], "height": camera["height"]})

    def test_wheel_leg_terrain_feeds_height_and_contact(self):
        result = tp.instantiate_task_plugin("wheel-leg-terrain", scenario={"scenario_id": "terrain"})
        perception = result["scenario"]["perception"]
        self.assertTrue(perception["heightfield"])
        self.assertTrue(perception["foot_contact"])
        self.assertEqual("obs", perception["route"])
        terms = {item.get("term") for item in result["obs_items"]["items"]}
        self.assertTrue(terms, "地形+接触都进观测 ⇒ 必须生成 obs 项")

    def test_attitude_balance_does_not_patch_command_source(self):
        """没有指令流的任务**不许**顺手给别人塞一个 command_source（保持基场景原样）。"""

        result = tp.instantiate_task_plugin("attitude-balance",
                                            scenario={"scenario_id": "bal", "command_source": "script"})
        self.assertEqual("script", result["scenario"]["command_source"])
        self.assertNotIn("command_source", result["applied"])


if __name__ == "__main__":
    unittest.main()
