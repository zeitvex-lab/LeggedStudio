"""E6：专家模式 dot-path —— **任意参数可改，但越界/只读必须当场拒**。

判据原文只有"任意参数可改"（逃生门）。我给它加的护栏是"**不能改的要说清为什么、并指出能改什么**"，
因为这条逃生门此前**完全没校验**：路径拼错没人报、改到只读项也一样静默 —— 于是
"我改了但没生效"会再演一次（本仓反复踩的形态：看起来生效、实际不生效）。

所以测试守三关：**未知路径**（附最近似建议）、**只读项**（静态表兜底，缓存冷也拒）、
**类型不符**（不猜），以及"整批拒绝"这条——专家模式最危险的结果是"一部分生效、一部分被静默丢掉"。
"""

import unittest

from backend.training import dot_path

CATALOG = [
    {"path": "environment.rewards.tracking_lin_vel.weight", "label": "线速度跟踪权重",
     "type": "float", "value": 1.5, "category": "rewards", "readonly": False},
    {"path": "runner.algorithm.learning_rate", "label": "学习率", "type": "float",
     "value": 0.0003, "category": "learning", "readonly": False},
    {"path": "runner.actor.hidden_dims", "label": "网络宽度", "type": "list",
     "value": [512, 256], "category": "learning", "readonly": True},
    {"path": "environment.sim.mujoco.timestep", "label": "物理步长", "type": "float",
     "value": 0.005, "category": "simulator", "readonly": True},
    {"path": "environment.actions.leg_joint_pos.scale", "label": "腿部动作缩放",
     "type": "float", "value": 0.25, "category": "embodiment", "readonly": True},
]


class AddressableTest(unittest.TestCase):
    def test_pattern_paths_are_not_addressable(self):
        """模式化路径（代表**一类**关节）不能当点路径用。"""
        self.assertTrue(dot_path.is_addressable("runner.algorithm.learning_rate"))
        self.assertFalse(dot_path.is_addressable("environment.actions.*.scale"))
        self.assertFalse(dot_path.is_addressable("environment.actions.leg[0].scale"))


class CoerceTest(unittest.TestCase):
    def test_numeric_and_bool_coercion(self):
        self.assertEqual((3, None), dot_path.coerce_value("3", "int"))
        self.assertEqual((0.5, None), dot_path.coerce_value("0.5", "float"))
        self.assertEqual((True, None), dot_path.coerce_value("true", "bool"))
        self.assertEqual((False, None), dot_path.coerce_value("0", "bool"))

    def test_unknown_type_passes_through_without_inventing_rules(self):
        value, error = dot_path.coerce_value({"a": 1}, "whatever")
        self.assertIsNone(error)
        self.assertEqual({"a": 1}, value)

    def test_bad_value_reports_instead_of_guessing(self):
        _, error = dot_path.coerce_value("abc", "float")
        self.assertIsNotNone(error)
        self.assertIn("无法解析", error)


class ValidateTest(unittest.TestCase):
    def test_editable_path_passes_and_is_coerced(self):
        report = dot_path.validate_edits(
            {"runner.algorithm.learning_rate": "0.001"}, catalog=CATALOG,
        )
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(0.001, report["applied"]["runner.algorithm.learning_rate"])

    def test_unknown_path_is_refused_with_a_suggestion(self):
        report = dot_path.validate_edits(
            {"runner.algorithm.learning_rat": "0.001"}, catalog=CATALOG,
        )
        self.assertFalse(report["ok"])
        self.assertIn("最接近的可改路径", report["problems"][0])
        self.assertIn("learning_rate", report["problems"][0])

    def test_readonly_from_catalog_is_refused_with_reason(self):
        report = dot_path.validate_edits(
            {"environment.sim.mujoco.timestep": 0.01}, catalog=CATALOG,
        )
        self.assertFalse(report["ok"])
        self.assertIn("只读", report["problems"][0])

    def test_static_readonly_refuses_physics_even_without_catalog(self):
        """**缓存冷也要能拒**：改物理这件事不依赖参数目录。"""
        for path in ("environment.sim.mujoco.stiffness", "sim.control_hz",
                     "model.joints.armature", "environment.terrain_mixes"):
            with self.subTest(path=path):
                report = dot_path.validate_edits({path: 1}, catalog=None)
                self.assertFalse(report["ok"])
                self.assertIn("只读", report["problems"][0])

    def test_type_mismatch_is_refused(self):
        report = dot_path.validate_edits(
            {"runner.algorithm.learning_rate": "快一点"}, catalog=CATALOG,
        )
        self.assertFalse(report["ok"])
        self.assertIn("无法解析", report["problems"][0])

    def test_batch_is_all_or_nothing_in_meaning(self):
        """一批里有一条不合格 → `ok=False`，调用方必须**整批拒绝**（applied 仅供展示）。"""
        report = dot_path.validate_edits(
            {"runner.algorithm.learning_rate": 0.001, "runner.algorithm.nope": 1},
            catalog=CATALOG,
        )
        self.assertFalse(report["ok"])
        self.assertEqual(1, len(report["problems"]))
        self.assertIn("runner.algorithm.learning_rate", report["applied"],
                      "合格项仍要回显（供前端展示），但 ok=False 时不得写入")


class ApplyTest(unittest.TestCase):
    def test_apply_builds_missing_intermediate_nodes_without_mutating_input(self):
        base = {"runner": {"algorithm": {}}}
        merged = dot_path.apply_to_config(base, {"runner.algorithm.lr": 0.01, "environment.seed": 7})
        self.assertEqual(0.01, merged["runner"]["algorithm"]["lr"])
        self.assertEqual(7, merged["environment"]["seed"])
        self.assertEqual({"runner": {"algorithm": {}}}, base, "不得修改入参")


if __name__ == "__main__":
    unittest.main()
