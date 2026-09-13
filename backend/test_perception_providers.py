"""S6：感知 provider 注册表 + 地形分类 + 切换动作层测试。

守什么：

1. **注册表是权威（K4 口径）**：清单 schema/id 唯一/entry_point 必须真实可解析；
   未知 provider 报错不回退；清单"谎报"（模块不存在）必须报错；目录里有文件但未登记
   只作诊断、不作注册来源；
2. **地形分类用合成地形做真回归**（`height_scan.build_height_scan_from_terrain`
   精确造平面/台阶/斜坡/墙/起伏），逐类断言，并钉住符号约定
   （`value = base_z - terrain_z` ⇒ **上台阶的相邻差为负**）；
3. **去抖**：连续 N 帧同类才对外切换（抖动期保留上一稳定类）；
4. **切换动作层**：只降不升、策略不可用时**降级为限速并注明**（不静默当成功）、
   不可通行 ⇒ 安全停机。
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.height_scan import build_height_scan_from_terrain
from backend.perception_scene import SceneTerrainError, height_scan_at
from backend.perception_providers import (
    MANIFEST_PATH,
    PerceptionProviderError,
    provider_manifest,
    provider_selftest,
    provider_spec,
    resolve_provider,
    unregistered_provider_files,
)
from backend.perception_providers.terrain_classifier import (
    TerrainClassifier,
    classify_terrain,
    forward_corridor,
    terrain_metrics,
)
from backend.skill_switch import evaluate_terrain, plan_switch, scale_limits, switch_selftest

BASE_XY, BASE_Z = (0.5, 0.0), 0.45


def scan(terrain_fn) -> list[float]:
    return build_height_scan_from_terrain(terrain_fn, BASE_XY, BASE_Z, 0.0)


#: (名称, 地形函数, 期望类别) —— 用 height_scan 的合成地形精确构造
TERRAIN_CASES = [
    ("flat", lambda x, y: 0.0, "flat"),
    ("stair_up", lambda x, y: 0.15 if x > 1.0 else 0.0, "stair_up"),
    ("stair_down", lambda x, y: -0.15 if x > 1.0 else 0.0, "stair_down"),
    ("slope_up", lambda x, y: 0.25 * (x - 0.5), "slope_up"),
    ("slope_down", lambda x, y: -0.25 * (x - 0.5), "slope_down"),
    ("wall", lambda x, y: 0.45 if x > 1.0 else 0.0, "obstacle"),
    # 起伏：0.1 m 交替方波（窗口 0.2 m 内升高为 0 ⇒ 不算台阶，残差 std 0.035 > rough_std 0.03 ⇒ rough）
    ("undulating", lambda x, y: 0.07 * (round(x / 0.1) % 2), "rough"),
    # 陡坡：35% 坡度在 0.2 m 窗口内升高 0.07 m，但由坡度解释得掉 ⇒ 不许判成台阶
    ("slope_steep_up", lambda x, y: 0.35 * (x - 0.5), "slope_up"),
]


class ManifestTests(unittest.TestCase):
    def test_manifest_is_valid_and_resolvable(self):
        manifest = provider_manifest()
        self.assertEqual(manifest["schema"], "perception-provider-index-1.0")
        ids = [entry["provider_id"] for entry in manifest["providers"]]
        self.assertEqual(len(ids), len(set(ids)), "provider_id 不得重复")
        self.assertIn("terrain_classifier", ids)

    def test_unknown_provider_is_rejected_with_available_list(self):
        with self.assertRaises(PerceptionProviderError) as ctx:
            provider_spec("no_such_provider")
        self.assertIn("terrain_classifier", str(ctx.exception))

    def test_manifest_lie_about_module_is_caught(self):
        payload = provider_manifest()
        payload["providers"][0]["entry_point"] = "backend.perception_providers.not_a_module:Nope"
        lying = Path(tempfile.mkdtemp()) / "index.json"
        lying.write_text(json.dumps(payload), encoding="utf-8")
        with mock.patch("backend.perception_providers.MANIFEST_PATH", lying):
            with self.assertRaises(PerceptionProviderError) as ctx:
                provider_manifest()
        self.assertIn("模块不存在", str(ctx.exception))

    def test_missing_manifest_is_fail_closed(self):
        with mock.patch("backend.perception_providers.MANIFEST_PATH", Path("/nonexistent/index.json")):
            with self.assertRaises(PerceptionProviderError) as ctx:
                provider_manifest()
        self.assertIn("清单缺失", str(ctx.exception))

    def test_unregistered_file_is_diagnostic_only(self):
        self.assertEqual(unregistered_provider_files(), [], "仓库内不应有未登记的 provider 实现")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "stray_provider.py").write_text("# not registered\n", encoding="utf-8")
            with mock.patch("backend.perception_providers.PROVIDER_DIR", Path(tmp)):
                self.assertEqual(unregistered_provider_files(), ["stray_provider.py"])
                # 诊断归诊断：注册集合不受影响
                self.assertEqual([spec.provider_id for spec in [provider_spec("terrain_classifier")]],
                                 ["terrain_classifier"])

    def test_selftest_instantiates_every_provider(self):
        report = provider_selftest()
        self.assertEqual(report["verdict"], "pass", report)
        self.assertTrue(all(item["ok"] for item in report["providers"]))

    def test_manifest_path_ships_with_repo(self):
        self.assertTrue(MANIFEST_PATH.is_file(), "清单必须随仓库分发（运行时读取）")


class TerrainClassifierTests(unittest.TestCase):
    def setUp(self):
        self.provider = resolve_provider("terrain_classifier")

    def test_synthetic_terrains_classify_as_expected(self):
        for name, terrain, expected in TERRAIN_CASES:
            with self.subTest(case=name):
                reading = self.provider.update(scan(terrain), 0.0)
                self.assertEqual(reading["raw_class"], expected, reading["metrics"])
                self.assertEqual(reading["provider_id"], "terrain_classifier")
                self.assertEqual(reading["sensor"], "heightfield")
                self.assertGreaterEqual(reading["confidence"], 0.0)
                self.assertLessEqual(reading["confidence"], 1.0)

    def test_step_sign_convention(self):
        """`value = base_z - terrain_z` ⇒ 上台阶的相邻差为负（钉住符号，防回归）。"""
        up = self.provider.update(scan(TERRAIN_CASES[1][1]), 0.0)["metrics"]
        down = self.provider.update(scan(TERRAIN_CASES[2][1]), 0.0)["metrics"]
        self.assertLess(up["max_step_signed_m"], 0.0)
        self.assertTrue(up["step_is_uphill"])
        self.assertGreater(down["max_step_signed_m"], 0.0)
        self.assertFalse(down["step_is_uphill"])

    def test_actions_come_from_registry(self):
        stair = self.provider.update(scan(TERRAIN_CASES[1][1]), 0.0)
        wall = self.provider.update(scan(TERRAIN_CASES[5][1]), 0.0)
        flat = self.provider.update(scan(TERRAIN_CASES[0][1]), 0.0)
        self.assertEqual(stair["action"]["kind"], "policy_hint")
        self.assertEqual(stair["action"]["policy_hint"], "perceptive")
        self.assertEqual(wall["action"]["kind"], "stop")
        self.assertEqual(flat["action"]["vx_scale"], 1.0)

    def test_debounce_requires_consecutive_readings(self):
        expected_stable = [False, False, True, True]
        for index, stable in enumerate(expected_stable):
            with self.subTest(reading=index):
                reading = self.provider.update(scan(TERRAIN_CASES[1][1]), index * 0.02)
                self.assertEqual(reading["stable"], stable, reading)
        self.assertEqual(reading["candidate_count"], 4)

    def test_debounce_holds_previous_class_while_jittering(self):
        for index in range(3):
            self.provider.update(scan(TERRAIN_CASES[1][1]), index * 0.02)  # 稳定为 stair_up
        jittering = self.provider.update(scan(TERRAIN_CASES[0][1]), 1.0)
        self.assertFalse(jittering["stable"], "单帧异常不应立刻切换")
        self.assertEqual(jittering["raw_class"], "flat")
        self.assertEqual(jittering["terrain_class"], "stair_up", "抖动期保留上一稳定类")

    def test_on_reset_clears_state(self):
        self.provider.update(scan(TERRAIN_CASES[1][1]), 0.0)
        self.provider.on_reset()
        self.assertIsNone(self.provider.last_reading)
        fresh = self.provider.update(scan(TERRAIN_CASES[1][1]), 0.0)
        self.assertEqual(fresh["readings"], 1)
        self.assertFalse(fresh["stable"])

    def test_dict_input_is_accepted(self):
        reading = self.provider.update({"height_scan": scan(TERRAIN_CASES[0][1])}, 0.0)
        self.assertEqual(reading["raw_class"], "flat")

    def test_bad_scan_length_is_rejected(self):
        with self.assertRaises(ValueError):
            self.provider.update([0.0] * 10, 0.0)

    def test_missing_params_are_rejected(self):
        provider = TerrainClassifier()
        with self.assertRaises(ValueError) as ctx:
            provider.init({"step_min_m": 0.06})
        self.assertIn("actions", str(ctx.exception))

    def test_corridor_comes_from_params(self):
        params = provider_spec("terrain_classifier").params
        ix, iy = forward_corridor(params)
        self.assertTrue(ix and iy)
        with self.assertRaises(ValueError):
            forward_corridor({**params, "forward_min_m": 5.0, "forward_max_m": 6.0})

    def test_metrics_are_pure_function_of_scan(self):
        params = provider_spec("terrain_classifier").params
        once = terrain_metrics(scan(TERRAIN_CASES[3][1]), params)
        twice = terrain_metrics(scan(TERRAIN_CASES[3][1]), params)
        self.assertEqual(once, twice)

    def test_priority_rough_before_slope(self):
        """非平面地形应该报 rough：平面模型不成立时坡度不可信（顺序是有意的）。"""
        cls, _ = classify_terrain(
            {"max_step_m": 0.01, "step_is_uphill": False, "slope_deg": -16.0,
             "roughness_m": 0.09, "max_step_signed_m": 0.01, "forward_drop_m": 0.0, "gradient": -0.28},
            provider_spec("terrain_classifier").params,
        )
        self.assertEqual(cls, "rough")

    def test_registry_params_carry_provenance_and_pending_calibration(self):
        entry = provider_manifest()["providers"][0]
        self.assertEqual(entry.get("calibration"), "pending",
                         "阈值未标定前必须保持 pending，不许当验收判据用")
        self.assertTrue(entry["params"]["evidence"]["sources"], "参数必须带来源")


class SkillSwitchTests(unittest.TestCase):
    BASE = {"vx": 1.0, "vy": 0.5, "wz": 0.8}

    def test_limits_only_decrease(self):
        scaled = scale_limits(self.BASE, {"vx_scale": 0.5})
        self.assertEqual(scaled, {"vx": 0.5, "vy": 0.25, "wz": 0.4})
        self.assertEqual(scale_limits(self.BASE, {"vx_scale": 3.0}), self.BASE, "不许放大权限")
        with self.assertRaises(ValueError):
            scale_limits(self.BASE, {"vx_scale": -1.0})

    def test_policy_switch_when_available(self):
        decision = plan_switch({"kind": "policy_hint", "policy_hint": "perceptive", "vx_scale": 0.5},
                               base_limits=self.BASE, available_policies=["perceptive"])
        self.assertEqual(decision["kind"], "policy")
        self.assertEqual(decision["policy_id"], "perceptive")
        self.assertIn("重置", decision["note"], "必须写明离散切换的代价")

    def test_policy_missing_degrades_to_limits_and_says_so(self):
        decision = plan_switch({"kind": "policy_hint", "policy_hint": "perceptive", "vx_scale": 0.5},
                               base_limits=self.BASE, available_policies=["velocity"])
        self.assertEqual(decision["kind"], "limits")
        self.assertEqual(decision["degraded_from"], "policy_hint")
        self.assertIn("降级", decision["note"])
        self.assertIsNone(decision["policy_id"])

    def test_stop_zeroes_everything(self):
        decision = plan_switch({"kind": "stop"}, base_limits=self.BASE)
        self.assertEqual(decision["kind"], "stop")
        self.assertEqual(decision["new_limits"], {"vx": 0.0, "vy": 0.0, "wz": 0.0})

    def test_no_action_is_no_change(self):
        decision = plan_switch(None, base_limits=self.BASE)
        self.assertEqual(decision["kind"], "none")
        self.assertFalse(decision["changed"])

    def test_evaluate_terrain_end_to_end(self):
        flat = evaluate_terrain(scan(TERRAIN_CASES[0][1]), base_limits=self.BASE,
                                available_policies=["perceptive"], provider=resolve_provider("terrain_classifier"))
        self.assertEqual(flat["reading"]["raw_class"], "flat")
        self.assertFalse(flat["switch"]["changed"], "平地不该改上限")
        stair = evaluate_terrain(scan(TERRAIN_CASES[1][1]), base_limits=self.BASE,
                                 available_policies=["perceptive"], provider=resolve_provider("terrain_classifier"))
        self.assertEqual(stair["switch"]["kind"], "policy")
        self.assertEqual(stair["switch"]["new_limits"]["vx"], 0.5)

    def test_switch_selftest(self):
        self.assertEqual(switch_selftest()["verdict"], "pass")


class SceneTerrainTests(unittest.TestCase):
    """同源地形路线：场景 → 高度场（用真实生成器，不是合成函数）。"""

    def _make_scene(self, tmp: Path, name: str, kind: str, *, rows: int = 128, obstacle_count=None):
        (tmp / name).mkdir(parents=True, exist_ok=True)
        manifest = {"scene_id": name, "terrain_kind": kind, "seed": 0, "rows": rows, "cols": rows}
        if obstacle_count is not None:
            manifest["obstacle_count"] = obstacle_count
        (tmp / name / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_builtin_flat_scene(self):
        scan, meta = height_scan_at("flat", [0.0, 0.0], base_z=0.45)
        self.assertEqual(len(scan), 187)
        self.assertEqual(meta["kind"], "flat")
        self.assertEqual(meta["reproducible"], "full")

    def test_generated_stairs_scene_detects_stairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenes = Path(tmp)
            self._make_scene(scenes, "stairs_probe", "stairs", obstacle_count=0)
            provider = resolve_provider("terrain_classifier")
            classes = set()
            for y in (-1.4, -1.0, -0.6, -0.2, 0.2, 0.6, 1.0, 1.4):
                scan, meta = height_scan_at("stairs_probe", [0.0, y], base_z=0.45,
                                            base_yaw=math.pi / 2, scenes_dir=scenes)
                self.assertEqual(len(scan), 187)
                self.assertEqual(meta["reproducible"], "full")
                classes.add(provider.update(scan, 0.0)["raw_class"])
            self.assertIn("stair_up", classes, f"真实楼梯场景必须能识别出台阶（得到 {sorted(classes)}）")
            self.assertNotIn("obstacle", classes, "0.114 m 立板不该被判成不可通行")

    def test_manifest_without_obstacle_count_is_marked_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenes = Path(tmp)
            self._make_scene(scenes, "stairs_noparam", "stairs")
            _, meta = height_scan_at("stairs_noparam", [0.0, 0.0], base_z=0.45, scenes_dir=scenes)
            self.assertEqual(meta["reproducible"], "partial")
            self.assertIn("obstacle_count", meta["note"])

    def test_unknown_scene_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SceneTerrainError) as ctx:
                height_scan_at("no_such_scene", [0.0, 0.0], base_z=0.45, scenes_dir=Path(tmp))
            self.assertIn("平", str(ctx.exception), "错误信息必须说明不按平地处理")

    def test_manifest_missing_keys_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenes = Path(tmp)
            (scenes / "broken").mkdir()
            (scenes / "broken" / "manifest.json").write_text(json.dumps({"scene_id": "broken"}), encoding="utf-8")
            with self.assertRaises(SceneTerrainError) as ctx:
                height_scan_at("broken", [0.0, 0.0], base_z=0.45, scenes_dir=scenes)
            self.assertIn("terrain_kind", str(ctx.exception))


class PerceptionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_providers_endpoint(self):
        response = self.client.get("/api/perception/providers")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        self.assertIn("terrain_classifier", [item["provider_id"] for item in payload["providers"]])
        self.assertEqual(payload["selftest"]["verdict"], "pass")

    def test_flat_scene_needs_no_switch(self):
        response = self.client.post("/api/perception/terrain/evaluate", json={"scene_id": "flat"})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["reading"]["raw_class"], "flat")
        self.assertEqual(payload["switch"]["kind"], "limits")
        self.assertFalse(payload["switch"]["changed"], "平地不该改上限")
        self.assertEqual(payload["height_scan_points"], 187)
        self.assertIn("不是机载", payload["note"])

    def test_unknown_scene_returns_400(self):
        response = self.client.post("/api/perception/terrain/evaluate", json={"scene_id": "nope"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("平", response.json()["detail"])

    def test_stairs_scene_switches_policy_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenes = Path(tmp)
            (scenes / "stairs_api").mkdir()
            (scenes / "stairs_api" / "manifest.json").write_text(json.dumps(
                {"scene_id": "stairs_api", "terrain_kind": "stairs", "seed": 0, "rows": 128,
                 "cols": 128, "obstacle_count": 0}), encoding="utf-8")
            with mock.patch("backend.perception_scene.DEFAULT_SCENES_DIR", scenes):
                with_policy = self.client.post("/api/perception/terrain/evaluate", json={
                    "scene_id": "stairs_api", "base_xy": [0.0, -1.4], "base_yaw": math.pi / 2,
                    "base_limits": {"vx": 1.0, "vy": 0.5, "wz": 0.8},
                    "available_policies": ["perceptive"],
                })
                without = self.client.post("/api/perception/terrain/evaluate", json={
                    "scene_id": "stairs_api", "base_xy": [0.0, -1.4], "base_yaw": math.pi / 2,
                    "base_limits": {"vx": 1.0, "vy": 0.5, "wz": 0.8},
                    "available_policies": ["velocity"],
                })
        self.assertEqual(with_policy.status_code, 200, with_policy.text)
        self.assertEqual(with_policy.json()["reading"]["raw_class"], "stair_up")
        self.assertEqual(with_policy.json()["switch"]["kind"], "policy")
        self.assertEqual(with_policy.json()["switch"]["new_limits"]["vx"], 0.5)
        self.assertEqual(without.json()["switch"]["kind"], "limits")
        self.assertEqual(without.json()["switch"]["degraded_from"], "policy_hint")

    def test_unknown_provider_returns_400(self):
        response = self.client.post("/api/perception/terrain/evaluate",
                                    json={"scene_id": "flat", "provider_id": "nope"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
