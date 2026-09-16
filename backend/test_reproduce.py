"""B12 后半：复现三档（R1 看 / R2 用 / R3 训）的判据与诚实边界。

## 这组测试守的是什么

复现最容易变成口号（"同 seed 就能复现"）—— 所以这里把三档各自**能证什么、不能证什么**钉死：

1. **R3 是"近似"而不是"逐位"**：报告必须逐项对账"当时记录的 vs 现在实测的"，只要有 warn 级差异
   （`uv.lock` / adapter venv 包版本 / python 版本）就**绝不自称 exact**；
2. **R2 如实受阻**：判据实现（`replay_determinism`）在位，但**没有可自动采集的逐帧日志**
   （L1 已登记缺口）⇒ 必须报 `blocked` 并写明原因，而不是给个 `ok` 让人以为验过了；
3. **R1 只判"回放所需最小集合"**：策略 blob 可载入 / 契约可校验 / 包清单在 —— 缺一即不就绪，
   onnxruntime 不可用时如实记 `skipped`（不算通过也不算失败）。

风格：纯 stdlib；Run 用真实落盘函数造（`create_run_for_task`），环境锁指向假 venv 以保证可复现。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import bundle_export as bx  # noqa: E402
from backend import reproduce as rp  # noqa: E402
from backend.training.runs import create_run_for_task  # noqa: E402


class _RunFixture:
    """造一个真实落盘的 Run（环境锁指向临时假 venv，避免依赖宿主机装了哪些包）。"""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="reproduce-")
        self.previous_venv = os.environ.get("LEGGED_STUDIO_MJLAB_VENV")
        venv = Path(self.tmp.name) / "venv"
        site = venv / "lib" / "python3.12" / "site-packages"
        for dist in ("torch-2.0.0.dist-info", "mjlab-1.6.0.dist-info"):
            (site / dist).mkdir(parents=True)
        os.environ["LEGGED_STUDIO_MJLAB_VENV"] = str(venv)
        self.workspace = Path(self.tmp.name) / "ws"
        self.workspace.mkdir()
        self.run_dir = self.workspace / "unitree_go2_task_000000000001"
        create_run_for_task(
            self.run_dir,
            contract=SimpleNamespace(robot_id="unitree_go2", compute_hash=lambda: "cafe1234"),
            config={"robot_id": "unitree_go2", "seed": 7, "num_envs": 16, "max_iterations": 5},
            task="training",
        )

    def lock_path(self) -> Path:
        return self.run_dir / "environment-lock.json"

    def doctor_lock(self, mutate) -> None:
        payload = json.loads(self.lock_path().read_text(encoding="utf-8"))
        mutate(payload)
        self.lock_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def close(self) -> None:
        if self.previous_venv is None:
            os.environ.pop("LEGGED_STUDIO_MJLAB_VENV", None)
        else:
            os.environ["LEGGED_STUDIO_MJLAB_VENV"] = self.previous_venv
        self.tmp.cleanup()


class R3EnvironmentAuditTest(unittest.TestCase):
    """R3：同 seed 近似复现 —— 环境对账 + 缺口清单 + 结论不许夸大。"""

    def setUp(self):
        self.fixture = _RunFixture()

    def tearDown(self):
        self.fixture.close()

    def _r3(self, **kwargs):
        report = rp.build_reproduction(run_dir=self.fixture.run_dir, **kwargs)
        return report["tiers"]["R3_training"]

    def test_unchanged_environment_is_exact(self):
        tier = self._r3()
        self.assertEqual("exact", tier["status"], tier["gaps"])
        self.assertEqual(0, tier["warn_count"])
        self.assertEqual(7, tier["seed"])
        self.assertTrue(tier["inputs_digest"] and tier["config_digest"])

    def test_changed_dependency_lock_is_approximate(self):
        """依赖锁变了 ⇒ 必须降级为 approximate 并列出一条 warn 级差异。"""

        self.fixture.doctor_lock(lambda payload: payload["dependency_lock"].update({"sha256": "0" * 64}))
        tier = self._r3()
        self.assertEqual("approximate", tier["status"])
        self.assertGreaterEqual(tier["warn_count"], 1)
        fields = {gap["field"]: gap["severity"] for gap in tier["gaps"]}
        self.assertEqual("warn", fields.get("dependency_lock.sha256"))

    def test_changed_package_version_is_approximate(self):
        self.fixture.doctor_lock(lambda payload: payload["adapter_venv"]["packages"].update({"torch": "9.9.9"}))
        tier = self._r3()
        self.assertEqual("approximate", tier["status"])
        self.assertTrue(any(gap["field"].endswith("torch") for gap in tier["gaps"]), tier["gaps"])

    def test_missing_venv_is_recorded_as_warn(self):
        """当时那套 venv 不在了 ⇒ 连近似复现都做不到，必须明说。"""

        self.fixture.doctor_lock(lambda payload: payload["adapter_venv"].update({"path": "/nonexistent/venv"}))
        tier = self._r3()
        self.assertEqual("approximate", tier["status"])
        self.assertTrue(any(gap["field"] == "adapter_venv.exists" for gap in tier["gaps"]), tier["gaps"])

    def test_platform_and_git_are_info_level(self):
        """平台补丁号/git 状态变化按 info 记录，不据此把结论降级（否则报告天天是 approximate）。"""

        recorded = json.loads(self.fixture.lock_path().read_text(encoding="utf-8"))
        current = dict(recorded)
        current["platform"] = {**recorded["platform"], "release": "different-release"}
        current["vcs"] = {**(recorded.get("vcs") or {}), "commit": "deadbeef"}
        gaps = rp._environment_gaps(recorded, current)
        severities = {gap["field"]: gap["severity"] for gap in gaps}
        self.assertEqual("info", severities["platform.release"])
        self.assertEqual("info", severities["vcs.commit"])
        self.assertEqual(0, sum(1 for gap in gaps if gap["severity"] == "warn"))

    def test_report_schema_and_note(self):
        report = rp.build_reproduction(run_dir=self.fixture.run_dir)
        self.assertEqual(rp.REPRODUCE_SCHEMA, report["schema_version"])
        self.assertIn("不保证", report["tiers"]["R3_training"]["note"])

    def test_non_run_directory_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = rp.build_reproduction(run_dir=tmp)
            self.assertEqual("not_available", report["tiers"]["R3_training"]["status"])


class R2HonestyTest(unittest.TestCase):
    """R2：判据已就位 ⇒ 默认记 `not_run`（未跑 ≠ 通过），且两道诚实闸门必须拦住假绿。

    闸门（2026-09-16）：① 策略必须落在被跑的包内（否则"干净机器可复现"是假的）；
    ② 环境不满足只能记 blocked（"没跑成"与"跑了不一致"是两件事）。
    """

    def test_default_is_not_run_with_the_command_to_run_it(self):
        report = rp.build_reproduction()
        tier = report["tiers"]["R2_evaluation"]
        self.assertEqual("not_run", tier["status"])
        self.assertIn("replay_gate.py --produce", tier["reason"])
        self.assertIn("未跑 ≠ 通过", tier["reason"])
        self.assertIn("frame_log.py", tier["machinery"])

    def test_summarise_exposes_all_three_tiers(self):
        summary = rp.summarise(rp.build_reproduction())
        self.assertEqual({"R1_playback", "R2_evaluation", "R3_training", "R3_gaps", "R3_warn"}, set(summary))


def _fake_gate(returncode: int, payload: dict | None = None, stderr: str = ""):
    """替换 `subprocess.run`：把门禁的返回钉死，用来单测两道闸门（不需适配器 venv）。"""

    class _Completed:
        def __init__(self):
            self.returncode = returncode
            self.stdout = json.dumps(payload) if payload is not None else ""
            self.stderr = stderr

    def runner(*_args, **_kwargs):
        return _Completed()

    return runner


def _gate_payload(inside_package: bool) -> dict:
    return {
        "verdict": "pass",
        "determinism": {"verdict": "pass", "reason": "identical", "frames": 60},
        "seed_sensitivity": {"changed": False, "note": "L3 未接入 DR"},
        "runs": {
            "frames": 60,
            "policy": {
                "path": "policies/x/policy.onnx",
                "resolution": {"mode": "explicit", "inside_package": inside_package},
            },
        },
    }


class R2GateTest(unittest.TestCase):
    """`evaluation_replay` 的四种结局：pass / fail / blocked(环境) / blocked(包外解析)。"""

    def _run(self, monkey_fake):
        import subprocess

        original = subprocess.run
        subprocess.run = monkey_fake
        try:
            return rp.evaluation_replay(package_dir="/tmp/pkg", policy="simulation/policies/policy.onnx", steps=60)
        finally:
            subprocess.run = original

    def test_pass_when_two_runs_are_identical(self):
        report = self._run(_fake_gate(0, _gate_payload(inside_package=True)))
        self.assertEqual("pass", report["status"])
        self.assertEqual("pass", report["determinism"]["verdict"])

    def test_fail_when_runs_diverge(self):
        report = self._run(_fake_gate(1, {**_gate_payload(True), "determinism": {"verdict": "fail"}}))
        self.assertEqual("fail", report["status"])

    def test_blocked_when_environment_missing(self):
        report = self._run(_fake_gate(2, None, stderr="找不到可用的适配器解释器"))
        self.assertEqual("blocked", report["status"])
        self.assertIn("适配器解释器", report["blocked_by"])

    def test_blocked_when_policy_resolved_outside_the_package(self):
        """本机（有仓库）跑 Bundle 时，索引可能把策略解析到仓库里的同名文件 —— 不算复现证据。"""

        report = self._run(_fake_gate(0, _gate_payload(inside_package=False)))
        self.assertEqual("blocked", report["status"])
        self.assertIn("包之外", report["blocked_by"])


class R2EndToEndTest(unittest.TestCase):
    """真跑一遍无头产出门禁（需适配器 venv；缺环境即跳过，不当失败）。"""

    @classmethod
    def setUpClass(cls):
        gate = ROOT / "tools" / "replay_gate.py"
        cls.venv = Path(os.environ.get("LEGGED_STUDIO_MJLAB_VENV") or "/opt/legged-studio/mjlab-cpu/.venv")
        if not (cls.venv / "bin" / "python").is_file():
            raise unittest.SkipTest(f"适配器 venv 不在：{cls.venv}")
        probe = subprocess.run([str(cls.venv / "bin" / "python"), "-c", "import mujoco, onnxruntime"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            raise unittest.SkipTest("适配器 venv 里没有 mujoco/onnxruntime")
        if not gate.is_file():
            raise unittest.SkipTest("缺 tools/replay_gate.py")

    def test_same_policy_twice_reproduces_frame_by_frame(self):
        report = rp.evaluation_replay(
            package_dir=ROOT / "assets" / "robots" / "zex-w",
            policy_id="zex-w-rough-9600",
            steps=12,
            seed_probe=99,
        )
        if report["status"] == "blocked":
            self.skipTest(f"环境未就绪：{report.get('blocked_by')}")
        self.assertEqual("pass", report["status"], report)
        self.assertEqual(12, report["runs"]["frames"])
        self.assertTrue(report["runs"]["policy"]["resolution"]["inside_package"])
        # seed 敏感性：DR 未接入（L3）⇒ 当前应为"未变化"，且报告必须自己说清这是空转
        self.assertIn("空转", report["seed_sensitivity"]["note"])


class R1PlaybackReadinessTest(unittest.TestCase):
    """R1：只判"回放所需最小集合齐备且可解析"。"""

    def test_empty_directory_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = rp.playback_readiness(tmp)
            self.assertFalse(report["ready"])
            by_name = {check["name"]: check for check in report["checks"]}
            self.assertFalse(by_name["policy_blob"]["ok"])
            self.assertTrue(by_name["policy_blob"]["required"])

    def test_bundle_with_policy_is_ready(self):
        artifact_id = next((key for key, entry in sorted(bx_artifacts()) if entry.get("kind") == "produced"), None)
        if artifact_id is None:
            self.skipTest("出库索引里没有 produced 产物")
        with tempfile.TemporaryDirectory() as tmp:
            bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", Path(tmp) / "bundle", artifact_id=artifact_id)
            report = rp.playback_readiness(Path(tmp) / "bundle")
            self.assertTrue(report["ready"], report["checks"])

    def test_removing_policy_blob_makes_it_not_ready(self):
        artifact_id = next((key for key, entry in sorted(bx_artifacts()) if entry.get("kind") == "produced"), None)
        if artifact_id is None:
            self.skipTest("出库索引里没有 produced 产物")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            bx.export_bundle(ROOT / "packs" / "zex-w.pack.json", out, artifact_id=artifact_id)
            for onnx in sorted(out.rglob("*.onnx")):
                onnx.unlink()
            report = rp.playback_readiness(out)
            self.assertFalse(report["ready"])
            self.assertTrue(any(not check["ok"] for check in report["checks"] if check["required"]))


def bx_artifacts():
    from backend import policy_artifacts as pa

    return pa.load_index().items()


if __name__ == "__main__":
    unittest.main()
