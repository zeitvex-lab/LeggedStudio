# -*- coding: utf-8 -*-
"""N1 离线模仿数据层的回归锁（`adapters/mjlab/toolchain/motion_io.py`）。

守三件事：

1. **两种格式都读得对**（CSV 表头/时间列/纯数值；NPZ 三档帧键与元数据）；
2. **关节列校验的判据**：缺列 / 多列 / **顺序不同**（最阴的一类）/ 无列名如实报
   —— 全部反例注入；
3. **fail-loud**：坏文件抛 ``MotionIOError``，不静默给个空数组继续跑。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.toolchain.motion_io import (  # noqa: E402
    MotionIOError,
    calibrate,
    joint_column_problems,
    load_motion,
)

ORDER = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip"]


def _csv(path: Path, header: list[str] | None, rows: list[list[float]]) -> Path:
    lines = ([",".join(header)] if header else [])
    lines += [",".join(str(value) for value in row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class CsvImportTest(unittest.TestCase):
    def test_header_names_and_time_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _csv(Path(tmp) / "a.csv", ["time", *ORDER], [[0.0, 1, 2, 3, 4]] * 5)
            motion = load_motion(path)
        self.assertEqual(ORDER, motion.joint_names, "time 列必须被丢掉")
        self.assertEqual((5, 4), motion.frames.shape)
        self.assertEqual("csv", motion.fmt)

    def test_headerless_csv_has_no_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _csv(Path(tmp) / "b.csv", None, [[0.0, 1, 2, 3]] * 3)
            motion = load_motion(path)
        self.assertIsNone(motion.joint_names, "纯数值表不该被当成有列名")
        self.assertEqual((3, 4), motion.frames.shape)

    def test_explicit_fps_and_default_fps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _csv(Path(tmp) / "c.csv", ORDER, [[0.0] * 4] * 2)
            self.assertEqual(30.0, load_motion(path, fps=30.0).fps)
            self.assertEqual(50.0, load_motion(path).fps)

    def test_empty_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(MotionIOError):
                load_motion(path)

    def test_non_numeric_body_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("FL_hip,FL_thigh\n1.0,oops\n", encoding="utf-8")
            with self.assertRaises(MotionIOError):
                load_motion(path)


class NpzImportTest(unittest.TestCase):
    def test_frames_key_with_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.npz"
            np.savez(path, frames=np.zeros((6, 4)), joint_names=np.array(ORDER), fps=np.array(30.0))
            motion = load_motion(path)
        self.assertEqual((6, 4), motion.frames.shape)
        self.assertEqual(ORDER, motion.joint_names)
        self.assertEqual(30.0, motion.fps)
        self.assertEqual("npz", motion.fmt)

    def test_frame_key_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("joint_pos", "dof_pos", "qpos"):
                path = Path(tmp) / f"{key}.npz"
                np.savez(path, **{key: np.zeros((2, 4))})
                with self.subTest(key=key):
                    self.assertEqual((2, 4), load_motion(path).frames.shape)

    def test_missing_frame_array_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.npz"
            np.savez(path, unrelated=np.zeros((2, 2)))
            with self.assertRaises(MotionIOError):
                load_motion(path)

    def test_name_count_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.npz"
            np.savez(path, frames=np.zeros((2, 4)), joint_names=np.array(ORDER[:2]))
            with self.assertRaises(MotionIOError):
                load_motion(path)

    def test_unknown_suffix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.txt"
            path.write_text("x", encoding="utf-8")
            with self.assertRaises(MotionIOError):
                load_motion(path)


class JointColumnRuleTest(unittest.TestCase):
    def test_same_order_passes(self):
        self.assertEqual([], joint_column_problems(ORDER, ORDER))

    def test_missing_column_is_caught(self):
        problems = joint_column_problems(ORDER[:3], ORDER)
        self.assertTrue(any("缺关节列" in p for p in problems), problems)

    def test_extra_column_is_caught(self):
        problems = joint_column_problems([*ORDER, "spare"], ORDER)
        self.assertTrue(any("多出来路不明" in p for p in problems), problems)

    def test_same_set_different_order_is_caught(self):
        """最阴的一类：集合相同、顺序不同 —— 能跑但不报错，训出来是错位的。"""
        swapped = [ORDER[1], ORDER[0], *ORDER[2:]]
        problems = joint_column_problems(swapped, ORDER)
        self.assertTrue(any("顺序不同" in p for p in problems), problems)

    def test_no_names_is_reported_not_guessed(self):
        problems = joint_column_problems(None, ORDER)
        self.assertTrue(any("没有关节列名" in p for p in problems), problems)

    def test_empty_expected_order_is_reported(self):
        self.assertTrue(joint_column_problems(ORDER, []))


class CalibrateReportTest(unittest.TestCase):
    def test_report_shape_and_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _csv(Path(tmp) / "a.csv", ORDER, [[0.0] * 4] * 4)
            report = calibrate(path, expected_order=ORDER)
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(4, report["frames"])
        self.assertEqual(4, report["dof_dim"])
        self.assertTrue(report["has_joint_names"])
        self.assertEqual(ORDER, report["checked_against"])

    def test_report_flags_order_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _csv(Path(tmp) / "b.csv", [ORDER[1], ORDER[0], *ORDER[2:]], [[0.0] * 4] * 4)
            report = calibrate(path, expected_order=ORDER)
        self.assertFalse(report["ok"])
        self.assertTrue(any("顺序不同" in p for p in report["problems"]))

    def test_without_expected_order_only_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _csv(Path(tmp) / "c.csv", [ORDER[1], ORDER[0], *ORDER[2:]], [[0.0] * 4] * 2)
            report = calibrate(path)
        self.assertTrue(report["ok"], "不传基准时只导入，不判列序")
        self.assertIsNone(report["checked_against"])


if __name__ == "__main__":
    unittest.main()
