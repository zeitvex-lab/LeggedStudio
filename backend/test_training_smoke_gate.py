"""冒烟前置门（E8）：**未过冒烟不能长训**。

门的设计要点，各有测试守：

1. **证据＝已有事实的组合**（B9 的 ``resolved-config.json`` 输入档案 + 任务状态），
   不另造记录；
2. **门挂在输入指纹上，但按"规范化比对"** ——「同配置」指除规模三元组
   （``num_envs`` / ``max_iterations`` / ``smoke_preset``）外**逐键一致**：
   冒烟档必然把规模钳到 64×5，逐字节相等会让门对一切真长训永远 409（本缺陷的
   修复语义）；而规模之外改一个字（seed / recipe / overrides / …）就换摘要，
   "改了配置却沿用旧冒烟结论"在结构上不可能。旧测试里「精确 digest 相等」的
   断言已按此语义更新：规模不同不再阻断，非规模键不同仍然阻断；
3. 完成态词表须覆盖 worker 实际写的 ``train_completed``
   （adapters/mjlab/native_worker.py），不只是 ``completed``。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.training import smoke_gate
from backend.training.runs import run_inputs_from_task

CONTRACT_HASH = "c" * 64


def _resolved_recipe(config: dict) -> dict:
    """镜像 resolve_recipe 的产出形状：规模键会**派生**进 environment / algorithm_config。"""
    return {
        "task_name": config["task_name"],
        "algorithm": config["algorithm"],
        "backend": config.get("backend", "native_mjlab"),
        "reward_scales": {"tracking_lin_vel": 1.0},
        "environment": {
            "num_envs": config["num_envs"],
            "episode_length_s": 20.0,
            "terrain_type": config["terrain_type"],
        },
        "algorithm_config": {
            key: value for key, value in config.items()
            if key not in {"task_name", "algorithm", "reward_scales", "num_envs",
                           "episode_length_s", "terrain_type", "resolved_recipe"}
        },
        "seed": config["seed"],
    }


def _config(**overrides):
    """与 create.py 的 config 键集对齐的最小合成配置（长训语义：smoke_preset=False）。"""
    base = {
        "algorithm": "PPO",
        "smoke_preset": False,
        "num_envs": 16,
        "max_iterations": 15,
        "task_name": "forward_walk",
        "profile_id": "go2-velocity-flat",
        "terrain_type": "plane",
        "device": "auto",
        "backend": "native_mjlab",
        "seed": 7,
        "overrides": {},
    }
    base.update(overrides)
    if "resolved_recipe" not in overrides:
        base["resolved_recipe"] = _resolved_recipe(base)
    return base


def _long_inputs(**overrides):
    """本次长训的完整输入四元组（与 create.py 同一条产线：run_inputs_from_task）。"""
    return run_inputs_from_task(contract_hash=CONTRACT_HASH, config=_config(**overrides))


def _smoke_task(root: Path, name: str, *, config_overrides: dict | None = None,
                status: str = "train_completed", seed: int = 7) -> tuple:
    """落一个「已完成冒烟 Run」目录：规模按 create.py 冒烟钳制（16×5 + smoke_preset=True）。"""
    config = _config(num_envs=16, max_iterations=5, smoke_preset=True, seed=seed)
    config.update(config_overrides or {})
    inputs = run_inputs_from_task(contract_hash=CONTRACT_HASH, config=config)
    task_dir = root / name
    task_dir.mkdir(parents=True)
    (task_dir / "resolved-config.json").write_text(
        json.dumps({"schema": "training-run-1.0", "inputs": inputs}, ensure_ascii=False),
        encoding="utf-8",
    )
    return (status, task_dir)


class ScaleTest(unittest.TestCase):
    def test_smoke_scale_is_inclusive_at_the_boundary(self):
        self.assertTrue(smoke_gate.is_smoke_scale({"num_envs": 64, "max_iterations": 5}))
        self.assertTrue(smoke_gate.is_smoke_scale({"num_envs": 8, "max_iterations": 1}))

    def test_long_run_is_not_smoke_scale(self):
        self.assertFalse(smoke_gate.is_smoke_scale({"num_envs": 4096, "max_iterations": 300}))
        self.assertFalse(smoke_gate.is_smoke_scale({"num_envs": 65, "max_iterations": 5}))
        self.assertFalse(smoke_gate.is_smoke_scale({"num_envs": 64, "max_iterations": 6}))


class MatchDigestTest(unittest.TestCase):
    """规范化摘要本身：只剔规模三元组，其余一键都算数。"""

    def test_scale_only_difference_shares_match_digest(self):
        """规模三元组不同 → 规范化摘要一致（这正是门要放行的"同配置"）。"""
        smoke = _long_inputs(num_envs=16, max_iterations=5, smoke_preset=True)
        long_ = _long_inputs()
        self.assertNotEqual(smoke["digest"], long_["digest"])  # 整档指纹确实不同
        self.assertEqual(
            smoke_gate._match_digest(smoke), smoke_gate._match_digest(long_),
        )

    def test_match_digest_reuses_runs_canonical_digest(self):
        """不发明第二种摘要：规范化摘要必须由 runs.canonical_digest 直接产出。"""
        import hashlib

        inputs = _long_inputs()
        strip = lambda m: {k: v for k, v in m.items() if k not in smoke_gate.SCALE_KEYS}
        body = {k: v for k, v in inputs.items() if k != "digest"}
        body["params"] = strip(body["params"])
        recipe = dict(body["recipe"])
        recipe["environment"] = strip(recipe["environment"])
        recipe["algorithm_config"] = strip(recipe["algorithm_config"])
        body["recipe"] = recipe
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(
            smoke_gate._match_digest(inputs),
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )


class EvidenceTest(unittest.TestCase):
    """证据链：只有「同配置（规模除外） + 冒烟档 + 已完成」三个条件同时成立才算通过。"""

    def test_same_config_smoke_run_is_evidence_for_long_run(self):
        """**修复的核心场景**：长训 16×15 的证据是 16×5 的冒烟（其余键全同）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = _smoke_task(root, "smoke-1")
            evidence = smoke_gate.smoke_evidence(_long_inputs(), [candidate])
            self.assertIsNotNone(evidence)
            self.assertEqual("smoke-1", evidence["run_id"])
            self.assertEqual(7, evidence["seed"])
            self.assertEqual(16, evidence["num_envs"])
            self.assertEqual(5, evidence["iterations"])

    def test_smoke_with_different_seed_is_not_evidence(self):
        """指纹含 seed（inputs 顶层键）：seed 不同仍 409，规范化只剔规模三元组。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = _smoke_task(root, "smoke-seed7", seed=7)
            self.assertIsNone(smoke_gate.smoke_evidence(_long_inputs(seed=8), [candidate]))

    def test_smoke_with_different_recipe_is_not_evidence(self):
        """recipe 的非规模键（reward_scales）有差 → 规范化摘要不同 → 旧冒烟结论不成立。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = _resolved_recipe(_config(num_envs=16, max_iterations=5, smoke_preset=True))
            recipe["reward_scales"] = {"tracking_lin_vel": 2.0}
            candidate = _smoke_task(root, "smoke-recipe", config_overrides={
                "resolved_recipe": recipe,
            })
            self.assertIsNone(smoke_gate.smoke_evidence(_long_inputs(), [candidate]))

    def test_smoke_with_different_overrides_is_not_evidence(self):
        """overrides 有差（params 内的非规模键）→ 仍 409。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = _smoke_task(root, "smoke-overrides", config_overrides={
                "overrides": {"environment.sim.mujoco.timestep": 0.002},
            })
            self.assertIsNone(smoke_gate.smoke_evidence(_long_inputs(), [candidate]))

    def test_long_run_cannot_be_its_own_smoke_evidence(self):
        """长训自己不能给自己当冒烟证据 —— 否则门形同不存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = _smoke_task(root, "long-1", config_overrides={
                "smoke_preset": False, "max_iterations": 15,
            })
            self.assertIsNone(smoke_gate.smoke_evidence(_long_inputs(), [candidate]))

    def test_unfinished_run_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for status in ("running", "failed", "stopped", "pending"):
                with self.subTest(status=status):
                    candidate = _smoke_task(root, f"t-{status}", status=status)
                    self.assertIsNone(smoke_gate.smoke_evidence(_long_inputs(), [candidate]))

    def test_worker_completion_vocabulary_is_accepted(self):
        """worker 实际写的完成词表（train_completed）与 completed 同样算"已完成"。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for status in ("completed", "train_completed"):
                with self.subTest(status=status):
                    candidate = _smoke_task(root, f"t-{status}", status=status)
                    self.assertIsNotNone(smoke_gate.smoke_evidence(_long_inputs(), [candidate]))


class CheckTest(unittest.TestCase):
    def test_smoke_scale_run_needs_no_gate(self):
        """回归：冒烟档自身的请求 required=False（它自己就是冒烟）。"""
        result = smoke_gate.check(
            inputs=_long_inputs(num_envs=16, max_iterations=5, smoke_preset=True),
            config={"num_envs": 16, "max_iterations": 5},
        )
        self.assertFalse(result["required"])
        self.assertTrue(result["ok"])
        self.assertFalse(result["bypassed"])

    def test_long_run_without_evidence_is_refused_with_actionable_reason(self):
        inputs = _long_inputs()
        result = smoke_gate.check(
            inputs=inputs, config={"num_envs": 16, "max_iterations": 15},
        )
        self.assertTrue(result["required"])
        self.assertFalse(result["ok"])
        self.assertIn("冒烟", result["reason"])
        self.assertIn("64 envs × 5 iters", result["reason"])
        self.assertIn("规模与 save_interval 外需逐键一致", result["reason"])
        self.assertIn(inputs["digest"][:12], result["reason"])  # 报出指纹，便于对账

    def test_long_run_with_same_config_smoke_passes_and_names_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = _smoke_task(root, "smoke-9")
            result = smoke_gate.check(
                inputs=_long_inputs(), config={"num_envs": 16, "max_iterations": 15},
                candidates=[candidate],
            )
            self.assertTrue(result["required"])
            self.assertTrue(result["ok"])
            self.assertFalse(result["bypassed"])
            self.assertEqual("smoke-9", result["evidence"]["run_id"])
            self.assertIn("smoke-9", result["reason"])
            self.assertIn("除规模", result["reason"])

    def test_bypass_is_visible_never_silent(self):
        """绕过必须**如实标注**（CI/合成配置用），不能伪装成"冒烟通过了"。"""
        result = smoke_gate.check(
            inputs=_long_inputs(), config={"num_envs": 4096, "max_iterations": 300}, bypass=True,
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
                        inputs=_long_inputs(), config={"num_envs": 4096, "max_iterations": 300},
                    )
                finally:
                    os.environ.pop(smoke_gate.BYPASS_ENV, None)
                self.assertEqual(expected_bypass, result["bypassed"])
                self.assertEqual(not expected_bypass, not result["ok"])


if __name__ == "__main__":
    unittest.main()
