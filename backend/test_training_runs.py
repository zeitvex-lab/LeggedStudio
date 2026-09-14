"""B9 验收测试：训练 Run 一等对象 + 可复现四件套。

对齐 `00_know/01_任务清单.md` B9 的验收判据：**「同 seed 可对账；`environment-lock.json` 存在」**。

覆盖三件事：
1. **同输入同指纹**（对账的地基）—— 键顺序/平台无关，输入一变指纹必变；
2. **四件套落盘且可复核** —— environment-lock 记的是 uv.lock 的真实 sha256 与 adapter venv 实装版本；
3. **不可变** —— 幂等重写返回同一记录；输入或内容一变即拒绝覆盖；被改过的档案 `verify_run` 必须报出来。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.training import runs  # noqa: E402


def make_inputs(**overrides):
    """一份典型的训练输入四元组（契约哈希 + recipe + profile + seed + 关键参数）。"""
    payload = {
        "contract_hash": "a" * 64,
        "recipe": {"id": "core/velocity@2.0", "version": "2.0"},
        "profile": {"name": "go2-velocity", "sha256": "b" * 64},
        "seed": 7,
        "params": {"num_envs": 4096, "iterations": 300, "physics_hz": 200},
    }
    payload.update(overrides)
    return runs.build_inputs(**payload)


def make_run(run_dir: Path, **overrides):
    inputs = make_inputs(**overrides)
    resolved_config = runs.build_resolved_config(
        robot_id="unitree_go2", task="velocity", inputs=inputs,
        resolved={"num_envs": 4096, "iterations": 300},
    )
    environment_lock = runs.collect_environment_lock(seed=inputs["seed"], device="cpu")
    return runs.write_run(
        run_dir, resolved_config=resolved_config, environment_lock=environment_lock,
        run_id=runs.run_id_for(task="velocity", inputs=inputs),
    )


class CanonicalDigestTest(unittest.TestCase):
    """账要对得上，靠的是"同一份输入必得同一个摘要"。"""

    def test_key_order_does_not_matter(self):
        self.assertEqual(
            runs.canonical_digest({"a": 1, "b": [2, 3]}),
            runs.canonical_digest({"b": [2, 3], "a": 1}),
        )

    def test_value_change_changes_digest(self):
        self.assertNotEqual(runs.canonical_digest({"seed": 1}), runs.canonical_digest({"seed": 2}))

    def test_non_ascii_is_stable_not_escaped(self):
        first = runs.canonical_digest({"任务": "速度追踪", "note": "中文"})
        second = runs.canonical_digest({"note": "中文", "任务": "速度追踪"})
        self.assertEqual(first, second)

    def test_file_digest_of_real_uv_lock(self):
        self.assertEqual(runs.file_digest(runs.UV_LOCK), runs.file_digest(runs.UV_LOCK))
        self.assertIsNone(runs.file_digest(runs.ROOT / "不存在的锁文件.lock"))


class SameSeedReconcileTest(unittest.TestCase):
    """验收第 1 条：同 seed 可对账。"""

    def test_same_inputs_produce_same_digest(self):
        self.assertEqual(make_inputs()["digest"], make_inputs()["digest"])

    def test_run_id_embeds_input_fingerprint(self):
        """run_id 的后 8 位是输入指纹：一眼能看出两次 Run 是否同源。"""
        inputs = make_inputs()
        first = runs.run_id_for(task="velocity", inputs=inputs)
        second = runs.run_id_for(task="velocity", inputs=make_inputs(seed=7))
        self.assertEqual(first[-8:], inputs["digest"][:8])
        self.assertEqual(first[-8:], second[-8:])                       # 同输入 → 同一指纹段
        self.assertNotEqual(first[-8:], make_inputs(seed=8)["digest"][:8])  # 不同输入 → 不同指纹段
        self.assertTrue(first.endswith(f"velocity_{inputs['digest'][:8]}"))

    def test_any_input_change_changes_fingerprint(self):
        baseline = make_inputs()["digest"]
        for label, overrides in (
            ("seed", {"seed": 8}),
            ("recipe 版本", {"recipe": {"id": "core/velocity@2.0", "version": "2.1"}}),
            ("契约哈希", {"contract_hash": "c" * 64}),
            ("profile", {"profile": {"name": "go2-rough", "sha256": "d" * 64}}),
            ("运行参数", {"params": {"num_envs": 1024}}),
        ):
            with self.subTest(which=label):
                self.assertNotEqual(baseline, make_inputs(**overrides)["digest"])


class EnvironmentLockTest(unittest.TestCase):
    """验收第 2 条：environment-lock.json 存在，且记的是**可复核**的事实。"""

    def test_lock_records_real_uv_lock_digest(self):
        lock = runs.collect_environment_lock(seed=3, device="cuda:0")
        self.assertEqual(lock["dependency_lock"]["sha256"], runs.file_digest(runs.UV_LOCK))
        self.assertEqual(lock["seed"], 3)
        self.assertEqual(lock["device"], "cuda:0")
        self.assertTrue(lock["python"]["version"])
        self.assertIn("system", lock["platform"])

    def test_lock_written_into_run_dir_and_verify_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            record = make_run(run_dir)
            paths = runs.run_paths(run_dir)
            self.assertTrue(paths["environment_lock"].is_file())
            self.assertTrue(paths["resolved_config"].is_file())
            self.assertTrue(paths["checkpoints"].is_dir())
            self.assertTrue(paths["metrics"].is_dir())
            self.assertTrue(record.config_digest)

            report = runs.verify_run(run_dir)
            self.assertTrue(report["ok"], report["problems"])
            self.assertEqual(report["inputs_digest"], record.inputs_digest)
            self.assertEqual(report["robot_id"], "unitree_go2")

    def test_adapter_venv_versions_read_without_importing_torch(self):
        """控制面不得 import torch/mjlab（V5）—— 版本从 dist-info 目录名读。"""
        versions = runs.venv_package_versions()
        self.assertIsInstance(versions, dict)
        self.assertNotIn("torch", sys.modules)


class ImmutabilityTest(unittest.TestCase):
    """V9：改任何东西＝派生新 Run，不就地覆盖。"""

    def test_same_inputs_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            first = make_run(run_dir)
            second = make_run(run_dir)          # 重跑同一份输入：不报错、不覆盖
            self.assertEqual(first.inputs_digest, second.inputs_digest)
            self.assertEqual(first.config_digest, second.config_digest)

    def test_different_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            make_run(run_dir)
            with self.assertRaises(runs.RunImmutableError):
                make_run(run_dir, seed=99)

    def test_tampered_archive_is_detected(self):
        """改档案里任意一处（不是输入指纹）也必须被抓到。"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            make_run(run_dir)
            config_path = runs.run_paths(run_dir)["resolved_config"]
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            payload["resolved"]["iterations"] = 999          # 偷改"实际生效参数"
            config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            report = runs.verify_run(run_dir)
            self.assertFalse(report["ok"])
            self.assertTrue(any("整档摘要" in problem for problem in report["problems"]), report["problems"])

    def test_missing_environment_lock_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            make_run(run_dir)
            runs.run_paths(run_dir)["environment_lock"].unlink()
            report = runs.verify_run(run_dir)
            self.assertFalse(report["ok"])
            self.assertTrue(any("environment-lock" in problem for problem in report["problems"]))

    def test_load_run_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-1"
            record = make_run(run_dir)
            self.assertEqual(runs.load_run(run_dir).as_dict(), record.as_dict())
            self.assertIsNone(runs.load_run(Path(tmp) / "不存在"))


class TaskWiringTest(unittest.TestCase):
    """B9 接线：训练任务的 config 决定 Run 指纹（键名对齐 `backend/training/create.py`）。"""

    class _Contract:
        robot_id = "unitree_go2"

        def compute_hash(self) -> str:
            return "f" * 64

    @staticmethod
    def _config(**overrides):
        config = {
            "backend": "native_mjlab",
            "mode": "train",
            "seed": 7,
            "profile_id": "go2-velocity",
            "profile_mtime": 1757800000.0,
            "num_envs": 4096,
            "max_iterations": 300,
            "resolved_recipe": {"id": "core/velocity", "version": "2.0"},
        }
        config.update(overrides)
        return config

    def _inputs(self, **overrides):
        return runs.run_inputs_from_task(
            contract_hash=self._Contract().compute_hash(), config=self._config(**overrides),
        )

    def test_recipe_profile_seed_are_extracted_not_left_in_params(self):
        inputs = self._inputs()
        self.assertEqual(inputs["seed"], 7)
        self.assertEqual(inputs["recipe"], {"id": "core/velocity", "version": "2.0"})
        self.assertEqual(inputs["profile"]["profile_id"], "go2-velocity")
        self.assertNotIn("resolved_recipe", inputs["params"])
        self.assertEqual(inputs["params"]["num_envs"], 4096)

    def test_any_config_change_changes_fingerprint(self):
        baseline = self._inputs()["digest"]
        for label, overrides in (
            ("num_envs", {"num_envs": 1024}),
            ("max_iterations", {"max_iterations": 5}),
            ("seed", {"seed": 8}),
            ("recipe", {"resolved_recipe": {"id": "core/velocity", "version": "2.1"}}),
            ("profile 换了", {"profile_id": "go2-rough"}),
            ("profile 被改但 id 没换", {"profile_mtime": 1757999999.0}),
        ):
            with self.subTest(which=label):
                self.assertNotEqual(baseline, self._inputs(**overrides)["digest"])

    def test_create_run_for_task_writes_tetrad_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "go2_velocity_20260914_120000"
            record = runs.create_run_for_task(
                run_dir, contract=self._Contract(), config=self._config(),
                task="go2_velocity_20260914_120000",
            )
            self.assertEqual(record.run_id, run_dir.name)      # task_id 即 run_id
            self.assertEqual(record.robot_id, "unitree_go2")
            self.assertEqual(record.seed, 7)
            for key in ("resolved_config", "environment_lock", "record"):
                self.assertTrue(runs.run_paths(run_dir)[key].is_file(), key)
            report = runs.verify_run(run_dir)
            self.assertTrue(report["ok"], report["problems"])


if __name__ == "__main__":
    unittest.main()
