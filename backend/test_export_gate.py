"""T0.4 DoD：导出双 gate（DENYLIST fail-closed）单元测试。

- 改坏 action_scale / joint_order / obs_groups / control_hz / armature → 拒绝（blocker）
- reward_scales / decimation 不一致 → 仅警告（仍放行）
- **K3 起收紧**：DENYLIST 字段"一侧有值一侧缺失"（不对称）→ 拒绝（fail-closed），
  旧行为是降级成 warning 后放行；两侧都缺才算"与本契约无关"，仅记 warning
- check_export_result：形状漂移与数值超阈值 → 拒绝；正常 → 放行
"""

from __future__ import annotations

import unittest

from backend.export_gate import REPLAY_DIFF_THRESHOLD, check_export_result, compare_contracts


def go2_snapshot() -> dict:
    return {
        "schema_version": "robot-contract-3.0",
        "robot_id": "unitree_go2",
        "action": {
            "joint_order": [
                "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
                "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
                "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
                "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
            ],
            "action_scale": 0.25,
            "reindex_from_model": None,
        },
        "observation": {
            "dimension": 48,
            "components": [
                {"name": "base_lin_vel", "width": 3, "source": "imu"},
                {"name": "base_ang_vel", "width": 3, "source": "imu"},
                {"name": "projected_gravity", "width": 3, "source": "imu"},
                {"name": "velocity_command", "width": 3, "source": "cmd"},
                {"name": "joint_pos", "width": 12, "source": "actuated"},
                {"name": "joint_vel", "width": 12, "source": "actuated"},
                {"name": "last_action", "width": 12, "source": "action"},
            ],
        },
        "control": {"control_hz": 50, "physics_hz": 500, "decimation": 10},
        "actuator_profile": {
            "by_role": {
                "hip": {"stiffness": 20.0, "damping": 0.5, "effort": 23.7, "armature": 0.01, "mode": "torque"},
                "thigh": {"stiffness": 20.0, "damping": 0.5, "effort": 23.7, "armature": 0.01, "mode": "torque"},
                "calf": {"stiffness": 20.0, "damping": 0.5, "effort": 35.55, "armature": 0.02, "mode": "torque"},
            }
        },
        "reward_scales": {"track_linear_velocity": 1.0, "action_rate_l2": -0.05},
    }


class DenylistGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = go2_snapshot()
        self.current = go2_snapshot()

    def test_identical_contracts_pass(self) -> None:
        report = compare_contracts(self.snapshot, self.current)
        self.assertTrue(report["ok"])
        self.assertEqual(report["blockers"], [])

    def test_action_scale_mismatch_blocks(self) -> None:
        self.current["action"]["action_scale"] = 0.5
        report = compare_contracts(self.snapshot, self.current)
        self.assertFalse(report["ok"])
        self.assertTrue(any("action.action_scale" in item for item in report["blockers"]))
        # 中文三段式：原因 + 后续动作
        self.assertIn("拒绝", report["blockers"][0])
        self.assertIn("回训练区", report["blockers"][0])

    def test_joint_order_swap_blocks(self) -> None:
        order = self.current["action"]["joint_order"]
        order[0], order[1] = order[1], order[0]
        report = compare_contracts(self.snapshot, self.current)
        self.assertFalse(report["ok"])
        self.assertTrue(any("joint_order" in item for item in report["blockers"]))

    def test_obs_group_width_change_blocks(self) -> None:
        self.current["observation"]["components"][3]["width"] = 4
        report = compare_contracts(self.snapshot, self.current)
        self.assertFalse(report["ok"])
        self.assertTrue(any("observation.components" in item for item in report["blockers"]))

    def test_control_hz_mismatch_blocks(self) -> None:
        self.current["control"]["control_hz"] = 100
        report = compare_contracts(self.snapshot, self.current)
        self.assertFalse(report["ok"])
        self.assertTrue(any("control.control_hz" in item for item in report["blockers"]))

    def test_armature_mismatch_blocks(self) -> None:
        self.current["actuator_profile"]["by_role"]["calf"]["armature"] = 0.03
        report = compare_contracts(self.snapshot, self.current)
        self.assertFalse(report["ok"])
        self.assertTrue(any("actuator_profile" in item for item in report["blockers"]))
        self.assertTrue(any("calf" in item for item in report["blockers"]))

    def test_reward_scale_mismatch_is_warning_only(self) -> None:
        self.current["reward_scales"]["track_linear_velocity"] = 2.0
        report = compare_contracts(self.snapshot, self.current)
        self.assertTrue(report["ok"])
        self.assertTrue(any("reward_scales" in item for item in report["warnings"]))

    def test_decimation_mismatch_is_warning_only(self) -> None:
        self.current["control"]["decimation"] = 20
        report = compare_contracts(self.snapshot, self.current)
        self.assertTrue(report["ok"])
        self.assertTrue(any("decimation" in item for item in report["warnings"]))

    def test_asymmetric_denylist_fields_fail_closed(self) -> None:
        """K3：一侧有值、一侧缺失 = 无法验证 → 拒绝（旧行为是降级 warning 后放行）。"""
        report = compare_contracts({"action": {}}, self.current)
        self.assertFalse(report["ok"])
        self.assertEqual(report["disposition"], "deny")
        self.assertTrue(any("不对称" in item for item in report["blockers"]))
        self.assertTrue(any("fail-closed" in item for item in report["blockers"]))

    def test_both_sides_missing_field_is_only_a_warning(self) -> None:
        """两侧都没声明该字段 = 与本契约无关，记 warning 但不阻断。"""
        report = compare_contracts({"action": {}}, {"action": {}})
        self.assertTrue(report["ok"])
        self.assertEqual(report["disposition"], "warn")
        self.assertTrue(any("两侧均未声明" in item for item in report["warnings"]))


class ShapeNumericGateTest(unittest.TestCase):
    class _Result:
        def __init__(self, input_shape, output_shape, max_diff):
            self.input_shape = input_shape
            self.output_shape = output_shape
            self.max_numerical_diff = max_diff

    def test_good_result_passes(self) -> None:
        report = check_export_result(self._Result([1, 48], [1, 12], 1e-7), 48, 12)
        self.assertTrue(report["ok"])

    def test_obs_dim_drift_blocks(self) -> None:
        report = check_export_result(self._Result([1, 45], [1, 12], 1e-7), 48, 12)
        self.assertFalse(report["ok"])
        self.assertTrue(any("obs_dim" in item for item in report["blockers"]))

    def test_numeric_drift_blocks(self) -> None:
        report = check_export_result(self._Result([1, 48], [1, 12], 1e-3), 48, 12)
        self.assertFalse(report["ok"])
        self.assertTrue(any("数值回放" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
