"""K3 回归测试：契约裁决器（一次实现，导出链路 + 跨引擎链路复用）。

要点：

* 三档处置 deny / warn / allow 语义正确；
* **不对称出现 fail-closed**（K3 的核心新增）——一侧有值一侧未声明即拒绝；
* 「显式 null」与「键不存在」必须区分（``action.reindex_from_model = null`` 是取值，
  不是缺失），否则既会误报又会漏检；
* 每条目含 **字段 / 源值 / 目标值 / 处置 / 依据**；
* 导出闸门与 ``tools/sim2sim_validator`` 的守卫对同一输入给出**同一处置**。
"""

from __future__ import annotations

import unittest

from backend.contract_adjudicator import (
    ALLOW,
    DENY,
    DENY_FIELDS,
    MISSING,
    WARN,
    adjudicate,
    adjudicate_sim2sim,
    adjudicator_selftest,
    extract_field,
    format_report,
)
from backend.export_gate import compare_contracts, sim2sim_contract_guard


def contract(**overrides) -> dict:
    """一份字段齐全的契约样本（与 go2 快照同构，尺寸缩小便于阅读）。"""
    base = {
        "action": {
            "joint_order": ["FL_hip_joint", "FL_thigh_joint"],
            "action_scale": 0.25,
            "reindex_from_model": None,
        },
        "observation": {
            "dimension": 6,
            "components": [{"name": "joint_pos", "width": 2}, {"name": "command", "width": 4}],
        },
        "control": {"control_hz": 50, "physics_hz": 500, "decimation": 10},
        "actuator_profile": {"by_role": {"hip": {"armature": 0.01, "effort": 23.7, "mode": "torque"}}},
        "reward_scales": {"track_linear_velocity": 1.0},
    }
    for path, value in overrides.items():
        head, _, tail = path.partition(".")
        if tail:
            base[head][tail] = value
        else:
            base[path] = value
    return base


class DispositionTests(unittest.TestCase):
    def test_identical_contracts_are_allowed(self):
        report = adjudicate(contract(), contract())
        self.assertTrue(report["ok"])
        self.assertEqual(report["disposition"], ALLOW)
        self.assertEqual(report["counts"]["deny"], 0)

    def test_denylist_drift_denies(self):
        report = adjudicate(contract(), contract(**{"action.action_scale": 0.5}))
        self.assertFalse(report["ok"])
        self.assertEqual(report["disposition"], DENY)
        self.assertTrue(any("action.action_scale" in item for item in report["blockers"]))

    def test_warning_field_drift_only_warns(self):
        report = adjudicate(contract(), contract(**{"control.decimation": 20}))
        self.assertTrue(report["ok"])
        self.assertEqual(report["disposition"], WARN)
        self.assertTrue(any("control.decimation" in item for item in report["warnings"]))

    def test_unknown_context_rejected(self):
        with self.assertRaises(ValueError):
            adjudicate(contract(), contract(), context="teleport")

    def test_every_entry_has_the_five_elements(self):
        report = adjudicate(contract(), contract(**{"action.action_scale": 0.5}))
        required = {"field", "source_value", "target_value", "disposition", "basis", "reason"}
        for entry in report["entries"]:
            with self.subTest(field=entry["field"]):
                self.assertTrue(required <= set(entry))
        self.assertEqual(len(report["entries"]), len(DENY_FIELDS) + 3)  # 7 deny 字段 + 3 warn 字段

    def test_report_rows_render_with_values_and_basis(self):
        report = adjudicate(contract(), contract(**{"action.action_scale": 0.5}))
        table = format_report(report)
        self.assertIn("| 字段 | 源值 | 目标值 | 处置 | 依据 |", table)
        self.assertIn("action.action_scale", table)
        self.assertIn("DENYLIST#action.action_scale", table)


class AsymmetryFailClosedTests(unittest.TestCase):
    """K3 的核心语义：无法验证 ≠ 没有问题。"""

    def test_missing_on_one_side_denies(self):
        # 源侧声明了 joint_order 却完全没有 action_scale → 该字段不对称
        report = adjudicate({"action": {"joint_order": ["a", "b"]}}, contract())
        self.assertFalse(report["ok"])
        self.assertEqual(report["disposition"], DENY)
        entry = next(item for item in report["entries"] if item["field"] == "action.action_scale")
        self.assertEqual(entry["disposition"], DENY)
        self.assertEqual(entry["target_value"], 0.25)
        self.assertEqual(entry["source_value"], "<缺失>")
        self.assertEqual(entry["basis"], "ASYMMETRY_FAIL_CLOSED#action.action_scale")

    def test_export_gate_reports_asymmetry_as_blocker(self):
        report = compare_contracts({"action": {}}, contract())
        self.assertFalse(report["ok"])
        self.assertTrue(any("fail-closed" in item for item in report["blockers"]))

    def test_both_sides_missing_is_not_denied(self):
        report = adjudicate({"action": {}}, {"action": {}})
        self.assertTrue(report["ok"])
        self.assertEqual(report["disposition"], WARN)
        bases = {item["basis"] for item in report["entries"] if item["disposition"] == WARN}
        self.assertTrue(any(basis.startswith("BOTH_MISSING#") for basis in bases), bases)

    def test_explicit_null_is_a_value_not_absence(self):
        # 两侧都显式 null（恒等映射）→ 一致，不应报"无法强校验"
        same = adjudicate(contract(), contract())
        entry = next(item for item in same["entries"] if item["field"] == "action.reindex_from_model")
        self.assertEqual(entry["disposition"], ALLOW)
        self.assertIsNone(entry["source_value"])
        # 一侧 null、一侧真映射表 → 值不一致，必须 deny
        drift = adjudicate(contract(), contract(**{"action.reindex_from_model": [1, 0]}))
        entry = next(item for item in drift["entries"] if item["field"] == "action.reindex_from_model")
        self.assertEqual(entry["disposition"], DENY)

    def test_extract_field_distinguishes_missing_and_null(self):
        self.assertIs(extract_field({"action": {}}, "action.reindex_from_model"), MISSING)
        self.assertIsNone(extract_field({"action": {"reindex_from_model": None}}, "action.reindex_from_model"))

    def test_warn_field_asymmetry_does_not_block(self):
        report = adjudicate(contract(), {"control": {"control_hz": 50}})
        # control_hz 缺失 → deny（DENYLIST）；decimation 缺失 → warn
        decimation = next(item for item in report["entries"] if item["field"] == "control.decimation")
        self.assertEqual(decimation["disposition"], WARN)
        self.assertEqual(decimation["basis"], "ASYMMETRY_WARN#control.decimation")


class SingleImplementationTests(unittest.TestCase):
    """一处实现、两条链路——判据不能各写一份。"""

    def test_export_and_sim2sim_agree_on_same_input(self):
        source, target = contract(), contract(**{"action.action_scale": 0.5, "reward_scales": {"x": 2.0}})
        export = adjudicate(source, target, context="export")
        sim2sim = adjudicate_sim2sim(source, target)
        self.assertEqual(
            [(item["field"], item["disposition"]) for item in export["entries"]],
            [(item["field"], item["disposition"]) for item in sim2sim["entries"]],
        )
        self.assertEqual(export["disposition"], sim2sim["disposition"])
        self.assertNotEqual(export["context"], sim2sim["context"])
        self.assertIn("跨引擎", sim2sim["context_label"])

    def test_export_gate_guard_delegates_to_the_same_implementation(self):
        source, target = contract(), contract(**{"observation.dimension": 8})
        report = sim2sim_contract_guard(source, target)
        export = compare_contracts(source, target)
        self.assertEqual(report["disposition"], DENY)
        self.assertEqual(report["context"], "sim2sim")
        # 判据（字段 + 处置 + 依据）完全一致，只有 context 措辞不同
        self.assertEqual(
            [(item["field"], item["disposition"], item["basis"]) for item in report["entries"]],
            [(item["field"], item["disposition"], item["basis"]) for item in export["entries"]],
        )
        self.assertEqual(len(report["blockers"]), len(export["blockers"]))

    def test_sim2sim_validator_reuses_the_guard(self):
        from tools.sim2sim_validator import guard_contract_consistency

        report = guard_contract_consistency(contract(), contract(**{"action.action_scale": 0.5}))
        self.assertEqual(report["disposition"], DENY)
        self.assertEqual(report["context"], "sim2sim")

    def test_adjudicator_selftest_passes(self):
        result = adjudicator_selftest()
        self.assertEqual(result["verdict"], "pass", result["failures"])


if __name__ == "__main__":
    unittest.main()
