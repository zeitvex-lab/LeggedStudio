"""G2 / S4：自动连跑两遍的采集器（`tools/replay_gate.py --auto`）+ 记录器抽象测试。

守什么：

1. **目标解析**（采集器唯一自己做的决定）：包/Bundle 目录、已提升产物目录、裸 onnx 三种
   目标各解析成什么；解析不出（produced 产物没绑包 / 路径不存在 / 陌生目录形状）必须
   退出码 2 且说清怎么改 —— 不许静默猜；
2. **记录器抽象**（`adapters/mjlab/frame_log.validate_frame_log`）：无头/浏览器两侧共享的
   帧约定——必备五件套、NaN/Inf 拦下、action 未回填拦下、head 的 recorded 对账；
3. **编排层**（mock 子进程，不跑真仿真）：
   - 两份一致 ⇒ exit 0 且结论 pass；
   - 篡改一帧 ⇒ exit 非 0 且**报出首个发散的 stepIndex**（判据不空转的证据链路）；
   - 子进程崩溃 ⇒ exit 2（「没跑成」≠「不一致」），绝不误报 pass；
   - 产出缺帧字段 / 干脆没写文件 ⇒ fail-closed（exit 2），不喂烂日志给判据；
4. **判据零改动**：比对一律走既有 `replay_determinism`（本文件不重写任何比对逻辑，
   判据本身由 backend/test_replay_determinism.py 守）。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess  # noqa: F401  （测试里被整体替换的是它）
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.frame_log import (  # noqa: E402
    FRAME_LOG_SCHEMA,
    validate_frame,
    validate_frame_log,
)


def _load_gate():
    """tools/ 不是包，按路径加载被测模块（与 backend/test_reproduce 的门禁口径一致）。"""

    spec = importlib.util.spec_from_file_location("replay_gate_under_test", ROOT / "tools" / "replay_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _payload(steps: int = 6, seed: int = 7, *, bump_at: int | None = None) -> dict:
    """一份合格的无头 frame log（与 frame_log.produce_frame_log 同形）。"""

    frames = []
    for step in range(steps):
        obs = [step * 0.1, 0.0, 1.0]
        if bump_at is not None and step == bump_at:
            obs[1] += 0.02
        frames.append({
            "t": round(step * 0.02, 6), "stepIndex": step, "obs": obs,
            "action": [0.1, -0.2], "ctrlBefore": [0.0, 0.0],
            "targetsPos": [1.0, 2.0], "targetsVel": [0.0, 0.0], "actuatorIds": [11, 12],
        })
    head = {
        "schema": FRAME_LOG_SCHEMA, "created_at": "2026-09-18T00:00:00+00:00",
        "producer": "adapters/mjlab/frame_log.py", "seed": seed,
        "cmd": [0.4, 0.0, 0.0], "steps": steps, "recorded": steps,
        "package": "assets/robots/zex-w", "robot_id": "zex-w",
        "policy": {"id": "fake-policy"}, "physics": {}, "observation": {},
        "randomization": {"applied": False}, "adapter": {},
    }
    return {"head": head, "frames": frames}


class _FakeProducer:
    """替换 gate 里的 subprocess.run：不跑真仿真，按命令行把假 frame log 写到 --out。

    记下每次调用（编排必须起**两个**子进程、同 seed、不同 --out），并可注入：
    returncode≠0（子进程崩溃）、坏日志（写出的 payload 缺字段）、缺文件（rc=0 但不写）。
    """

    def __init__(self, plans: dict[str, dict], *, returncode: int = 0, stderr: str = "",
                 write_nothing: bool = False, corrupt: bool = False):
        self.plans = plans
        self.returncode = returncode
        self.stderr = stderr
        self.write_nothing = write_nothing
        self.corrupt = corrupt
        self.calls: list[list[str]] = []

    def __call__(self, command, capture_output=True, text=True, cwd=None):
        self.calls.append(list(command))
        if self.returncode != 0:
            return SimpleNamespace(returncode=self.returncode, stdout="", stderr=self.stderr)
        out = Path(command[command.index("--out") + 1])
        if not self.write_nothing:
            name = out.stem
            payload = self.plans.get(name, self.plans["run-a"])
            if self.corrupt:
                payload = json.loads(json.dumps(payload))
                for frame in payload["frames"]:
                    frame.pop("stepIndex")
            out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="frame log 已写出", stderr="")


class AutoTargetResolutionTests(unittest.TestCase):
    """--auto 的目标解析：三种认得、解析不出就 exit 2 并给修法（原因走 stderr）。"""

    def _resolve(self, target: Path, **kwargs):
        """直接调解析器：返回 (plan|None, code, stderr)。SystemExit 的消息在 stderr，不在异常里。"""

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            try:
                return gate.resolve_auto_target(target, **kwargs), 0, stderr.getvalue()
            except SystemExit as exc:
                return None, exc.code, stderr.getvalue()

    def test_bundle_directory_resolves_to_package_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            (bundle / "simulation").mkdir(parents=True)
            (bundle / "simulation" / "config.json").write_text(
                json.dumps({"policies": [{"id": "p1"}]}), encoding="utf-8")
            plan = gate.resolve_auto_target(bundle, package=None, policy=None, policy_id=None)
            self.assertEqual(plan["kind"], "package_or_bundle")
            self.assertEqual(plan["package"], str(bundle))
            self.assertIn("第一条", plan["note"])

    def test_explicit_policy_id_passes_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            (bundle / "simulation").mkdir(parents=True)
            (bundle / "simulation" / "config.json").write_text("{}", encoding="utf-8")
            plan = gate.resolve_auto_target(bundle, package=None, policy=None, policy_id="the-one")
            self.assertIsNone(plan["policy"])
            self.assertEqual(plan["policy_id"], "the-one")

    def test_bound_artifact_resolves_robot_package_and_policy_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "zex-w__x"
            artifact.mkdir()
            (artifact / "artifact.json").write_text(
                json.dumps({"kind": "policies", "robot": "some-robot", "policy_id": "the-id"}),
                encoding="utf-8")
            plan = gate.resolve_auto_target(artifact, package=None, policy=None, policy_id=None)
            self.assertEqual(plan["kind"], "artifact")
            self.assertEqual(plan["package"], "assets/robots/some-robot")
            self.assertEqual(plan["policy_id"], "the-id")

    def test_produced_artifact_without_package_is_honest_exit_2(self):
        """produced 产物未绑定包是已登记现状 —— 解析器不许假装能猜。"""

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "produced"
            artifact.mkdir()
            (artifact / "artifact.json").write_text(
                json.dumps({"kind": "produced", "run_id": "r1"}), encoding="utf-8")
            plan, code, stderr = self._resolve(artifact, package=None, policy=None, policy_id=None)
            self.assertIsNone(plan)
            self.assertEqual(code, 2)
            self.assertIn("--package", stderr)

    def test_produced_artifact_with_onnx_and_package_resolves_explicit_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "produced"
            artifact.mkdir()
            (artifact / "artifact.json").write_text(json.dumps({"kind": "produced"}), encoding="utf-8")
            (artifact / "policy.onnx").write_bytes(b"onnx")
            plan = gate.resolve_auto_target(artifact, package="assets/robots/zex-w",
                                            policy=None, policy_id=None)
            self.assertEqual(plan["policy"], str(artifact / "policy.onnx"))

    def test_missing_target_and_unknown_shape_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, code, stderr = self._resolve(Path(tmp) / "nope", package=None, policy=None, policy_id=None)
            self.assertIsNone(plan)
            self.assertEqual(code, 2)
            stranger = Path(tmp) / "stranger"
            stranger.mkdir()
            (stranger / "readme.txt").write_text("hi", encoding="utf-8")
            plan, code, stderr = self._resolve(stranger, package=None, policy=None, policy_id=None)
            self.assertIsNone(plan)
            self.assertEqual(code, 2)
            self.assertIn("simulation/config.json", stderr)

    def test_bare_onnx_requires_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            onnx = Path(tmp) / "p.onnx"
            onnx.write_bytes(b"onnx")
            plan, code, stderr = self._resolve(onnx, package=None, policy=None, policy_id=None)
            self.assertIsNone(plan)
            self.assertEqual(code, 2)
            plan, _, _ = self._resolve(onnx, package="assets/robots/zex-w", policy=None, policy_id=None)
            self.assertEqual(plan["kind"], "onnx")
            self.assertEqual(plan["policy"], str(onnx))

    def test_check_auto_package_rejects_missing_package(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate._check_auto_package({"kind": "artifact", "package": "assets/robots/definitely-not-here"})
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("不存在", stderr.getvalue())


class ValidateFrameLogTests(unittest.TestCase):
    """记录器抽象：两侧共享的帧约定，坏形状必须报得出是哪一帧哪个字段。"""

    def test_valid_headless_log_has_no_problems(self):
        self.assertEqual(validate_frame_log(_payload(), require_head=True), [])

    def test_browser_bare_array_accepted_without_head(self):
        payload = _payload()["frames"]
        self.assertEqual(validate_frame_log(payload), [])

    def test_bare_array_rejected_when_head_required(self):
        problems = validate_frame_log(_payload()["frames"], require_head=True)
        self.assertTrue(any("head" in problem for problem in problems))

    def test_missing_stepindex_reported_with_position(self):
        problems = validate_frame_log([
            {"t": 0.0, "obs": [1.0], "action": [0.0], "ctrlBefore": [0.0]}])
        self.assertTrue(any("stepIndex" in problem and "frames[0]" in problem for problem in problems))
        # 整帧几乎为空：四条"缺必备字段"一起报，且指明是第几帧
        self.assertTrue(any("必备字段" in problem for problem in validate_frame({"t": 0.0}, 3)))

    def test_nan_obs_is_caught_with_offender(self):
        problems = validate_frame_log([{"t": 0.0, "stepIndex": 0, "obs": [float("nan"), 1.0],
                                        "action": [0.0], "ctrlBefore": [0.0]}])
        self.assertTrue(any("nan 不是有限数" in problem for problem in problems))

    def test_unfilled_action_is_caught(self):
        problems = validate_frame_log([{"t": 0.0, "stepIndex": 0, "obs": [1.0],
                                        "action": None, "ctrlBefore": [0.0]}])
        self.assertTrue(any("action" in problem and "null" in problem for problem in problems))

    def test_head_recorded_must_match_frames(self):
        payload = _payload(steps=4)
        payload["head"]["recorded"] = 5
        problems = validate_frame_log(payload, require_head=True)
        self.assertTrue(any("recorded" in problem for problem in problems))

    def test_targets_length_must_match_action(self):
        frame = {**_payload()["frames"][0], "targetsPos": [1.0]}
        problems = validate_frame(frame, 0)
        self.assertTrue(any("targetsPos" in problem and "长度" in problem for problem in problems))

    def test_schema_and_cmd_contract(self):
        payload = _payload(steps=2)
        payload["head"]["schema"] = "nope"
        payload["head"]["cmd"] = [0.4]
        problems = validate_frame_log(payload, require_head=True)
        self.assertTrue(any("schema" in problem for problem in problems))
        self.assertTrue(any("cmd" in problem for problem in problems))


class AutoOrchestrationTests(unittest.TestCase):
    """编排层（mock 子进程）：一致→0 / 篡改→非0+stepIndex / 崩溃→2 不误报 / 烂产出→fail-closed。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.package = self.tmp / "fake-bundle"
        (self.package / "simulation").mkdir(parents=True)
        (self.package / "simulation" / "config.json").write_text(
            json.dumps({"policies": [{"id": "fake-policy"}]}), encoding="utf-8")
        self.keep_logs = self.tmp / "logs"

    def _run_auto(self, fake: _FakeProducer, *extra: str):
        argv = ["replay_gate.py", "--auto", str(self.package), "--venv", "fake-venv",
                "--steps", "6", "--min-frames", "3", "--keep-logs", str(self.keep_logs), *extra]
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(gate, "_adapter_interpreter", return_value=Path("fake-python")), \
                mock.patch.object(gate.subprocess, "run", fake), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = gate.main()
            except SystemExit as exc:  # argparse.error / _fail_environment 都走这里
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def _summary(self, stdout: str) -> dict:
        return json.loads(stdout)

    def test_identical_runs_pass_with_exit_zero_and_two_subprocesses(self):
        fake = _FakeProducer({"run-a": _payload(), "run-b": _payload()})
        code, stdout, _ = self._run_auto(fake, "--json")
        self.assertEqual(code, 0)
        summary = self._summary(stdout)
        self.assertEqual(summary["verdict"], "pass")
        self.assertEqual(summary["determinism"]["verdict"], "pass")
        self.assertEqual(summary["auto"]["target"], str(self.package))
        # 编排的本质：**两个独立子进程**、同 seed、各写各的日志
        self.assertEqual(len(fake.calls), 2)
        seeds = {call[call.index("--seed") + 1] for call in fake.calls}
        outs = {Path(call[call.index("--out") + 1]).name for call in fake.calls}
        self.assertEqual(seeds, {"7"})
        self.assertEqual(outs, {"run-a.json", "run-b.json"})
        self.assertEqual(summary["runs"]["frames"], 6)

    def test_tampered_frame_fails_with_first_divergence_step_index(self):
        fake = _FakeProducer({"run-a": _payload(), "run-b": _payload(bump_at=4)})
        code, stdout, stderr = self._run_auto(fake, "--json")
        self.assertEqual(code, 1)
        summary = self._summary(stdout)
        self.assertEqual(summary["verdict"], "fail")
        first = summary["determinism"]["first_divergence"]
        self.assertEqual(first["step_index"], 4)
        self.assertIn("stepIndex=4", stderr)

    def test_producer_crash_is_environment_failure_not_pass(self):
        fake = _FakeProducer({"run-a": _payload()}, returncode=1, stderr="mujoco boom")
        code, stdout, stderr = self._run_auto(fake, "--json")
        self.assertEqual(code, 2)  # 「没跑成」≠「不一致」：不占用判据的 fail 码
        self.assertNotIn("pass", stdout)
        self.assertIn("无头产出失败", stderr)
        self.assertIn("mujoco boom", stderr)

    def test_produced_log_without_required_fields_fails_closed(self):
        fake = _FakeProducer({"run-a": _payload(), "run-b": _payload()}, corrupt=True)
        code, _, stderr = self._run_auto(fake, "--json")
        self.assertEqual(code, 2)
        self.assertIn("帧校验", stderr)
        self.assertIn("stepIndex", stderr)

    def test_missing_produced_log_fails_closed(self):
        fake = _FakeProducer({"run-a": _payload()}, write_nothing=True)
        code, _, stderr = self._run_auto(fake, "--json")
        self.assertEqual(code, 2)
        self.assertIn("产出日志不可读", stderr)

    def test_human_mode_reports_resolution_and_pass(self):
        fake = _FakeProducer({"run-a": _payload(), "run-b": _payload()})
        code, stdout, _ = self._run_auto(fake)
        self.assertEqual(code, 0)
        self.assertIn("--auto", stdout)
        self.assertIn(str(self.package), stdout)
        self.assertIn("PASS", stdout)


if __name__ == "__main__":
    unittest.main()
