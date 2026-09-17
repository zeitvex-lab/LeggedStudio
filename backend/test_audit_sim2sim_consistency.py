"""H23：sim2sim 执行器/滤波一致性审计的钉住测试。

守三件事：

1. **当前仓全绿**：浏览器下发 ↔ 契约 v3 ↔ 训练常量表 ↔ 电机参数卡 四端同值，
   B3 残留为零，端点接线钉住全中，rc_old 参考事实可取证；
2. **注入反例必红**：往 ``simulation/config.json`` 篡改/回填增益（B3 残留）、删掉
   ``contract_v3.json``（物理真值回落 legacy config）、清空契约增益（端点以内置
   默认 fabrication 进仿真）、拆掉端点接线钉住——审计必须逐条报出；
3. **诚实边界**：``--json`` 结构稳定；rc_old 参考文件缺失时降级为
   ``status="missing"`` 而不崩、不判红（参考值不参与门禁，契约才是真值）。

另有一条**语义钉住**值得说明：单改契约里的一处增益值**不会**被本审计判红——
契约就是真值，改它=改真值，两端（浏览器/训练）会跟着一起走（MJCF 是否随之重固化
由 ``validate_mjcf_contract.py`` 守，不在 H23 范围）。判红的是"我们自己的两端不一致"。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.audit_sim2sim_consistency import (
    ENDPOINT_WIRING_PINS,
    audit,
    browser_control_value,
    browser_velocity_value,
    check_config_residuals,
    check_endpoint_wiring,
    check_package,
    rc_old_reference,
)

ROOT = Path(__file__).resolve().parents[1]
GO2_CONTRACT = ROOT / "assets" / "robots" / "unitree_go2" / "contract_v3.json"


def make_package(root: Path, contract: dict | None = None, sim_config: dict | None = None) -> Path:
    """在临时目录搭一个最小机器人包（契约 v3 [+ sim config]）。"""
    package = root / "unitree_go2_like"
    package.mkdir(parents=True)
    source = contract if contract is not None else json.loads(GO2_CONTRACT.read_text(encoding="utf-8-sig"))
    (package / "contract_v3.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    if sim_config is not None:
        (package / "simulation").mkdir(exist_ok=True)
        (package / "simulation" / "config.json").write_text(json.dumps(sim_config, ensure_ascii=False), encoding="utf-8")
    return package


class RealRepoAuditGreenTest(unittest.TestCase):
    """真实仓不变量：四端一致、B3 零残留、接线钉住全中。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit()

    def test_audit_is_green(self):
        self.assertEqual([], self.report["problems"])
        self.assertTrue(self.report["ok"])

    def test_every_package_serves_contract_v3_physics(self):
        for row in self.report["packages"]:
            with self.subTest(package=row["robot"], scope=row["scope"]):
                self.assertEqual("contract_v3", row["physics_source"])
                self.assertTrue(row["gains_equal_contract"], row["problems"])
                self.assertTrue(row["physics_view_equal_payload"])

    def test_bundled_packages_are_covered(self):
        """bundled 范围必须覆盖 assets/robots 下全部机型（链路枚举没掉包）。"""
        bundled = {row["robot"] for row in self.report["packages"] if row["scope"] in ("bundled", "both")}
        on_disk = {p.name for p in (ROOT / "assets" / "robots").iterdir() if p.is_dir()}
        self.assertEqual(on_disk, bundled)

    def test_browser_chain_packages_audited(self):
        """浏览器链（mujoco_sim 能力 + browser_package）解析出的每个包都在审计范围内。"""
        from backend.robot_presets import list_robot_presets
        from backend.simulation_browser import browser_package

        served: set[str] = set()
        for preset in list_robot_presets():
            capabilities = [str(c) for c in ((preset.get("robot_package") or {}).get("capabilities") or [])]
            if "mujoco_sim" not in capabilities:
                continue
            root, _ = browser_package(str(preset["robot_id"]))
            served.add((root.resolve(), preset["robot_id"]))
        audited = {
            (ROOT / row["root"]).resolve() if not Path(row["root"]).is_absolute() else Path(row["root"]).resolve()
            for row in self.report["packages"]
            if row["scope"] in ("browser", "both")
        }
        for root, robot_id in served:
            with self.subTest(robot=robot_id):
                self.assertIn(root.resolve(), audited)

    def test_endpoint_wiring_pinned_on_real_source(self):
        source = (ROOT / "backend" / "simulation_api.py").read_text(encoding="utf-8")
        self.assertEqual([], check_endpoint_wiring(source))
        self.assertGreaterEqual(len(ENDPOINT_WIRING_PINS), 10)

    def test_rc_old_reference_extracted_with_evidence(self):
        """H23 原文的数字（50/1.5/1.0/17 与 lpf 5.0/15.0）必须能从上游文件取证。"""
        reference = self.report["rc_old_reference"]
        self.assertEqual("ok", reference["status"])
        self.assertFalse(reference["gating"])
        pd = reference["pd"]
        expected = {
            "leg_kp": 50.0,
            "leg_kd": 1.5,
            "wheel_kd": 1.0,
            "torque_limit_nm": 17.0,
            "lpf_legs_hz": 5.0,
            "lpf_wheels_hz": 15.0,
        }
        for name, value in expected.items():
            with self.subTest(reference=name):
                self.assertIn(name, pd)
                self.assertAlmostEqual(value, pd[name]["value"], places=9)
                self.assertIn(":", pd[name]["evidence"], "证据必须带 文件:行号")

    def test_rc_old_counterpart_matches_reference(self):
        """本仓轮足机型（zex-w）当前契约值与 rc_old 实测一致（传承关系成立）。"""
        repo_side = self.report["rc_old_reference"]["repo_side"]
        self.assertEqual("ok", repo_side["status"])
        self.assertEqual("zex-w", repo_side["robot"])
        for name, matched in repo_side["matches"].items():
            with self.subTest(reference=name):
                self.assertTrue(matched, f"{name}: repo={repo_side['values'][name]} 应与 rc_old 参考一致")


class CounterexampleRedTest(unittest.TestCase):
    """注入反例必红：审计不是摆设。"""

    def test_tampered_gain_in_sim_config_is_red(self):
        """往 simulation/config.json 回填一处增益（B3 废弃键）→ 必须报。"""
        import tempfile

        config = {
            "actuator_interface": "position_target",
            # 篡改：把 FL_hip_joint 的刚度 999 写回 config（真值在契约里是 20）
            "stiffness": {"FL_hip_joint": 999.0},
        }
        with tempfile.TemporaryDirectory() as tmp:
            package = make_package(Path(tmp), sim_config=config)
            report = check_package(package)
        checks = [problem["check"] for problem in report["problems"]]
        self.assertIn("simulation/config.json 无 B3 废弃物理键", checks)
        b3 = next(problem for problem in report["problems"] if "B3" in problem["check"])
        self.assertIn("stiffness", b3["evidence"])
        self.assertFalse(report["gains_equal_contract"] and not report["problems"])

    def test_missing_contract_falls_back_to_legacy_and_is_red(self):
        """删掉 contract_v3.json → physics_facts 回落 legacy config → 判红。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = make_package(Path(tmp), sim_config={"stiffness": {"hip": 20.0}})
            (package / "contract_v3.json").unlink()
            report = check_package(package)
        self.assertTrue(any(p["check"] == "物理真值来源=契约 v3" for p in report["problems"]))
        self.assertFalse(report["gains_equal_contract"])

    def test_stripped_gains_trigger_endpoint_fabrication_red(self):
        """契约增益被清空 → 端点把内置默认（50/1.5…）顶进仿真 → 判红。"""
        import tempfile

        stripped = json.loads(GO2_CONTRACT.read_text(encoding="utf-8-sig"))
        stripped["actuator_profile"] = {"by_role": {}, "by_joint": {}, "default": {}}
        with tempfile.TemporaryDirectory() as tmp:
            package = make_package(Path(tmp), contract=stripped)
            report = check_package(package)
        fabrication = [p for p in report["problems"] if "fabrication" in p["check"]]
        self.assertTrue(fabrication, report["problems"])
        self.assertTrue(any("50.0" in p["evidence"] for p in fabrication), fabrication)
        self.assertFalse(report["gains_equal_contract"])

    def test_tampering_the_contract_itself_is_not_an_end_to_end_drift(self):
        """语义钉住：改契约=改真值，两端同走，审计不伪造红项（MJCF 由别家守）。"""
        import tempfile

        retuned = json.loads(GO2_CONTRACT.read_text(encoding="utf-8-sig"))
        by_role = retuned["actuator_profile"]["by_role"]
        tuned_role = next(role for role, params in by_role.items() if "stiffness" in params)
        by_role[tuned_role]["stiffness"] = float(by_role[tuned_role]["stiffness"]) + 7.0
        with tempfile.TemporaryDirectory() as tmp:
            report = check_package(make_package(Path(tmp), contract=retuned))
        self.assertEqual([], report["problems"], "契约是真值：改契约后两端同值，不构成两端不一致")

    def test_broken_endpoint_wiring_pin_is_red(self):
        source = (ROOT / "backend" / "simulation_api.py").read_text(encoding="utf-8")
        # 模拟"有人改了白名单装配"：把 stiffness 透传行换成硬编码
        broken = source.replace('"stiffness": payload_physics["stiffness"] or', '"stiffness": 40.0 or')
        missing = check_endpoint_wiring(broken)
        self.assertIn("白名单 stiffness 透传", missing)
        self.assertEqual([], check_endpoint_wiring(source))

    def test_browser_lookup_replicas_match_app_js_key_order(self):
        """审计的两条浏览器查找复刻必须与 app.js 两条真实键序一致（不自创并集口径）。

        controlValue:   精确名 → segment → group → "joint"；
        applyVelocityLimits: 精确名 → segment → group → joint.toLowerCase()（无 "joint"）。
        乱复刻会把合法的逐关节覆盖判成漂移（假红）或把漂移漏掉（假绿）。
        """
        table = {"FL_hip_joint": 25.0, "hip": 10.0, "joint": 1.0}
        self.assertEqual(25.0, browser_control_value(table, "FL_hip_joint"))
        self.assertEqual(25.0, browser_velocity_value(table, "FL_hip_joint"))
        # 角色键在 segment 之后的查找序里先于"小写关节名"/"joint" 兜底命中：
        # 两条真实键序此时同值（app.js 两函数皆如此）。
        lower_only = {"fl_hip_joint": 7.0}
        self.assertEqual(7.0, browser_velocity_value(lower_only, "FL_hip_joint"))
        self.assertIsNone(browser_control_value(lower_only, "FL_hip_joint"))
        # applyVelocityLimits 没有 "joint" 兜底：joint-only 表对 velocity 查找落空。
        self.assertIsNone(browser_velocity_value({"joint": 3.0}, "FL_hip_joint"))
        self.assertEqual(3.0, browser_control_value({"joint": 3.0}, "FL_hip_joint"))

    def test_workspace_copy_residuals_are_demoted_to_notes(self):
        """非仓属包（workspace 导入副本）的 B3 残留降级为环境备注，不进门禁。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = make_package(Path(tmp), sim_config={"stiffness": {"FL_hip_joint": 999.0}})
            self.assertFalse(check_package(package)["problems"] == [])
            report = audit(robots_dir=Path(tmp))
        self.assertTrue(report["ok"], "workspace 副本的 config 残留只登记，不判红")
        kinds = {note.get("kind") for note in report["environment_notes"]}
        self.assertIn("workspace_legacy_config_keys", kinds)

    def test_repo_owned_scope_check(self):
        """_is_repo_owned 口径：assets/robots 下的包才是仓属（B3 残留进门禁的范围）。"""
        import tempfile

        from tools.audit_sim2sim_consistency import _is_repo_owned

        self.assertTrue(_is_repo_owned(ROOT / "assets" / "robots" / "unitree_go2"))
        self.assertTrue(_is_repo_owned(ROOT / "assets" / "robots"))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(_is_repo_owned(Path(tmp) / "somewhere"))

    def test_legit_per_joint_velocity_override_is_not_false_red(self):
        """合法契约模式：by_role.velocity_limit + 单关节 by_joint 覆盖 → 不得误判。"""
        import tempfile

        v3 = json.loads(GO2_CONTRACT.read_text(encoding="utf-8-sig"))
        profile = v3.setdefault("actuator_profile", {})
        by_role = profile.setdefault("by_role", {})
        by_joint = profile.setdefault("by_joint", {})
        for params in by_role.values():
            if isinstance(params, dict):
                params["velocity_limit"] = 10.0
        override_joint = next(
            entry["name"] for entry in v3["joints"]["actuated"] if "hip" in str(entry.get("name"))
        )
        by_joint.setdefault(override_joint, {})["velocity_limit"] = 25.0
        with tempfile.TemporaryDirectory() as tmp:
            report = check_package(make_package(Path(tmp), contract=v3))
        velocity_reds = [p for p in report["problems"] if "velocity" in p["check"]]
        self.assertEqual([], velocity_reds, report["problems"])


class ReportShapeTest(unittest.TestCase):
    """--json 结构稳定：键集合固定、问题条目四元组齐全、可 json 序列化。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit()

    def test_top_level_keys_are_stable(self):
        self.assertEqual(
            {"schema", "ok", "gating", "packages", "endpoint_wiring", "rc_old_reference",
             "environment_notes", "problems", "problem_count"},
            set(self.report),
        )
        self.assertEqual("sim2sim-consistency-audit-1.0", self.report["schema"])

    def test_problem_entries_carry_robot_check_file_evidence(self):
        for problem in self.report["problems"]:
            with self.subTest(problem=problem):
                self.assertEqual({"robot", "check", "file", "evidence"}, set(problem))

    def test_package_rows_are_stable(self):
        for row in self.report["packages"]:
            with self.subTest(package=row["robot"]):
                self.assertEqual(
                    {"robot", "root", "physics_source", "joint_count", "gains_equal_contract",
                     "physics_view_equal_payload", "action_filter_cutoffs", "config_residuals",
                     "problems", "infos", "scope"},
                    set(row),
                )

    def test_report_is_json_serializable(self):
        payload = json.dumps(self.report, ensure_ascii=False)
        self.assertIn('"ok": true', payload)


class RcOldDegradationTest(unittest.TestCase):
    """参考值缺文件：如实降级（status=missing），不崩、不判红。"""

    def test_missing_reference_files_degrade_gracefully(self):
        missing = rc_old_reference(Path("Z:/no/such/file.hpp"), Path("Z:/no/such/file.cpp"))
        self.assertEqual("missing", missing["status"])
        self.assertFalse(missing["gating"])
        self.assertEqual({}, missing["pd"])

    def test_full_audit_with_missing_reference_stays_green(self):
        report = audit(rc_old_hpp=Path("Z:/no/such/file.hpp"), rc_old_cpp=Path("Z:/no/such/file.cpp"))
        self.assertTrue(report["ok"])
        self.assertEqual("missing", report["rc_old_reference"]["status"])

    def test_nested_dead_physics_is_reported_not_fatal(self):
        """B3 口径之外的嵌套死数据（g1 的 config.control.stiffness）：登记不判红。"""
        top, nested = check_config_residuals({
            "control": {"stiffness": {"a": 1.0}, "damping": {"a": 0.5}, "settle_steps": 10},
        })
        self.assertEqual([], top)
        self.assertEqual(["damping", "stiffness"], sorted(nested))
        top_only, _ = check_config_residuals({"stiffness": {"a": 1.0}})
        self.assertEqual(["stiffness"], top_only)


if __name__ == "__main__":
    unittest.main()
