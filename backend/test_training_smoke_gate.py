"""冒烟前置门（E8）：**未过冒烟不能长训**。

门的两条设计要点，各有测试守：

1. **证据＝已有事实的组合**（B9 的 `resolved-config.json` 指纹 + 任务状态），不另造记录；
2. **门挂在输入指纹上** —— 配置改一个字就派生新指纹，于是"改了配置却沿用旧冒烟结论"
   在结构上不可能（这是把门挂在 B9 上换来的性质）。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.training import smoke_gate

DIGEST = "a" * 64


class ScaleTest(unittest.TestCase):
    def test_smoke_scale_is_inclusive_at_the_boundary(self):
        self.assertTrue(smoke_gate.is_smoke_scale({"num_envs": 64, "max_iterations": 5}))
        self.assertTrue(smoke_gate.is_smoke_scale({"num_envs": 8, "max_iterations": 1}))

    def test_long_run_is_not_smoke_scale(self):
        self.assertFalse(smoke_gate.is_smoke_scale({"num_envs": 4096, "max_iterations": 300}))
        self.assertFalse(smoke_gate.is_smoke_scale({"num_envs": 65, "max_iterations": 5}))
        self.assertFalse(smoke_gate.is_smoke_scale({"num_envs": 64, "max_iterations": 6}))


class EvidenceTest(unittest.TestCase):
    """证据链：只有「同指纹 + 冒烟档 + 已完成」三个条件同时成立才算通过。"""

    @staticmethod
    def _task(root: Path, name: str, *, digest: str, smoke: bool, status: str) -> tuple:
        task_dir = root / name
        task_dir.mkdir(parents=True)
        (task_dir / "resolved-config.json").write_text(
            json.dumps({
                "schema": "run-1.0",
                "inputs": {
                    "digest": digest,
                    "seed": 7,
                    "params": {"smoke_preset": smoke, "num_envs": 64, "max_iterations": 5},
                },
            }),
            encoding="utf-8",
        )
        return (status, task_dir)

    def test_completed_smoke_run_is_accepted_as_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._task(root, "smoke-1", digest=DIGEST, smoke=True, status="completed")
            evidence = smoke_gate.smoke_evidence(DIGEST, [candidate])
            self.assertIsNotNone(evidence)
            self.assertEqual("smoke-1", evidence["run_id"])
            self.assertEqual(7, evidence["seed"])

    def test_long_run_cannot_be_its_own_smoke_evidence(self):
        """长训自己不能给自己当冒烟证据 —— 否则门形同不存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._task(root, "long-1", digest=DIGEST, smoke=False, status="completed")
            self.assertIsNone(smoke_gate.smoke_evidence(DIGEST, [candidate]))

    def test_unfinished_run_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for status in ("running", "failed", "stopped", "pending"):
                with self.subTest(status=status):
                    candidate = self._task(root, f"t-{status}", digest=DIGEST, smoke=True, status=status)
                    self.assertIsNone(smoke_gate.smoke_evidence(DIGEST, [candidate]))

    def test_different_digest_is_not_evidence(self):
        """**核心性质**：配置改一个字 → 指纹变 → 旧冒烟结论不成立。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._task(root, "smoke-1", digest="b" * 64, smoke=True, status="completed")
            self.assertIsNone(smoke_gate.smoke_evidence(DIGEST, [candidate]))


class CheckTest(unittest.TestCase):
    def test_smoke_scale_run_needs_no_gate(self):
        result = smoke_gate.check(digest=DIGEST, config={"num_envs": 64, "max_iterations": 5})
        self.assertFalse(result["required"])
        self.assertTrue(result["ok"])
        self.assertFalse(result["bypassed"])

    def test_long_run_without_evidence_is_refused_with_actionable_reason(self):
        result = smoke_gate.check(
            digest=DIGEST, config={"num_envs": 4096, "max_iterations": 300},
        )
        self.assertTrue(result["required"])
        self.assertFalse(result["ok"])
        self.assertIn("冒烟", result["reason"])
        self.assertIn("64 envs × 5 iters", result["reason"])
        self.assertIn(DIGEST[:12], result["reason"])       # 报出指纹，便于对账

    def test_long_run_with_evidence_passes_and_names_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = EvidenceTest._task(
                root, "smoke-9", digest=DIGEST, smoke=True, status="completed",
            )
            result = smoke_gate.check(
                digest=DIGEST, config={"num_envs": 4096, "max_iterations": 300},
                candidates=[candidate],
            )
            self.assertTrue(result["ok"])
            self.assertIn("smoke-9", result["reason"])

    def test_bypass_is_visible_never_silent(self):
        """绕过必须**如实标注**（CI/合成配置用），不能伪装成"冒烟通过了"。"""
        result = smoke_gate.check(
            digest=DIGEST, config={"num_envs": 4096, "max_iterations": 300}, bypass=True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["bypassed"])
        self.assertIsNone(result["evidence"])
        self.assertIn(smoke_gate.BYPASS_ENV, result["reason"])

    def test_env_bypass_only_on_explicit_falsey_values(self):
        for value, expected_bypass in (("0", True), ("false", True), ("1", False), ("", False)):
            with self.subTest(env=value):
                os.environ[smoke_gate.BYPASS_ENV] = value
                try:
                    result = smoke_gate.check(
                        digest=DIGEST, config={"num_envs": 4096, "max_iterations": 300},
                    )
                finally:
                    os.environ.pop(smoke_gate.BYPASS_ENV, None)
                self.assertEqual(expected_bypass, result["bypassed"])
                self.assertEqual(not expected_bypass, not result["ok"])


if __name__ == "__main__":
    unittest.main()
