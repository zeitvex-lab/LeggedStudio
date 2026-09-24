"""族 MJCF 约定门禁的回归锁（`tools/audit_family_mjcf.py`）。

两层：
* **规则层**（反例注入）：口径类"实测 == 声明 或 已登记偏离"的三条判红——未登记、**登记了又
  与实测一致**（防静默统一/静默放宽）、登记项缺 `why` / 未知键；
* **真仓层**：跑一遍门禁本体，2 个族 × 8 台必须 0 判红（规范化后无名传感器清零、"撤 XML 执行器"
  口径真能编译、被动关节与契约对账、口径偏离全部登记）。

为什么这层重要：这四项差异（执行器归属 / margin 政策 / 无传感器名 / keyframe 引用 ctrl）此前
散在各机型里、谁都不知道全景——"同架构"要有个基准，就得有人逐台把偏离摆到台面上。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_family_mjcf import _actuator_binding, audit, check_conventions  # noqa: E402

_CONVENTIONS = {"actuator_binding": "mjcf_wrapped", "margin_policy": "zero"}


def _summary(**overrides) -> dict:
    base = {"family": "demo", "robot_id": "demo_a", "actuator_binding": "mjcf_wrapped", "margin_policy": "zero"}
    base.update(overrides)
    return base


class ConventionRulesTest(unittest.TestCase):
    def test_matching_values_pass(self):
        problems: list[str] = []
        check_conventions(_summary(), _CONVENTIONS, {}, problems)
        self.assertEqual([], problems)

    def test_unregistered_deviation_is_red(self):
        problems: list[str] = []
        check_conventions(_summary(actuator_binding="cfg_declared"), _CONVENTIONS, {}, problems)
        self.assertEqual(1, len(problems))
        self.assertIn("未登记", problems[0])

    def test_registered_deviation_passes_with_reason(self):
        problems: list[str] = []
        check_conventions(
            _summary(actuator_binding="cfg_declared"), _CONVENTIONS,
            {"actuator_binding": {"value": "cfg_declared", "why": "上游口径，未上 Kit"}}, problems,
        )
        self.assertEqual([], problems)

    def test_stale_registration_is_red(self):
        """登记了偏离、实测却与声明一致 ⇒ 判红（否则登记表会变成永久谎言）。"""
        problems: list[str] = []
        check_conventions(
            _summary(), _CONVENTIONS,
            {"actuator_binding": {"value": "cfg_declared", "why": "旧记录"}}, problems,
        )
        self.assertEqual(1, len(problems))
        self.assertIn("登记该撤掉", problems[0])

    def test_deviation_without_reason_is_red(self):
        problems: list[str] = []
        check_conventions(
            _summary(margin_policy="warp_ccd_off"), _CONVENTIONS,
            {"margin_policy": {"value": "warp_ccd_off"}}, problems,
        )
        self.assertEqual(1, len(problems))
        self.assertIn("没写 why", problems[0])

    def test_unknown_deviation_key_is_red(self):
        problems: list[str] = []
        check_conventions(_summary(), _CONVENTIONS, {"whatever": {"value": "x", "why": "y"}}, problems)
        self.assertEqual(1, len(problems))
        self.assertIn("未知键", problems[0])


class ActuatorBindingDerivationTest(unittest.TestCase):
    def _package(self, tmp: Path, body: str, name: str = "robot_constants.py") -> Path:
        source = tmp / "training" / "source" / "demo_velocity"
        source.mkdir(parents=True)
        (source / name).write_text(body, encoding="utf-8")
        return tmp

    def test_kit_factory_counts_as_mjcf_wrapped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = self._package(Path(tmp), 'hip, thigh, calf = kit.position_actuator_trio((".*hip.*",))\n')
            self.assertEqual("mjcf_wrapped", _actuator_binding(package))

    def test_direct_xml_actuator_cfg_counts_as_mjcf_wrapped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = self._package(Path(tmp), 'A = XmlActuatorCfg(target_names_expr=(".*",))\n')
            self.assertEqual("mjcf_wrapped", _actuator_binding(package))

    def test_builtin_groups_mean_cfg_declared(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = self._package(Path(tmp), 'A = BuiltinPositionActuatorCfg(target_names_expr=(".*",))\n')
            self.assertEqual("cfg_declared", _actuator_binding(package))


class RealRegistryTest(unittest.TestCase):
    def test_two_families_eight_members_have_no_problem(self):
        rows, problems = audit()
        self.assertEqual([], problems, "族 MJCF 约定门禁判红：\n" + "\n".join(problems))
        self.assertEqual(8, len(rows))
        for row in rows:
            self.assertTrue(row["sensors_named_after"], row["robot_id"])
            self.assertTrue(row["strip_compiles"], row["robot_id"])
            self.assertEqual(0, row["joints_total"] - row["joints_actuated"], row["robot_id"])


if __name__ == "__main__":
    unittest.main()
