"""导入后自动冒烟的回归锁（`backend/trainability_check.py`）。

守四件事：
1. **静态就绪不过就不起冒烟**（如实写 not_ready + 静态原因，不浪费一次真跑）；
2. 目标档/任务由**族 ready 档 + 任务表**选出（不是写死 plane）；
3. 判据链四条（rc / 生效==预览 / ONNX / 解析地形）**任一不满足即 failed**，并把原因写进记录；
4. 记录只在 `write_record=True` 时落盘——矩阵工具跑 assets 源树时**不往仓库里写文件**。

真跑（起 worker）在本文件里用注入的 `runner` 替身验证判据链；真实链路另有 gated 用例
（`LEGGED_STUDIO_TEST_TRAINING=1`）与 `tools/validate_family_trainability.py` 覆盖。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trainability_check  # noqa: E402

GO2 = ROOT / "assets" / "robots" / "unitree_go2"


def _package(tmp: Path, *, readiness_ok: bool) -> Path:
    """造一个小包：契约 + 清单（真跑用替身，所以模型文件不需要存在）。"""

    package = tmp / "demo_package"
    package.mkdir(parents=True, exist_ok=True)
    contract = json.loads((GO2 / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
    contract["robot_id"] = "demo_package" if readiness_ok else "demo_package"
    (package / "contract_legacy_v2.json").write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    descriptor = {"schema_version": "robot-package-1.0", "package_id": "demo_package",
                  "task_kind": "generic", "model": {"format": "mjcf", "path": "robot.xml"}}
    (package / "robot_package.json").write_text(json.dumps(descriptor, ensure_ascii=False), encoding="utf-8")
    return package


class PickTargetTest(unittest.TestCase):
    def test_ready_package_picks_first_family_terrain_and_its_task(self):
        terrain, task = trainability_check.pick_target(GO2)
        self.assertEqual("plane", terrain)
        self.assertEqual("forward_walk", task)

    def test_not_ready_package_has_no_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = _package(Path(tmp), readiness_ok=False)
            # 空目录里没有模型 ⇒ 静态就绪判红
            self.assertIsNone(trainability_check.pick_target(package))


#: 预览替身：判据链里的「生效配置 == 预览」由此可控（真预览要起 schema worker，慢且与本锁无关）
_PREVIEW = {"environment": {"terrain_type": "plane", "num_envs": 2}, "observations": {"actor": []}}


class CheckRulesTest(unittest.TestCase):
    def _runner(self, *, returncode=0, onnx=True, terrain="plane"):
        def runner(config, contract, output: Path, timeout_s: int):
            env = {**_PREVIEW["environment"], "terrain_type": terrain}
            (output / "effective-config.json").write_text(
                json.dumps({"environment": env}, ensure_ascii=False), encoding="utf-8")
            if onnx:
                (output / "exported").mkdir(parents=True, exist_ok=True)
                (output / "exported" / "policy.onnx").write_bytes(b"onnx")
            return subprocess.CompletedProcess(args=["worker"], returncode=returncode, stdout="ok", stderr="")

        return runner

    def _invoke(self, package: Path, runner, **kwargs) -> dict:
        from unittest import mock

        with mock.patch("backend.training_config_helpers.dump_schema_via_worker",
                        lambda *args, **kw: json.loads(json.dumps(_PREVIEW))):
            return trainability_check.check(package, terrain="plane", task="forward_walk",
                                            runner=runner, timeout_s=30, **kwargs)

    def _check(self, tmp: Path, runner) -> dict:
        return self._invoke(_package(tmp, readiness_ok=True), runner)

    def test_all_four_criteria_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self._check(Path(tmp), self._runner())
            self.assertEqual("passed", record["status"], record["reason"])
            self.assertTrue(record["effective_matches_preview"])
            self.assertTrue(record["onnx_exported"])
            self.assertEqual("plane", record["resolved_terrain"])

    def test_nonzero_exit_is_failed_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self._check(Path(tmp), self._runner(returncode=1))
            self.assertEqual("failed", record["status"])
            self.assertIn("退出码 1", record["reason"])

    def test_missing_onnx_is_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self._check(Path(tmp), self._runner(onnx=False))
            self.assertEqual("failed", record["status"])
            self.assertIn("ONNX", record["reason"])

    def test_effective_config_diverging_from_preview_is_failed(self):
        """worker 生效的地形与预览不一致 ⇒ 判红（页面看到的与真跑不能是两回事）。"""
        with tempfile.TemporaryDirectory() as tmp:
            record = self._check(Path(tmp), self._runner(terrain="flat"))
            self.assertEqual("failed", record["status"])
            self.assertIn("生效配置", record["reason"])

    def test_record_is_written_only_when_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = _package(Path(tmp), readiness_ok=True)
            self._invoke(package, self._runner(), write_record=False)
            self.assertIsNone(trainability_check.load(package))
            self._invoke(package, self._runner())
            self.assertEqual("passed", (trainability_check.load(package) or {}).get("status"))

    def test_assembly_failure_is_recorded_as_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "broken"
            package.mkdir()
            (package / "robot_package.json").write_text("{}", encoding="utf-8")
            record = trainability_check.check(package, terrain="plane", task="forward_walk", timeout_s=5)
            self.assertEqual("failed", record["status"])
            self.assertTrue(record["reason"])


class RunDispatcherTest(unittest.TestCase):
    def test_missing_manifest_reports_not_a_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = trainability_check.run(Path(tmp))
            self.assertEqual("not_ready", record["status"])
            self.assertIn("robot_package.json", record["reason"])

    def test_not_ready_package_records_static_reason_without_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = _package(Path(tmp), readiness_ok=False)
            record = trainability_check.run(package)
            self.assertEqual("not_ready", record["status"])
            self.assertIn("静态就绪未通过", record["reason"])
            self.assertEqual("not_ready", (trainability_check.load(package) or {}).get("status"))


if __name__ == "__main__":
    unittest.main()
