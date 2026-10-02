"""assembly_emit 回归锁：契约导出是「一套通行」的核心件，导错一个字段就是一次事故重演。"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("assembly_emit", ROOT / "backend" / "assembly_emit.py")
ae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ae)

HYBRID_EFFECTIVE = {
    "environment": {
        "actions": {
            "joint_pos": {"scale": 0.5, "offset": 0.0, "use_default_offset": True,
                          "actuator_names": ["FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
                                             "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
                                             "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
                                             "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint"],
                          "cut_off_frequency": 5.0, "control_frequency": 50.0},
            "wheel_vel": {"scale": 35.0, "use_default_offset": False,
                          "actuator_names": ["FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"],
                          "cut_off_frequency": 15.0, "control_frequency": 50.0},
        },
        "observations": {"actor": {"terms": {
            "base_ang_vel": {"params": {}},
            "projected_gravity": {"params": {}},
            "command": {"params": {}},
            "joint_pos": {"params": {"asset_cfg": {"joint_names": ["x"] * 12}}},
            "joint_vel": {"params": {"asset_cfg": {"joint_names": ["x"] * 12}}},
            "wheel_joint_pos_rel": {"params": {"asset_cfg": {"joint_names": ["w"] * 4}}},
            "wheel_joint_vel_rel": {"params": {"asset_cfg": {"joint_names": ["w"] * 4}}},
            "actions": {"params": {}},
        }}},
        "commands": {"twist": {"ranges": {"lin_vel_x": [-0.5, 1.0], "lin_vel_y": [-0.4, 0.4],
                                          "ang_vel_z": [-1.0, 1.0]}}},
        "curriculum": {"command_vel": {"params": {"velocity_stages": [
            {"step": 0, "lin_vel_x": [-0.5, 1.0], "ang_vel_z": [-1.0, 1.0]}]}}},
    },
}
SNAPSHOT = {"action": {"joint_order": [f"j{i}" for i in range(16)]}}


class EmitAssemblyTest(unittest.TestCase):
    def test_action_terms_carry_mode_scale_cutoffs_per_segment(self):
        out = ae.emit_assembly(HYBRID_EFFECTIVE, SNAPSHOT)
        self.assertIsNotNone(out)
        terms = {t["term"]: t for t in out["action_terms"]}
        legs, wheels = terms["joint_pos"], terms["wheel_vel"]
        self.assertEqual("position", legs["mode"])
        self.assertEqual(0.5, legs["scale"])
        self.assertEqual(5.0, legs["cutoff_hz"])
        self.assertEqual(50.0, legs["control_frequency_hz"])
        self.assertEqual("velocity", wheels["mode"])
        self.assertEqual(35.0, wheels["scale"])
        self.assertEqual(12, len(legs["joints"]))
        self.assertEqual(4, len(wheels["joints"]))

    def test_obs_segments_follow_term_order_with_widths_and_wrap(self):
        out = ae.emit_assembly(HYBRID_EFFECTIVE, SNAPSHOT)
        segs = out["obs_segments"]
        self.assertEqual([s["term"] for s in segs],
                         ["base_ang_vel", "projected_gravity", "command", "joint_pos",
                          "joint_vel", "wheel_joint_pos_rel", "wheel_joint_vel_rel", "actions"])
        widths = {s["term"]: s["width"] for s in segs}
        self.assertEqual(3, widths["base_ang_vel"])
        self.assertEqual(12, widths["joint_pos"])
        self.assertEqual(4, widths["wheel_joint_pos_rel"])
        self.assertEqual(16, widths["actions"])  # 快照动作序长度
        # 轮 pos 段带 wrap 标记（数据如实记录；vel 段不标）
        wrap_flags = {s["term"]: s.get("wrap", False) for s in segs}
        self.assertTrue(wrap_flags["wheel_joint_pos_rel"])
        self.assertFalse(wrap_flags["wheel_joint_vel_rel"])

    def test_command_ranges_and_stages_emitted(self):
        out = ae.emit_assembly(HYBRID_EFFECTIVE, SNAPSHOT)
        self.assertEqual({"lin_vel_x": [-0.5, 1.0], "lin_vel_y": [-0.4, 0.4],
                          "ang_vel_z": [-1.0, 1.0]}, out["command_ranges"])
        self.assertEqual(1, len(out["command_stages"]))

    def test_unrecognizable_structure_returns_none(self):
        self.assertIsNone(ae.emit_assembly({}, SNAPSHOT))
        self.assertIsNone(ae.emit_assembly({"environment": {"actions": {}, "observations": {}}}, SNAPSHOT))


if __name__ == "__main__":
    unittest.main()
