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

from backend.height_scan import build_height_scan_from_terrain
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
    ("undulating", lambda x, y: 0.05 * math.sin(8.0 * x), "rough"),
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


if __name__ == "__main__":
    unittest.main()
