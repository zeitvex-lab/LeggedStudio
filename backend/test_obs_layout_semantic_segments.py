"""声明式布局的**语义筛选**段（2026-09-22 v0.58.0）：`mode` / `zero_velocity_joints`。

## 为什么要这两个选项（不是在堆功能）

布局规格原先只能"**按位置**取关节前 N 个"（`joint_pos` 恒为 `order[:width]`）。而真实契约里
"轮位要清零""非轮 pos 与轮 dq 分列"是**语义**（由 `control_modes` 决定），位置写法能对上
完全靠"腿恰好排在前 12"的巧合——**契约一换序就静默错位**（错得还不报错，策略只是不走路）。
所以把语义补进词汇表，并 **fail-closed**：`mode` 必须显式给 `width`（= 选中关节数），
不符即抛——"猜宽度"正是静默错位的来源。

与 JS `observation_builders.js::applyLayoutSpec` **逐字同规则**；两侧的值级一致性另有
`web/sim2sim/obs/observation_builders.test.mjs` 的同名用例守着（同一张表、两种语言各一份函数，
靠用例把语义钉在一起）。
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "adapters" / "mjlab" / "policy_acceptance.py"


def _load_engine():
    spec = importlib.util.spec_from_file_location("policy_acceptance_for_segments", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeContract:
    """16 关节：前 12 腿（position 控制）+ 后 4 轮（velocity 控制）。"""

    def __init__(self, order, velocity_joints, pos_scale=1.0, vel_scale=0.05):
        self.action_joint_order = list(order)
        self.command_dims = 3
        self.obs_dim = None
        self.ang_vel_scale = 0.25
        self.dof_pos_scale = pos_scale
        self.dof_vel_scale = vel_scale
        self.cmd_scale = (2.0, 2.0, 0.25)
        self._velocity = set(velocity_joints)

    def is_velocity_joint(self, name: str) -> bool:
        return name in self._velocity

    def default_for(self, name: str) -> float:
        return 0.1


class _FakeObs:
    def __init__(self, contract, qpos, qvel, time=0.0):
        self.contract = contract
        self.jadr = {n: (i, i) for i, n in enumerate(contract.action_joint_order)}
        self.data = SimpleNamespace(qpos=np.asarray(qpos, dtype=np.float64),
                                    qvel=np.asarray(qvel, dtype=np.float64), time=time)
        self.last_action = np.zeros(len(contract.action_joint_order), dtype=np.float64)

    def base_state(self):
        """机体系线/角速度：给 `base_lin_vel` 段用（值可辨识，便于断言）。"""
        return None, np.array([0.3, -0.5, 0.2]), np.array([1.5, -2.5, 0.5])


def _setup():
    order = [f"leg{i}_joint" for i in range(12)] + [f"wheel{i}_joint" for i in range(4)]
    contract = _FakeContract(order, velocity_joints=order[12:])
    qpos = np.zeros(16)
    qvel = np.zeros(16)
    for i in range(16):
        qpos[i] = i + 1          # 关节角 = i+1（default 0.1 ⇒ rel = i+0.9）
        qvel[i] = 10.0 * (i + 1)  # dq = 10·(i+1)
    return contract, _FakeObs(contract, qpos, qvel)


class SemanticSegmentTest(unittest.TestCase):
    def setUp(self):
        self.engine = _load_engine()

    def test_zero_velocity_joints(self):
        """`zero_velocity_joints`：宽度不变，速度控制关节写 0（rl_sdk/himloco 57 的口径）。"""
        contract, obs = _setup()
        out = self.engine.frame_from_spec(
            obs, np.zeros(3), [{"source": "joint_pos", "scale": "@contract", "zero_velocity_joints": True}]
        )
        self.assertEqual(16, len(out))
        self.assertAlmostEqual((0 + 1) - 0.1, out[0], places=6)      # 腿：保留
        self.assertAlmostEqual((11 + 1) - 0.1, out[11], places=6)
        self.assertEqual([0.0] * 4, out[12:])                        # 轮：清零

    def test_mode_velocity_picks_wheels(self):
        """`mode=velocity`：按**控制模式**选关节（不是按位置取前 4 个）。"""
        contract, obs = _setup()
        out = self.engine.frame_from_spec(
            obs, np.zeros(3), [{"source": "joint_vel", "mode": "velocity", "width": 4, "scale": "@contract"}]
        )
        self.assertEqual(4, len(out))
        # 选中 wheel0..3 ⇒ dq = 10·(12+1)…10·(15+1)，乘 dof_vel_scale 0.05
        self.assertAlmostEqual(6.5, out[0], places=6)
        self.assertAlmostEqual(8.0, out[3], places=6)

    def test_mode_position_picks_legs(self):
        contract, obs = _setup()
        out = self.engine.frame_from_spec(
            obs, np.zeros(3), [{"source": "joint_vel", "mode": "position", "width": 12, "scale": "@contract"}]
        )
        self.assertEqual(12, len(out))
        self.assertAlmostEqual(0.5, out[0], places=6)
        self.assertAlmostEqual(6.0, out[11], places=6)

    def test_positional_writeup_would_pick_the_wrong_joints(self):
        """**反例注入**：不带 `mode` 的"按位置取前 4 个"取到的是**腿**，与语义结果不同。

        这一条证明上面两个选项不是"换个写法"，而是**修正了一个会静默取错关节的表达方式**。
        """
        contract, obs = _setup()
        positional = self.engine.frame_from_spec(
            obs, np.zeros(3), [{"source": "joint_vel", "width": 4, "scale": "@contract"}]
        )
        semantic = self.engine.frame_from_spec(
            obs, np.zeros(3), [{"source": "joint_vel", "mode": "velocity", "width": 4, "scale": "@contract"}]
        )
        self.assertNotAlmostEqual(positional[0], semantic[0], places=6)
        self.assertAlmostEqual(0.5, positional[0], places=6)   # 位置写法取的是 leg0


class BaseLinVelSegmentTest(unittest.TestCase):
    """`base_lin_vel` 段（2026-09-22 v0.58.0 补）：`go1_playground_48` / `g1_mjswan_locomotion`
    这类"带本体线速度"的帧原先只能手写，单列成段后两侧才都能声明。"""

    def setUp(self):
        self.engine = _load_engine()

    def test_base_lin_vel_is_body_frame_raw(self):
        contract, obs = _setup()
        out = self.engine.frame_from_spec(obs, np.zeros(3), [{"source": "base_lin_vel", "width": 3}])
        self.assertEqual([1.5, -2.5, 0.5], out)

    def test_base_lin_vel_has_no_contract_scale(self):
        """`@contract` 没有对应字段 ⇒ **抛**（不许静默当 1.0 —— 那正是"看着像对"的错法）。"""
        contract, obs = _setup()
        with self.assertRaises(ValueError):
            self.engine.frame_from_spec(
                obs, np.zeros(3), [{"source": "base_lin_vel", "width": 3, "scale": "@contract"}]
            )

    def test_base_lin_vel_scalar_scale(self):
        contract, obs = _setup()
        out = self.engine.frame_from_spec(obs, np.zeros(3), [
            {"source": "base_lin_vel", "width": 3, "scale": 0.5},
        ])
        self.assertEqual([0.75, -1.25, 0.25], out)


class WrapPiSegmentTest(unittest.TestCase):
    """`wrap_pi`（2026-10-04 补）：轮位 ±π 语义进规格——legs-53 从专用 builder 回归声明式。

    语义（与 JS `applyLayoutSpec` 逐字同规则）：值 = `wrap_pi(原始 qpos)`，**不减默认位**；
    只许声明在 `joint_pos` 段上（其他段 fail-closed 不静默忽略）。
    """

    def setUp(self):
        self.engine = _load_engine()

    def test_wrap_pi_wraps_raw_qpos_without_default(self):
        import math

        contract, obs = _setup()
        out = self.engine.frame_from_spec(
            obs, np.zeros(3), [{"source": "joint_pos", "mode": "velocity", "width": 4, "wrap_pi": True}]
        )
        self.assertEqual(4, len(out))
        for i in range(4):
            raw = 12 + i + 1  # 轮 i 的 qpos = 13..16 rad
            self.assertAlmostEqual(math.atan2(math.sin(raw), math.cos(raw)), out[i], places=6)
        # 与"减默认位"路径可区分：wrap 值 ≠ raw - 0.1（default_for 的返回）
        self.assertNotAlmostEqual(raw - 0.1, out[3], places=3)

    def test_wrap_pi_on_non_joint_pos_raises(self):
        contract, obs = _setup()
        with self.assertRaises(ValueError) as ctx:
            self.engine.frame_from_spec(
                obs, np.zeros(3), [{"source": "joint_vel", "mode": "velocity", "width": 4, "wrap_pi": True}]
            )
        self.assertIn("wrap_pi", str(ctx.exception))

    def test_wrap_pi_respects_scale(self):
        import math

        contract, obs = _setup()
        out = self.engine.frame_from_spec(
            obs, np.zeros(3),
            [{"source": "joint_pos", "mode": "velocity", "width": 4, "wrap_pi": True, "scale": 2.0}],
        )
        raw = 16
        self.assertAlmostEqual(math.atan2(math.sin(raw), math.cos(raw)) * 2.0, out[3], places=6)


class SemanticSegmentFailClosedTest(unittest.TestCase):
    """定位不了就抛：宽度不猜、未实现的模式不许静默当 position。"""

    def setUp(self):
        self.engine = _load_engine()

    def _run(self, seg):
        contract, obs = _setup()
        return self.engine.frame_from_spec(obs, np.zeros(3), [seg])

    def test_mode_without_width_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._run({"source": "joint_vel", "mode": "velocity"})
        self.assertIn("必须显式给 width", str(ctx.exception))

    def test_width_mismatch_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._run({"source": "joint_vel", "mode": "velocity", "width": 5})
        self.assertIn("选中的关节数", str(ctx.exception))

    def test_torque_mode_not_implemented_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._run({"source": "joint_vel", "mode": "torque", "width": 16})
        self.assertIn("torque", str(ctx.exception))


class MigratedWheelLegLayoutsTest(unittest.TestCase):
    """数据面回归：本轮迁移的 12 条策略，规格里的"选中关节数"必须与**契约真值**相符。

    这些正是"位置写法能对上、但语义写法才对"的那批：`zero_velocity_joints` 用于
    `go2w_rl_sdk_57` / `go2w_himloco_57`，`mode` 分列用于 `zexw_53`。
    """

    #: 本轮迁移的 kind → **声明了布局规格的策略条数**（数量变了就得回来看一眼：
    #: 是不是有人把规格悄悄撤回、只留下"两份实现还能对上"的假绿）
    EXPECTED = {
        "go2w_rl_sdk_57": 4,
        "go2w_himloco_57": 4,
        "zexw_53": 4,
    }

    def setUp(self):
        spec = importlib.util.spec_from_file_location("policy_acceptance_for_migrated", ENGINE_PATH)
        self.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.engine)

    def _policies(self):
        for config_path in sorted((ROOT / "assets" / "robots").glob("*/simulation/config.json")):
            robot = config_path.parents[1].name
            cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
            for entry in cfg.get("policies") or []:
                if isinstance(entry, dict) and (entry.get("contract") or {}).get("observation_layout"):
                    yield robot, config_path.parents[1], entry

    def test_semantic_segments_match_contract(self):
        seen = {kind: 0 for kind in self.EXPECTED}
        for robot, package_dir, entry in self._policies():
            contract = entry["contract"]
            kind = contract.get("observation_kind")
            if kind not in self.EXPECTED:
                continue
            seen[kind] += 1
            engine_contract = self.engine.PackageContract(package_dir, entry)
            engine_contract.motion_loader = None
            order = engine_contract.action_joint_order
            velocity = [n for n in order if engine_contract.is_velocity_joint(n)]
            for seg in contract["observation_layout"]:
                if seg.get("zero_velocity_joints"):
                    self.assertTrue(velocity, f"{robot}/{entry['id']}：契约里没有速度控制关节，"
                                              f"zero_velocity_joints 是空操作（规格写错了？）")
                if seg.get("mode") == "velocity":
                    self.assertEqual(len(velocity), int(seg["width"]),
                                     f"{robot}/{entry['id']}：width≠速度关节数")
                if seg.get("mode") == "position":
                    self.assertEqual(len(order) - len(velocity), int(seg["width"]),
                                     f"{robot}/{entry['id']}：width≠非速度关节数")
        for kind, count in self.EXPECTED.items():
            self.assertEqual(count, seen[kind], f"{kind} 迁移条数变了（{kind}: {seen[kind]}）")


if __name__ == "__main__":
    unittest.main()
