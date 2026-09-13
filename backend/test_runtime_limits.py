"""H8 / H9 / H10 的回归测试。

三件事各自的核心断言：

* **H8** 相机真机口径与畸变：档位注册表完整、两种畸变模型的数学正确、同一 K 下
  「畸变开-关」的像素位移可量化，且投影路径能消费档位带上的畸变系数；
* **H9** 运动指令档位数据化：裁剪会报告被裁了什么、死区置零、非有限值拒绝、
  `teleop` 与 `nav` 档位确实不同、加减速分开；
* **H10** 到达判据单一真值：导航默认值与相机投影判定都取自注册表，显式传旧值
  （0.35 / 0.3）会被标注 `deviation`，视觉停靠三项容差与丢帧判定正确。
"""

import json
import math
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.arrival_criteria import (
    arrival_criteria,
    arrival_selftest,
    effective_thresholds,
    visual_dock_arrival,
    visual_dock_spec,
    waypoint_arrival,
    waypoint_spec,
)
from backend.camera_projection import (
    arrival_verdict,
    camera_profile,
    camera_profile_intrinsics,
    camera_profiles,
    camera_projection_selftest,
    distort_normalized,
    distortion_impact,
    project_optical_points,
    resolve_intrinsics,
)
from backend.motion_commands import (
    clamp_command,
    motion_command_profiles,
    motion_command_selftest,
    resolve_command,
    slew_limit,
)
from backend.runtime_registry import RegistryError, load_registry, registry_snapshot

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_three_registries_load_with_expected_schema(self):
        expected = {
            "cameras": "camera-profile-1.0",
            "motion_commands": "motion-command-profile-1.0",
            "arrival_criteria": "arrival-criteria-1.0",
        }
        for name, schema in expected.items():
            with self.subTest(registry=name):
                self.assertEqual(load_registry(name)["schema"], schema)

    def test_unknown_registry_is_rejected(self):
        with self.assertRaises(RegistryError):
            load_registry("not_a_registry")

    def test_snapshot_reports_all_three(self):
        snapshot = registry_snapshot()
        self.assertEqual(set(snapshot["registries"]), {"cameras", "motion_commands", "arrival_criteria"})
        self.assertTrue(all(entry["ok"] for entry in snapshot["registries"].values()))

    def test_runtime_data_dirs_ship_with_the_app(self):
        """registry/ 与 packs/ 是运行时读取的，必须随发行物一起走。

        漏带不会在开发态暴露（源码树里文件都在），只在打包后表现为"接口空表/500"，
        所以用一条静态断言把它钉住。
        """
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        shipped = {entry.get("from") for entry in package["build"]["extraResources"]}
        for required in ("registry", "packs"):
            self.assertIn(required, shipped, f"electron extraResources 缺 {required}/")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for required in ('"registry" = "registry"', '"packs" = "packs"'):
            self.assertIn(required, pyproject, "wheel force-include 缺运行时数据目录")


class CameraProfileTests(unittest.TestCase):
    def test_profiles_are_self_describing_with_evidence(self):
        profiles = camera_profiles()
        self.assertGreaterEqual(len(profiles), 4)
        ids = [profile["id"] for profile in profiles]
        self.assertEqual(len(ids), len(set(ids)), "档位 id 必须唯一")
        for profile in profiles:
            with self.subTest(profile=profile["id"]):
                self.assertTrue(profile.get("label"))
                self.assertIn(profile.get("model"), {"pinhole", "brown_conrady", "fisheye_equidistant"})
                resolution = profile.get("resolution") or {}
                self.assertGreaterEqual(int(resolution.get("width") or 0), 2)
                self.assertGreaterEqual(int(resolution.get("height") or 0), 2)
                evidence = profile.get("evidence") or {}
                self.assertTrue(evidence.get("source"), "每个档位必须带 evidence.source，不允许猜数")

    def test_go2_fisheye_matches_upstream_calibration(self):
        profile = camera_profile("go2-front-fisheye-1920x1080")
        resolved = camera_profile_intrinsics(profile)
        self.assertAlmostEqual(resolved["fx"], 1248.95099, places=5)
        self.assertAlmostEqual(resolved["fy"], 1247.94633, places=5)
        self.assertAlmostEqual(resolved["cx"], 957.862066, places=5)
        self.assertAlmostEqual(resolved["cy"], 530.821641, places=5)
        self.assertEqual(resolved["distortion_model"], "fisheye_equidistant")
        self.assertEqual(len(resolved["distortion"]), 4)

    def test_ideal_pinhole_profile_is_distortion_free(self):
        impact = distortion_impact("ideal-pinhole-1920x1080")
        self.assertEqual(impact["max_delta_px"], 0.0)
        self.assertFalse(impact["distortion_matters"])

    def test_real_fisheye_distortion_is_material(self):
        impact = distortion_impact("go2-front-fisheye-1920x1080")
        self.assertTrue(impact["distortion_matters"])
        self.assertGreater(impact["max_delta_px"], 1.0)
        # 尺寸检查：位移应远小于画面尺寸（否则说明模型或系数写反了）
        self.assertLess(impact["max_delta_px"], impact["resolution"]["width"] * 0.5)
        self.assertLessEqual(impact["mean_delta_px"], impact["max_delta_px"])

    def test_brown_conrady_formula(self):
        xd, yd = distort_normalized(0.2, 0.1, model="brown_conrady", coefficients=[0.1, 0.0, 0.0, 0.0, 0.0])
        radial = 1.0 + 0.1 * (0.2**2 + 0.1**2)
        self.assertAlmostEqual(xd, 0.2 * radial, places=12)
        self.assertAlmostEqual(yd, 0.1 * radial, places=12)

    def test_brown_conrady_tangential_terms(self):
        # 只有 p1 时，x 方向应出现 2·p1·x·y 的切向项
        xd, _yd = distort_normalized(0.1, 0.2, model="brown_conrady", coefficients=[0.0, 0.0, 0.5, 0.0, 0.0])
        self.assertAlmostEqual(xd, 0.1 + 2.0 * 0.5 * 0.1 * 0.2, places=12)

    def test_fisheye_equidistant_formula(self):
        xd, yd = distort_normalized(0.3, 0.4, model="fisheye_equidistant", coefficients=[0.05, 0.0, 0.0, 0.0])
        self.assertAlmostEqual(xd, 0.281179, places=6)
        self.assertAlmostEqual(yd, 0.374905, places=6)

    def test_zero_coefficients_are_identity_for_both_models(self):
        for model, coeffs in (("brown_conrady", [0.0] * 5), ("fisheye_equidistant", [0.0] * 4)):
            with self.subTest(model=model):
                self.assertEqual(distort_normalized(0.3, -0.2, model=model, coefficients=coeffs), (0.3, -0.2))

    def test_unknown_distortion_model_rejected(self):
        with self.assertRaises(ValueError):
            distort_normalized(0.1, 0.1, model="tilt_shift", coefficients=[0.1])

    def test_projection_consumes_distortion_from_intrinsics(self):
        profile = camera_profile("go2-front-fisheye-1920x1080")
        lens = camera_profile_intrinsics(profile)
        pinned = {**lens, "distortion_model": "pinhole", "distortion": []}
        point = [(1.0, 0.6, 1.5)]  # 偏离光轴，畸变影响应可见
        real = project_optical_points(point, lens)[0]
        ideal = project_optical_points(point, pinned)[0]
        self.assertTrue(real["valid"] and ideal["valid"])
        self.assertGreater(math.hypot(real["u"] - ideal["u"], real["v"] - ideal["v"]), 1.0)

    def test_projection_defaults_to_pinhole_without_distortion(self):
        intrinsics = resolve_intrinsics(640, 480, fov_deg=90.0)
        point = [(2.0, 1.0, 3.0)]
        plain = project_optical_points(point, intrinsics)[0]
        explicit = project_optical_points(point, intrinsics, distortion_model="pinhole", distortion_coefficients=[]) [0]
        self.assertEqual(plain, explicit)

    def test_camera_selftest_passes(self):
        result = camera_projection_selftest()
        self.assertEqual(result["verdict"], "pass", result["failures"])


class MotionCommandTests(unittest.TestCase):
    def test_profiles_are_data_driven(self):
        profiles = motion_command_profiles()
        self.assertEqual(set(profiles), {"teleop", "nav"})
        self.assertNotEqual(profiles["teleop"]["limits"], profiles["nav"]["limits"])

    def test_over_limit_is_clipped_and_explained(self):
        result = clamp_command({"vx": 5.0, "vy": -3.0, "yaw_rate": 3.0}, profile="teleop")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["command"], {"vx": 1.0, "vy": -1.0, "yaw_rate": 1.0})
        self.assertEqual({item["axis"] for item in result["clipped"]}, {"vx", "vy", "yaw_rate"})
        self.assertTrue(any("超限" in reason for reason in result["reasons"]))

    def test_nav_profile_tighter_than_teleop(self):
        nav = clamp_command({"vx": 5.0, "vy": 5.0, "yaw_rate": 5.0}, profile="nav")
        self.assertEqual(nav["command"], {"vx": 0.9, "vy": 0.5, "yaw_rate": 0.85})

    def test_below_deadzone_is_zeroed(self):
        result = clamp_command({"vx": 0.1}, profile="teleop")
        self.assertEqual(result["command"]["vx"], 0.0)
        self.assertTrue(any("死区" in reason for reason in result["reasons"]))

    def test_non_finite_is_rejected_not_clamped(self):
        result = clamp_command({"vx": float("nan")}, profile="teleop")
        self.assertFalse(result["accepted"])
        self.assertIsNone(result["command"])
        self.assertTrue(any("非有限" in reason for reason in result["reasons"]))

    def test_slew_uses_separate_accel_and_decel(self):
        accelerating = slew_limit({"vx": 0.0}, {"vx": 1.0}, dt=0.1, profile="teleop")
        decelerating = slew_limit({"vx": 1.0}, {"vx": 0.0}, dt=0.1, profile="teleop")
        self.assertAlmostEqual(accelerating["command"]["vx"], 0.1, places=9)
        self.assertAlmostEqual(decelerating["command"]["vx"], 0.8, places=9)

    def test_resolve_runs_full_chain(self):
        result = resolve_command({"vx": 9.0}, previous={"vx": 0.0}, dt=0.1, profile="teleop")
        self.assertTrue(result["accepted"])
        self.assertAlmostEqual(result["command"]["vx"], 0.1, places=9)
        self.assertTrue(result["clipped"] and result["rate_limited"])

    def test_motion_selftest_passes(self):
        result = motion_command_selftest()
        self.assertEqual(result["verdict"], "pass", result["failures"])


class ArrivalCriteriaTests(unittest.TestCase):
    def test_navigation_default_comes_from_registry(self):
        from backend.navigation_api import WAYPOINT_TOLERANCE_M

        self.assertEqual(WAYPOINT_TOLERANCE_M, float(waypoint_spec()["tolerance_m"]))

    def test_waypoint_arrival_requires_position_heading_and_stability(self):
        spec = waypoint_spec()
        ticks = int(spec["stable_ticks"])
        self.assertTrue(waypoint_arrival((0.0, 0.0), (0.1, 0.0), consecutive_ticks=ticks)["arrived"])
        self.assertFalse(waypoint_arrival((0.0, 0.0), (1.0, 0.0), consecutive_ticks=ticks)["arrived"])
        self.assertFalse(waypoint_arrival((0.0, 0.0), (0.1, 0.0), consecutive_ticks=0)["arrived"])
        turned = waypoint_arrival(
            (0.0, 0.0), (0.1, 0.0), heading_rad=1.0, target_heading_rad=0.0, consecutive_ticks=ticks
        )
        self.assertFalse(turned["arrived"])

    def test_legacy_tolerances_are_flagged_not_silently_accepted(self):
        ticks = int(waypoint_spec()["stable_ticks"])
        for legacy in (0.35, 0.3):
            with self.subTest(legacy=legacy):
                verdict = waypoint_arrival((0.0, 0.0), (0.1, 0.0), consecutive_ticks=ticks, tolerance_m=legacy)
                self.assertTrue(verdict["deviation"], "旧值必须被标注偏离单一真值")
                self.assertEqual(verdict["deviation"][0]["canonical"], float(waypoint_spec()["tolerance_m"]))

    def test_camera_arrival_verdict_uses_single_source(self):
        verdict = arrival_verdict((0.0, 0.0), (0.1, 0.0))
        self.assertTrue(verdict["arrived"])
        self.assertEqual(verdict["tolerance_m"], float(waypoint_spec()["tolerance_m"]))
        self.assertEqual(verdict["source"], "registry/arrival_criteria.json::waypoint")
        self.assertEqual(verdict["deviation"], [])
        # 旧默认 0.3 现在只会作为「被标注的偏离」出现
        legacy = arrival_verdict((0.0, 0.0), (0.1, 0.0), tolerance_m=0.3)
        self.assertTrue(legacy["deviation"])

    def test_visual_dock_tolerances_and_lost_frames(self):
        spec = visual_dock_spec()
        self.assertTrue(visual_dock_arrival(lateral_m=0.01, forward_m=0.02, yaw_error_rad=0.01)["docked"])
        self.assertFalse(visual_dock_arrival(lateral_m=0.10, forward_m=0.0, yaw_error_rad=0.0)["docked"])
        short_loss = visual_dock_arrival(
            lateral_m=0.0, forward_m=0.0, yaw_error_rad=0.0, lost_frame_s=float(spec["lose_frame_s"]) + 0.1
        )
        self.assertTrue(short_loss["docked"], "短暂丢失不应判定失败")
        self.assertTrue(any("短暂丢失" in reason for reason in short_loss["reasons"]))
        confirmed = visual_dock_arrival(
            lateral_m=0.0, forward_m=0.0, yaw_error_rad=0.0, lost_frame_s=float(spec["lose_confirm_s"]) + 0.1
        )
        self.assertTrue(confirmed["lost"])
        self.assertFalse(confirmed["docked"])

    def test_effective_thresholds_point_at_the_registry(self):
        thresholds = effective_thresholds()
        self.assertEqual(thresholds["source"], "registry/arrival_criteria.json")
        self.assertEqual(thresholds["schema"], arrival_criteria()["schema"])

    def test_arrival_selftest_passes(self):
        result = arrival_selftest()
        self.assertEqual(result["verdict"], "pass", result["failures"])


class LimitsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_motion_profiles_endpoint(self):
        payload = self.client.get("/api/limits/motion").json()
        self.assertTrue(payload["success"])
        self.assertEqual(set(payload["profiles"]), {"teleop", "nav"})

    def test_clamp_endpoint_reports_clipping(self):
        payload = self.client.post("/api/limits/motion/clamp", json={"command": {"vx": 9.0}}).json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["command"]["vx"], 1.0)
        self.assertTrue(payload["clipped"])

    def test_clamp_endpoint_rejects_non_finite_without_5xx(self):
        response = self.client.post("/api/limits/motion/clamp", json={"command": {"vx": "nan"}})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])

    def test_arrival_endpoints(self):
        thresholds = self.client.get("/api/limits/arrival").json()
        self.assertEqual(thresholds["waypoint"]["tolerance_m"], float(waypoint_spec()["tolerance_m"]))
        waypoint = self.client.post(
            "/api/limits/arrival/waypoint",
            json={"position_xy": [0.0, 0.0], "target_xy": [0.1, 0.0], "consecutive_ticks": int(waypoint_spec()["stable_ticks"])},
        ).json()
        self.assertTrue(waypoint["verdict"]["arrived"])
        dock = self.client.post(
            "/api/limits/arrival/visual-dock",
            json={"lateral_m": 0.0, "forward_m": 0.0, "yaw_error_rad": 0.0},
        ).json()
        self.assertTrue(dock["verdict"]["docked"])

    def test_limits_selftest_endpoint(self):
        payload = self.client.get("/api/limits/selftest").json()
        self.assertEqual(payload["verdict"], "pass", payload["verdicts"])

    def test_registry_endpoint_lists_ids(self):
        payload = self.client.get("/api/limits/registry").json()
        self.assertTrue(payload["success"])
        self.assertIn("go2-front-fisheye-1920x1080", payload["registries"]["cameras"]["ids"])


if __name__ == "__main__":
    unittest.main()
