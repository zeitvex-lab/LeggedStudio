"""B3 收尾回归：物理事实只在一处（契约真值），且两条消费链同源。

**这条测试守的是什么**（B3 的验收口径「物理事实只在一处；`simulation/config.json`
降级为引用」）：

1. `assets/robots/*/simulation/config.json` **不得**再出现那组物理键
   （stiffness/damping/torque_limits/armature/frictionloss/control_hz/physics_hz/
   decimation）——否则"两处并存"回潮；
2. 14/14 包的 `contract.json` 必须给**每个执行器角色**声明 armature
   （lite3 / m20 / zex-w 此前三包全缺，训练与浏览器都没有转子惯量）；
3. `contracts.physics_binding.joint_constant_tables()` 的键**统一小写**，
   大小写不敏感查表必须命中——这是修掉的静默失效：训练/验收侧用
   `joint.name.lower()` 查混合大小写键（`FL_hip_joint`）永远查不中，
   armature 静默不生效，而浏览器侧同一份数据是生效的；
4. 训练侧（scene_builder / policy_acceptance）与浏览器侧（simulation_api 载荷）
   取的**是同一份事实**（`physics_facts` → source=contract_truth）。
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.package_records import package_contract_views
from contracts.physics_binding import (
    LEGACY_CONFIG_PHYSICS_KEYS,
    apply_t_n_curves,
    apply_actuator_gains,
    dc_actuator_settings,
    dc_params_from_t_n_curve,
    t_n_curve_facts,
    format_tn_curve_text,
    joint_constant_tables,
    parse_tn_curve_text,
    payload_physics_view,
    payload_t_n_curve_view,
    physics_facts,
    physics_scalars,
)

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"


def package_dirs() -> list[Path]:
    return sorted(p for p in ROBOTS.iterdir() if p.is_dir())


class ConfigNoLongerHoldsPhysicsTests(unittest.TestCase):
    def test_simulation_config_has_no_legacy_physics_keys(self):
        offenders: dict[str, list[str]] = {}
        for package in package_dirs():
            config_path = package / "simulation" / "config.json"
            if not config_path.is_file():
                continue
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            hit = [key for key in LEGACY_CONFIG_PHYSICS_KEYS if key in config]
            if hit:
                offenders[package.name] = hit
        self.assertEqual(offenders, {}, f"simulation/config.json 又出现物理键：{offenders}")

    def test_save_chain_strips_legacy_keys_before_persisting(self):
        """保存链必须剔除这组键，否则前端一保存就把重复写回来。"""
        source = (ROOT / "backend" / "api_complete.py").read_text(encoding="utf-8")
        self.assertIn("LEGACY_CONFIG_PHYSICS_KEYS", source)
        self.assertIn("persisted_simulation", source)


class ContractCarriesPhysicsTests(unittest.TestCase):
    def test_every_package_declares_armature_for_every_role(self):
        missing: dict[str, list[str]] = {}
        for package in package_dirs():
            contract_path = package / "contract.json"
            if not contract_path.is_file():
                continue
            contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
            by_role = (contract.get("actuator_profile") or {}).get("by_role") or {}
            gaps = [role for role, params in by_role.items() if not isinstance(params, dict) or params.get("armature") is None]
            if gaps:
                missing[package.name] = gaps
        self.assertEqual(missing, {}, f"契约真值 缺 armature 的角色：{missing}")

    def test_physics_facts_come_from_contract_for_all_packages(self):
        for package in package_dirs():
            with self.subTest(package=package.name):
                facts = physics_facts(package)
                self.assertEqual(facts["source"], "contract")
                self.assertFalse(facts.get("needs_migration"))

    def test_scalars_expose_control_layer_from_contract(self):
        """去掉 sim config 顶层键之后，控制层标量必须仍来自契约（不能静默回落默认值）。"""
        for package in package_dirs():
            with self.subTest(package=package.name):
                scalars = physics_scalars(package)
                contract = json.loads((package / "contract.json").read_text(encoding="utf-8-sig"))
                control = contract.get("control") or {}
                if control.get("physics_hz") is not None:
                    self.assertEqual(scalars["physics_hz"], control["physics_hz"])
                if control.get("decimation") is not None:
                    self.assertEqual(scalars["decimation"], control["decimation"])


class CaseInsensitiveLookupTests(unittest.TestCase):
    """修掉的静默失效：小写查表必须命中混合大小写的契约键。"""

    def test_tables_are_lower_cased_and_lookupable(self):
        tables = joint_constant_tables(ROBOTS / "unitree_go2")
        self.assertTrue(tables["armature"], "go2 契约应含 armature")
        self.assertTrue(all(key == key.lower() for key in tables["armature"]))
        self.assertIn("fl_hip_joint", tables["armature"])
        self.assertAlmostEqual(tables["armature"]["fl_hip_joint"], 0.01, places=9)

    def test_lite3_m20_zexw_now_have_armature(self):
        expected = {
            "deeprobotics_lite3": 0.01,
            "deeprobotics_m20": 0.01,
            "zex-w": 0.0042,
        }
        for robot_id, value in expected.items():
            with self.subTest(robot=robot_id):
                tables = joint_constant_tables(ROBOTS / robot_id)
                self.assertTrue(tables["armature"], f"{robot_id} 仍无 armature")
                for joint, actual in tables["armature"].items():
                    if joint == "__default__":
                        continue
                    self.assertAlmostEqual(actual, value, places=9)
                # 用 MJCF 里的真实关节名（大写前缀）小写化后必须命中
                self.assertTrue(any(joint.startswith("fl_") for joint in tables["armature"]))

    def test_training_and_browser_share_one_source(self):
        """训练侧（joint_constant_tables）与浏览器载荷（payload_physics_view）同源同值。"""
        for package in package_dirs():
            with self.subTest(package=package.name):
                facts = physics_facts(package)
                tables = joint_constant_tables(package)
                payload = payload_physics_view(facts)
                for joint, value in (facts["by_joint"].get("armature") or {}).items():
                    if value is None:
                        continue
                    self.assertIn(str(joint).lower(), tables["armature"])
                    self.assertAlmostEqual(float(payload["armature"][joint]), float(value), places=9)
                    self.assertAlmostEqual(tables["armature"][str(joint).lower()], float(value), places=9)


class ActuatorGainMappingTests(unittest.TestCase):
    """D8：面板编辑 → 契约真值 的唯一映射实现（`apply_actuator_gains`）。"""

    @staticmethod
    def _v3() -> dict:
        return {
            "joints": {
                "actuated": [
                    {"name": "FL_hip_joint", "role": "hip"},
                    {"name": "FR_hip_joint", "role": "hip"},
                    {"name": "FL_calf_joint", "role": "calf"},
                    {"name": "FR_calf_joint", "role": "calf"},
                ]
            },
            "actuator_profile": {"by_role": {}, "by_joint": {}},
        }

    def test_role_uniform_values_go_to_by_role(self):
        v3 = self._v3()
        written = apply_actuator_gains(
            v3,
            {"armature": {"FL_hip_joint": 0.01, "FR_hip_joint": 0.01,
                          "FL_calf_joint": 0.02, "FR_calf_joint": 0.02}},
        )
        profile = v3["actuator_profile"]
        self.assertIn("armature", written)
        self.assertEqual(profile["by_role"]["hip"]["armature"], 0.01)
        self.assertEqual(profile["by_role"]["calf"]["armature"], 0.02)
        self.assertEqual(profile["by_joint"], {}, "角色内全同不应留下逐关节覆盖")

    def test_heterogeneous_values_fall_back_to_by_joint(self):
        v3 = self._v3()
        apply_actuator_gains(
            v3,
            {"armature": {"FL_hip_joint": 0.01, "FR_hip_joint": 0.03}},
        )
        by_joint = v3["actuator_profile"]["by_joint"]
        self.assertEqual(by_joint["FL_hip_joint"]["armature"], 0.01)
        self.assertEqual(by_joint["FR_hip_joint"]["armature"], 0.03)
        self.assertNotIn("hip", v3["actuator_profile"]["by_role"])

    def test_armature_and_friction_loss_are_first_class(self):
        """D8 的核心：两者与 stiffness/damping/effort 走同一张映射表、同一归层规则。"""
        v3 = self._v3()
        written = apply_actuator_gains(
            v3,
            {
                "stiffness": {"FL_hip_joint": 20.0, "FR_hip_joint": 20.0},
                "torque_limits": {"FL_hip_joint": 23.7, "FR_hip_joint": 23.7},
                "armature": {"FL_hip_joint": 0.01, "FR_hip_joint": 0.01},
                "friction_loss": {"FL_hip_joint": 0.2, "FR_hip_joint": 0.2},
            },
        )
        # 返回的是**契约真值 的键名**（力矩限幅在 v3 里叫 effort）
        self.assertEqual(written, ["armature", "effort", "friction_loss", "stiffness"])
        hip = v3["actuator_profile"]["by_role"]["hip"]
        self.assertEqual(hip["effort"], 23.7)
        self.assertEqual(hip["armature"], 0.01)
        self.assertEqual(hip["friction_loss"], 0.2)

    def test_by_role_write_clears_stale_by_joint_override(self):
        v3 = self._v3()
        v3["actuator_profile"]["by_joint"] = {"FL_hip_joint": {"armature": 9.9}}
        apply_actuator_gains(v3, {"armature": {"FL_hip_joint": 0.01, "FR_hip_joint": 0.01}})
        self.assertEqual(v3["actuator_profile"]["by_role"]["hip"]["armature"], 0.01)
        self.assertNotIn("armature", v3["actuator_profile"]["by_joint"]["FL_hip_joint"])

    def test_empty_or_malformed_control_is_a_noop(self):
        v3 = self._v3()
        for payload in ({}, None, {"armature": "nope"}, {"unknown_key": {"a": 1}}):
            with self.subTest(payload=payload):
                self.assertEqual(apply_actuator_gains(v3, payload), [])
        self.assertEqual(v3["actuator_profile"], {"by_role": {}, "by_joint": {}})


class WorkbenchPhysicsViewTests(unittest.TestCase):
    """D8：工作台电机面板的数据源 = 契约真值 物理视图（与浏览器同源同形状）。"""

    def test_physics_view_covers_all_packages(self):
        for package in package_dirs():
            with self.subTest(package=package.name):
                view = package_contract_views(package)["physics"]
                self.assertEqual(view.get("source"), "contract")
                for key in ("stiffness", "damping", "torque_limits", "armature", "frictionloss"):
                    self.assertIn(key, view, f"{package.name} 缺 {key}")
                self.assertTrue(view["armature"], f"{package.name} 的 armature 为空，面板将显示空白")

    def test_physics_view_matches_binding_payload(self):
        """同一包、同一事实：record.physics 与 simulation_api 浏览器载荷必须一致。"""
        for package in package_dirs():
            with self.subTest(package=package.name):
                expected = payload_physics_view(physics_facts(package))
                actual = package_contract_views(package)["physics"]
                for key in ("stiffness", "damping", "torque_limits", "armature", "frictionloss"):
                    self.assertEqual(actual[key], expected[key], f"{package.name} 的 {key} 与浏览器载荷不一致")

    def test_missing_contract_marks_source_missing(self):
        """无契约的目录显式标 ``source=missing``（面板据此提示"未声明"），不是静默空值。"""
        with tempfile.TemporaryDirectory() as tmp:
            view = package_contract_views(Path(tmp))["physics"]
            self.assertEqual(view.get("source"), "missing")
            self.assertTrue(view.get("needs_migration"))
            self.assertEqual(view["armature"], {})


class ControlConsistencyTests(unittest.TestCase):
    """P2：契约真值 的控制三件套必须自洽——decimation 是派生量（physics_hz / control_hz）。

    这条一旦不成立，策略频率、观测频率、验收时长全部按错的数走，而且不会报错。
    """

    def test_v3_control_rates_are_self_consistent(self):
        checked = 0
        for package in package_dirs():
            contract_truth = json.loads((package / "contract.json").read_text(encoding="utf-8-sig"))
            control = contract_truth.get("control") or {}
            hz, physics_hz, decimation = (
                control.get("control_hz"), control.get("physics_hz"), control.get("decimation")
            )
            if not all(isinstance(value, int) for value in (hz, physics_hz, decimation)):
                continue
            checked += 1
            with self.subTest(package=package.name):
                self.assertLessEqual(
                    abs(physics_hz - hz * decimation), 1,
                    f"{package.name}: physics_hz={physics_hz} 与 control_hz×decimation={hz * decimation} 不自洽",
                )
        self.assertGreater(checked, 10, "自洽性检查覆盖的包太少，检查是否失效")


class TnCurveTests(unittest.TestCase):
    """P1：T-N 曲线。核心不变量是「**声明 ≠ 生效**」——缺省 ideal_pd 下必须什么都不做。"""

    def test_parse_format_round_trip(self):
        text = "0:120, 95:120, 192:0"
        self.assertEqual(format_tn_curve_text(parse_tn_curve_text(text)), text)
        self.assertEqual(parse_tn_curve_text(""), [])
        self.assertEqual(parse_tn_curve_text("  "), [])

    def test_parse_accepts_semicolon_and_rejects_junk(self):
        self.assertEqual(len(parse_tn_curve_text("0:60; 120:0")), 2)
        for bad in ("abc", "0-60", "0:60, x:10"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_tn_curve_text(bad)

    def test_dc_params_from_curve(self):
        """图例曲线：0/120 rpm 恒扭矩 60 Nm，188 rpm 空载。"""
        params = dc_params_from_t_n_curve("0:60, 120:60, 188:0")
        self.assertEqual(params["saturation_effort"], 60.0)
        self.assertEqual(params["no_load_rpm"], 188.0)
        self.assertAlmostEqual(params["velocity_limit_rad_s"], 188.0 * 2 * math.pi / 60, places=6)

    def test_dc_params_extrapolates_no_load_speed(self):
        """末点扭矩不为 0 时按末段斜率外推（datasheet 常只给到额定点）。"""
        params = dc_params_from_t_n_curve("0:60, 100:20")
        self.assertEqual(params["saturation_effort"], 60.0)
        self.assertAlmostEqual(params["no_load_rpm"], 150.0, places=6)

    def test_dc_params_fail_closed(self):
        """非单调、水平末段（推不出空载）、点太少——全部拒绝，不猜。"""
        for bad in ("0:60, 120:80", "0:25, 95:25", "0:60", "0:0, 100:0"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    dc_params_from_t_n_curve(bad)

    def test_all_packages_default_to_ideal_pd_and_no_t_n_curve(self):
        """装箱状态：14 包都不该有 T-N 曲线，且 actuator_model 缺省 = ideal_pd（不改任何行为）。"""
        for package in package_dirs():
            with self.subTest(package=package.name):
                facts = t_n_curve_facts(package)
                self.assertFalse(facts["declared"], f"{package.name} 不该有默认 T-N 曲线")
                self.assertEqual(facts["actuator_model"], "ideal_pd")
                self.assertEqual(dc_actuator_settings(package), {})

    def test_t_n_curves_layer_by_role_then_by_joint(self):
        v3 = {
            "joints": {"actuated": [
                {"name": "FL_hip_joint", "role": "hip"}, {"name": "FR_hip_joint", "role": "hip"},
                {"name": "FL_calf_joint", "role": "calf"}, {"name": "FR_calf_joint", "role": "calf"},
            ]},
            "actuator_profile": {"by_role": {}, "by_joint": {}},
        }
        touched = apply_t_n_curves(v3, {"hip": "0:60, 120:60, 188:0", "FL_calf_joint": "0:120, 192:0"})
        self.assertEqual(touched, ["FL_calf_joint", "role:hip"])
        profile = v3["actuator_profile"]
        self.assertEqual(len(profile["by_role"]["hip"]["t_n_curve"]), 3)
        self.assertEqual(profile["by_joint"]["FL_calf_joint"]["t_n_curve"][0]["torque_nm"], 120.0)
        # 空串 = 清除该部位声明
        apply_t_n_curves(v3, {"hip": ""})
        self.assertNotIn("t_n_curve", profile["by_role"]["hip"])

    def test_t_n_curves_reject_invalid_before_writing(self):
        v3 = {"joints": {"actuated": [{"name": "FL_hip_joint", "role": "hip"}]},
              "actuator_profile": {"by_role": {}, "by_joint": {}}}
        with self.assertRaises(ValueError):
            apply_t_n_curves(v3, {"hip": "0:60, 120:80"})
        self.assertNotIn("t_n_curve", v3["actuator_profile"]["by_role"].get("hip", {}))

    def test_dc_settings_require_t_n_curve_when_enabled(self):
        """开 dc_motor 但缺曲线 → 抛错（不静默退回理想 PD）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = package_dirs()[0]
            shutil.copytree(package, root / "pkg")
            v3 = json.loads((root / "pkg" / "contract.json").read_text(encoding="utf-8-sig"))
            v3["control"]["actuator_model"] = "dc_motor"
            (root / "pkg" / "contract.json").write_text(
                json.dumps(v3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                dc_actuator_settings(root / "pkg")
            # 补上全角色 T-N 曲线后即可装配，且参数来自契约（同一真值）
            t_n_curves = {
                role: "0:60, 120:60, 188:0" for role in (v3.get("actuator_profile") or {}).get("by_role", {})
            }
            apply_t_n_curves(v3, t_n_curves)
            (root / "pkg" / "contract.json").write_text(
                json.dumps(v3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            settings = dc_actuator_settings(root / "pkg")
            self.assertTrue(settings)
            sample = next(iter(settings.values()))
            self.assertEqual(sample["saturation_effort"], 60.0)
            self.assertAlmostEqual(sample["velocity_limit"], 188.0 * 2 * math.pi / 60, places=6)
            self.assertIn("stiffness", sample)


class BrowserControlWiringTests(unittest.TestCase):
    """D9/P1：契约里的速度限幅与 T-N 曲线必须**真的到达**浏览器 control 载荷。

    背景：``robot.control`` 是**显式白名单**（``backend/simulation_api.py``），而浏览器读的是
    ``control.velocity_limits`` / ``control.motor_envelopes``。白名单缺键时契约里有值也到不了
    仿真——且失败是**静默**的：``applyVelocityLimits`` / ``applyMotorEnvelopes`` 拿到 undefined
    就直接早退（表现为"参数改了没反应"，而不是报错）。
    """

    def test_browser_control_payload_carries_velocity_limits(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        client = TestClient(app)
        control = client.get("/api/simulation/browser-config/unitree_g1").json()["robot"]["control"]
        self.assertIn("velocity_limits", control)
        self.assertTrue(control["velocity_limits"], "g1 契约声明了速度限幅，浏览器载荷必须带上")
        self.assertEqual(control["velocity_limits"]["hip_pitch"], 32.0)

    def test_browser_control_payload_carries_t_n_curves(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        client = TestClient(app)
        control = client.get("/api/simulation/browser-config/unitree_go2").json()["robot"]["control"]
        self.assertIn("motor_envelopes", control)
        # 装箱态：14 包都未声明曲线 → 空值（浏览器 applyMotorEnvelopes 早退，行为与现状一致）
        self.assertIsNone(control["motor_envelopes"])

    def test_browser_t_n_curve_view_shape_matches_browser_parser(self):
        """形状必须能被 app.js::normalizeMotorEnvelope 接受：[rpm, torque] 二元组、rpm 升序。"""
        view = payload_t_n_curve_view({
            "by_role": {"hip": [{"rpm": 0.0, "torque_nm": 60.0}, {"rpm": 188.0, "torque_nm": 0.0}]},
            "by_joint": {"FL_hip_joint": [{"rpm": 0.0, "torque_nm": 60.0}, {"rpm": 188.0, "torque_nm": 0.0}]},
        })
        self.assertEqual(sorted(view), ["fl_hip_joint", "hip"])
        points = view["fl_hip_joint"]
        self.assertEqual(points[0], [0.0, 60.0])
        self.assertTrue(all(isinstance(p, list) and len(p) == 2 for p in points))
        self.assertTrue(all(points[i][0] < points[i + 1][0] for i in range(len(points) - 1)))


if __name__ == "__main__":
    unittest.main()
