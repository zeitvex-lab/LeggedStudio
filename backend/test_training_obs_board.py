"""E4：观测/动作映射板 —— 判据「**维度不符即时报错**」+ 观测五元组可视化。

五元组（重构方案 §5.1）：`(source, role[actor|critic|teacher|student], history, encoder,
deployment_available)`；**部署观测 = 过滤 `deployment_available=true ∧ role=actor`**。

`RealBoardCharacterizationTest` 里的数字是**特征化测试**（characterization test）：
它锁住的是"映射板**如实报出**了什么"，而不是"一切都干净"。

**2026-09-14 进展**：3 份契约（lite3 / m20 / b2）的五元组已补齐 —— 证据分三层：① `rl_sar` 的
lite3 **部署清单**就是这 6 项（`observations: [commands, ang_vel, gravity_vec, dof_pos, dof_vel,
actions]`，`num_observations: 45`）；② 三者的**策略输入宽度 = 这 6 项之和**（少一项就部署不了）；
③ 6 项的物理来源都是真机必备（IMU / 关节编码器 / 遥控指令 / 上一步动作）。
于是「缺五元组字段」这栏归零，并**升格为不变量**（见 `FiveTupleInvariantTest`，不再是快照）。
**剩下的 11 份仍是「只声明宽度、未声明组件」** —— 那个数字改小了，才说明缺口继续收敛。
"""

import json
import pathlib
import unittest

from backend.training import obs_board as ob

ROBOTS = pathlib.Path(__file__).resolve().parents[1] / "assets" / "robots"


def _load(robot: str) -> dict:
    return json.loads((ROBOTS / robot / "contract_v3.json").read_text(encoding="utf-8-sig"))


def _synthetic(*, components: list | None = None, dimension: int | None = None,
               order: list | None = None, actuated: list | None = None) -> dict:
    return {
        "robot_id": "synthetic",
        "observation": {"components": components, "dimension": dimension},
        "action": {"joint_order": order or [], "action_scale": 0.25},
        "joints": {"actuated": [{"name": name} for name in (actuated or [])]},
    }


def _full_component(**overrides) -> dict:
    base = {"id": "c", "width": 3, "source": "imu", "role": "actor",
            "history": 1, "encoder": None, "deployment_available": True}
    base.update(overrides)
    return base


class FiveTupleTest(unittest.TestCase):
    def test_missing_fields_are_reported_with_the_component_id(self):
        """缺字段必须**点名报出**：缺的字段会一路传到部署侧，不能等部署时才发现。"""
        board = ob.observation_board(
            _synthetic(components=[{"id": "base_ang_vel", "width": 3}], dimension=3),
        )
        row = board["components"][0]
        self.assertEqual(["source", "role", "history", "encoder", "deployment_available"],
                         row["missing_fields"])
        self.assertTrue(any("base_ang_vel" in item and "五元组缺字段" in item
                            for item in board["problems"]))

    def test_complete_five_tuple_yields_deployment_dimension(self):
        """部署宽度＝`deployment_available ∧ role=actor` 的宽度之和（critic/特权项不进部署）。"""
        components = [
            _full_component(id="base_ang_vel", width=3),
            _full_component(id="privileged", width=5, role="critic",
                            deployment_available=False),
        ]
        board = ob.observation_board(_synthetic(components=components, dimension=8))
        self.assertEqual([], board["problems"])
        self.assertEqual(8, board["components_total"])
        self.assertEqual(3, board["deployment_dimension"])

    def test_width_mismatch_is_an_error(self):
        board = ob.observation_board(_synthetic(components=[_full_component(width=3)], dimension=99))
        self.assertTrue(any("维度不符即时报错" in item for item in board["problems"]))

    def test_undeclared_components_are_said_out_loud_not_faked(self):
        """没声明组件就**说没声明**，不拿 dimension 假充组件之和（不编数据）。"""
        board = ob.observation_board(_synthetic(components=[], dimension=48))
        self.assertEqual(0, board["components_declared"])
        self.assertIsNone(board["components_total"])
        self.assertIsNone(board["deployment_dimension"])
        self.assertIn("未声明", board["note"])


class ActionBoardTest(unittest.TestCase):
    def test_unknown_and_missing_joints_are_reported(self):
        board = ob.action_board(_synthetic(
            order=["A", "B", "Z"], actuated=["A", "B", "C"],
        ))
        self.assertEqual(["Z"], board["unknown_in_order"])
        self.assertEqual(["C"], board["missing_from_order"])
        self.assertEqual(2, len(board["problems"]))

    def test_every_real_contract_has_consistent_action_mapping(self):
        """**真实仓不变量**：14 个机型的 `joint_order` 与驱动关节一一对应（实测 0 问题）。"""
        problems = {}
        for path in sorted(ROBOTS.glob("*/contract_v3.json")):
            report = ob.action_board(json.loads(path.read_text(encoding="utf-8-sig")))
            if report["problems"]:
                problems[path.parent.name] = report["problems"]
        self.assertEqual({}, problems)


class RealBoardCharacterizationTest(unittest.TestCase):
    """**特征化测试**：锁住映射板当前如实报出的缺口（补上后这两个数字要改小）。"""

    @staticmethod
    def _scan() -> tuple[set[str], set[str]]:
        without_components: set[str] = set()
        missing_fields: set[str] = set()
        for path in sorted(ROBOTS.glob("*/contract_v3.json")):
            robot = path.parent.name
            report = ob.board(json.loads(path.read_text(encoding="utf-8-sig")))
            if report["observations"]["components_declared"] == 0:
                without_components.add(robot)
            if report["observations"]["problems"]:
                missing_fields.add(robot)
        return without_components, missing_fields

    def test_no_package_is_left_without_components(self):
        """**不变量**（2026-09-15 收口）：14 包全部声明了观测组件 —— 空缺集必须为空。

        这条从「特征化快照」升格为「不变量」：**只要还有一台没声明组件，它就红**。
        快照时代它记的是「11 台缺组件」，随补齐一路减到 0（11→9→7→6→3→0）；
        现在它守的是「别再退回去」。
        """
        without_components, _ = self._scan()
        self.assertEqual(set(), without_components)


class FiveTupleInvariantTest(unittest.TestCase):
    """**不变量**（不再是快照）：契约一旦声明组件，五元组就得齐全、部署宽度就得自洽。

    2026-09-14 补齐 lite3 / m20 / b2 后升格。缺字段的后果很具体：部署观测 =
    ``deployment_available ∧ role=actor`` 这条过滤**无从执行** —— 于是"训练能看、部署看不到"
    的特权信息无处可查（这正是 E4 存在的理由）。
    """

    def test_no_contract_declares_components_without_a_full_five_tuple(self):
        incomplete: dict[str, list] = {}
        for path in sorted(ROBOTS.glob("*/contract_v3.json")):
            report = ob.board(json.loads(path.read_text(encoding="utf-8-sig")))
            bad = [row["id"] for row in report["observations"]["components"] if row["missing_fields"]]
            if bad:
                incomplete[path.parent.name] = bad
        self.assertEqual({}, incomplete, "声明了组件就必须五元组齐全")

    def test_filled_robots_have_self_consistent_deployment_width(self):
        """补齐的 3 份：**部署宽度 == 组件宽度之和 == 声明宽度**（= 策略输入宽度）。"""
        for robot, expected in (("deeprobotics_lite3", 45), ("deeprobotics_m20", 57), ("unitree_b2", 45)):
            with self.subTest(robot=robot):
                observation = ob.board(_load(robot))["observations"]
                self.assertEqual(expected, observation["declared_dimension"])
                self.assertEqual(expected, observation["components_total"])
                self.assertEqual(expected, observation["deployment_dimension"],
                                 "6 项都是 actor ∧ deployment_available ⇒ 全部可部署")
                self.assertEqual([], observation["problems"])


if __name__ == "__main__":
    unittest.main()
