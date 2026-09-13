"""L1 / G2：确定性回放判据测试（`adapters/mjlab/replay_determinism.py`）。

守什么：

1. **同执行器重跑**默认容差为 0：差一位就必须红，且要给出「哪个 stepIndex / 哪一维 / 两侧取值」；
2. **帧数不等**、**obs 维度不等**、**空日志**都必须 fail-closed（不许"少比几帧就算过"）；
3. **min_frames** 门槛：只比初始两三帧不算通过（"没走出初始态的一致"没有说服力）；
4. **stepIndex 对齐**：两侧墙钟不同、帧序不同也能对齐；没有 stepIndex 时退回按位置比；
5. **跨执行器口径**（WASM vs 原生）用显式容差，小差放行——此时判的是"链路一致"，不是"确定性"。
"""

from __future__ import annotations

import unittest

from adapters.mjlab.replay_determinism import (
    CROSS_EXECUTOR_TOLERANCE,
    DEFAULT_TOLERANCE,
    compare_frame_logs,
    determinism_verdict,
    iter_obs_rows,
    summarize,
)


def frames(count: int = 60, *, bump_at: int | None = None, bump_dim: int = 1, bump: float = 0.02):
    rows = []
    for step in range(1, count + 1):
        obs = [step * 0.1, 0.0, 1.0]
        if bump_at is not None and step == bump_at:
            obs[bump_dim] += bump
        rows.append({"stepIndex": step, "t": step * 0.02, "obs": obs})
    return rows


class CompareFrameLogsTests(unittest.TestCase):
    def test_identical_logs_pass_with_zero_tolerance(self):
        result = compare_frame_logs(frames(), frames())
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["reason"], "identical")
        self.assertEqual(result["max_delta"], 0.0)
        self.assertEqual(result["alignment"], "step_index")
        self.assertIsNone(result["first_divergence"])
        self.assertEqual(DEFAULT_TOLERANCE, 0.0)

    def test_single_dim_bump_fails_with_actionable_divergence(self):
        result = compare_frame_logs(frames(), frames(bump_at=31))
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["reason"], "obs_divergence")
        first = result["first_divergence"]
        self.assertEqual(first["step_index"], 31)
        self.assertEqual(first["dim"], 1)
        self.assertAlmostEqual(first["delta"], 0.02, places=6)
        self.assertEqual(first["a"], 0.0)
        self.assertEqual(first["b"], 0.02)
        self.assertEqual(result["mismatched_frames"], 1)

    def test_length_mismatch_is_fail_closed(self):
        result = compare_frame_logs(frames(60), frames(59))
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["reason"], "length_mismatch")
        self.assertEqual(result["length_mismatch"], {"a": 60, "b": 59})

    def test_obs_dim_mismatch_reported(self):
        shorter = frames(3)
        for frame in shorter:
            frame["obs"] = frame["obs"][:2]
        result = compare_frame_logs(frames(3), shorter)
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["first_divergence"]["reason"], "obs_dim_mismatch")

    def test_empty_log_fails(self):
        self.assertEqual(compare_frame_logs([], frames())["reason"], "empty")
        self.assertEqual(compare_frame_logs({"frames": []}, frames())["reason"], "empty")

    def test_step_index_alignment_survives_shuffled_input(self):
        result = compare_frame_logs(list(reversed(frames())), frames())
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["alignment"], "step_index")

    def test_missing_step_index_falls_back_to_position(self):
        plain = [{"obs": [1.0, 2.0]} for _ in range(4)]
        result = compare_frame_logs(plain, [{"obs": [1.0, 2.0]} for _ in range(4)])
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["alignment"], "position")

    def test_missing_frames_field_raises(self):
        with self.assertRaises(ValueError):
            compare_frame_logs({"nope": 1}, frames())

    def test_cross_executor_tolerance_lets_small_delta_through(self):
        result = compare_frame_logs(frames(), frames(bump_at=31, bump=1e-3),
                                    tolerance=CROSS_EXECUTOR_TOLERANCE)
        self.assertEqual(result["verdict"], "pass")
        self.assertGreater(result["max_delta"], 0.0)

    def test_accepts_dict_wrapped_logs(self):
        result = compare_frame_logs({"frames": frames()}, {"frame_log": frames()})
        self.assertEqual(result["verdict"], "pass")

    def test_skipped_step_indices_are_reported(self):
        partial = frames()[10:]
        result = compare_frame_logs(frames(), partial)
        self.assertEqual(result["verdict"], "fail")  # 帧数不等
        self.assertEqual(len(result["skipped"]), 10)


class DeterminismVerdictTests(unittest.TestCase):
    def test_min_frames_guard(self):
        result = determinism_verdict(frames(3), frames(3), min_frames=50)
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["reason"], "too_few_frames")
        self.assertEqual(result["required_frames"], 50)

    def test_min_frames_satisfied_passes(self):
        self.assertEqual(determinism_verdict(frames(60), frames(60), min_frames=50)["verdict"], "pass")

    def test_summarize_mentions_verdict_and_divergence(self):
        passed = summarize(determinism_verdict(frames(5), frames(5)))
        failed = summarize(determinism_verdict(frames(5), frames(5, bump_at=2)))
        self.assertIn("PASS", passed)
        self.assertIn("FAIL", failed)
        self.assertIn("stepIndex=2", failed)

    def test_iter_obs_rows_helper(self):
        rows = iter_obs_rows(frames(2))
        self.assertEqual(rows, [[0.1, 0.0, 1.0], [0.2, 0.0, 1.0]])


if __name__ == "__main__":
    unittest.main()
