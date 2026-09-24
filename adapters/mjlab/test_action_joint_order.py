"""导出盖章的关节序必须取**动作接口序**（`native_worker.action_joint_order`）。

根因（2026-09-24 移植核对 F2）：原实现取 `scene["robot"].joint_names`（MJCF 实体序），而策略的
动作向量是**动作项**拼出来的（轮足 = `joint_pos` 腿 + `wheel_vel` 轮，腿先轮后）。m20 的 MJCF 是
逐腿混排 ⇒ 盖章与策略实际动作序互相错标。真跑导出复验见
`workspace/validation/m20_export_metadata_check.py`（本地证据）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.native_worker import action_joint_order  # noqa: E402


class _Term:
    def __init__(self, names) -> None:
        self.target_names = list(names)


class _Manager:
    def __init__(self, terms: dict) -> None:
        self.active_terms = list(terms)
        self._terms = terms

    def get_term(self, name: str):
        return self._terms[name]


class _Scene(dict):
    pass


class _Env:
    def __init__(self, terms=None, entity_joints=None) -> None:
        self.scene = _Scene(robot=type("R", (), {"joint_names": list(entity_joints or [])})())
        self.action_manager = _Manager(terms) if terms else None


class _ContractJoint:
    def __init__(self, name: str) -> None:
        self.name = name


class _Contract:
    def __init__(self, names) -> None:
        self.joints = type("J", (), {"actuated_joints": [_ContractJoint(n) for n in names]})()


class ActionJointOrderTest(unittest.TestCase):
    def test_concatenates_terms_in_term_order(self):
        env = _Env(
            terms={"joint_pos": _Term(["fl_hipx", "fr_hipx"]), "wheel_vel": _Term(["fl_wheel", "fr_wheel"])},
            entity_joints=["fl_hipx", "fl_wheel", "fr_hipx", "fr_wheel"],
        )
        # 动作序 = 腿先轮后；实体序是混排 —— 必须取前者
        self.assertEqual(["fl_hipx", "fr_hipx", "fl_wheel", "fr_wheel"], action_joint_order(env))

    def test_falls_back_to_contract_then_entity(self):
        contract = _Contract(["a", "b"])
        self.assertEqual(["a", "b"], action_joint_order(_Env(entity_joints=["x"]), contract))
        self.assertEqual(["x"], action_joint_order(_Env(entity_joints=["x"])))

    def test_duplicates_are_dropped(self):
        env = _Env(terms={"joint_pos": _Term(["j1"]), "extra": _Term(["j1", "j2"])})
        self.assertEqual(["j1", "j2"], action_joint_order(env))


if __name__ == "__main__":
    unittest.main()
