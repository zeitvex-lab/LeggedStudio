"""I1 第一批 CLI 离线列表命令测试：``pack list`` / ``run list`` / ``artifact list``。

三个命令都**不连控制面**，直接读仓库数据且复用 backend/ 的同一实现。这里用
subprocess 真调 ``scripts/legged_studio_cli.py``（与用户用法完全一致）：

* ``pack list`` —— 以**真实仓库**为底（14 个 Pack、含 unitree_go2）；
* ``run list`` / ``artifact list`` —— 用 tempfile 造合成 workspace / 出库目录
  （复用 ``backend.training.runs.create_run_for_task`` 与 ``backend.policy_artifacts``
  的真实产出函数造夹具），经 ``--workspace`` / ``--out-dir`` 指过去；
* 同时锁定：``--json`` 在全局与子命令两个位置都可用、输出可解析、字段齐全、
  ``--help`` 写明「离线命令，无需后端」（--offline 语义）。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import policy_artifacts as pa  # noqa: E402
from backend.training.runs import create_run_for_task  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "legged_studio_cli.py"

#: 控制面 venv 的 python（测试正是跑在里面）；不存在则退回当前解释器。
_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.is_file() else sys.executable


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """以仓库根为 cwd 真调 CLI；强制 UTF-8，保证中文/JSON 在 Windows 管道下不乱码。"""

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [PYTHON, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(ROOT), env=env, timeout=180,
    )


def make_package(root: Path, robot: str = "go2") -> Path:
    """造一个最小机器人包（与 test_policy_artifacts 的合成包同构）。"""

    policies = root / robot / "simulation" / "policies"
    policies.mkdir(parents=True)
    (policies / "walk.onnx").write_bytes(b"onnx-bytes-0123456789")
    (root / robot / "simulation" / "config.json").write_text(
        json.dumps({"policies": [{
            "id": "walk-100", "path": "simulation/policies/walk.onnx", "label": "Walk",
            "obs_dim": 48, "action_dim": 12, "history_len": 1, "task_type": "velocity",
            "source": "builtin-package",
            "contract": {"observation_kind": "go2_velocity", "action_scale": 0.25},
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root / robot


def make_run(root: Path, name: str = "unitree_go2_task_000000000000", *, status: str = "completed") -> Path:
    """造一个最小 Run 档案（复用 backend.training.runs 的真实落盘函数）。"""

    run_dir = root / name
    contract = SimpleNamespace(robot_id="unitree_go2", compute_hash=lambda: "cafe1234")
    create_run_for_task(
        run_dir, contract=contract,
        config={"robot_id": "unitree_go2", "seed": 7, "num_envs": 16, "max_iterations": 5},
        task="training",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"status": status}, ensure_ascii=False), encoding="utf-8",
    )
    (run_dir / "exported").mkdir(exist_ok=True)
    (run_dir / "exported" / "policy.onnx").write_bytes(b"produced-onnx-bytes")
    return run_dir


class PackListTest(unittest.TestCase):
    """``pack list``：真实仓库为底（与 tools/validate_packs.py 同一份校验实现）。"""

    def test_json_lists_at_least_14_packs_with_fields(self):
        proc = run_cli("pack", "list", "--json")
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)                       # --json 输出必须可解析
        self.assertGreaterEqual(payload["count"], 14, "本仓应有 14 个 Pack")
        ids = [pack["pack_id"] for pack in payload["packs"]]
        # 本仓真实 pack_id 带「-velocity」后缀（如 unitree_go2-velocity），按前缀匹配
        self.assertTrue(any(pid.startswith("unitree_go2") for pid in ids), ids)
        for key in ("pack_id", "valid", "file", "errors", "warnings"):
            self.assertTrue(all(key in pack for pack in payload["packs"]), f"缺字段 {key}")

    def test_human_output_is_chinese_table(self):
        proc = run_cli("pack", "list")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("unitree_go2", proc.stdout)
        self.assertIn("汇总", proc.stdout)
        self.assertIn("离线命令", proc.stdout)                  # --offline 语义写明在输出里


class RunListTest(unittest.TestCase):
    """``run list``：合成 workspace——含 run.json 的目录列出，旧目录如实跳过。"""

    def test_json_lists_runs_and_skips_dirs_without_run_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            run_dir = make_run(workspace)
            (workspace / "legacy_20260101").mkdir()            # B9 接线前的旧任务目录：无 run.json

            proc = run_cli("run", "list", "--workspace", str(workspace), "--json")
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(1, payload["count"])
            run = payload["runs"][0]
            self.assertEqual(run_dir.name, run["run_id"])
            self.assertEqual("unitree_go2", run["robot_id"])
            self.assertEqual(7, run["seed"])
            self.assertEqual("completed", run["status"])        # status.json 附状态
            self.assertTrue(run["created_at"])
            self.assertEqual(["legacy_20260101"], payload["skipped"])

    def test_human_output_lists_run_id_and_robot(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = make_run(Path(tmp) / "ws", status="failed")
            proc = run_cli("run", "list", "--workspace", str(run_dir.parent))
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn(run_dir.name, proc.stdout)
            self.assertIn("unitree_go2", proc.stdout)
            self.assertIn("failed", proc.stdout)
            self.assertIn("离线命令", proc.stdout)


class ArtifactListTest(unittest.TestCase):
    """``artifact list``：合成出库目录——声明条目 + produced 条目（特别标注）。"""

    def test_json_lists_declared_and_produced_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp), Path(tmp) / "policies"
            pkg = make_package(root)
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            artifact = pa.promote_from_run(make_run(root / "ws"), out_dir=out)

            proc = run_cli("artifact", "list", "--out-dir", str(out), "--json")
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(2, payload["count"])
            self.assertEqual(1, payload["produced_count"])

            by_id = {item["artifact_id"]: item for item in payload["artifacts"]}
            declared = by_id["go2__walk-100"]
            self.assertEqual("policies", declared["kind"])
            self.assertFalse(declared["produced"])
            self.assertEqual(
                declared["onnx_sha256_prefix"],
                pa.file_digest(pkg / "simulation" / "policies" / "walk.onnx")[:12],
            )
            self.assertEqual(declared["onnx_bytes"], len(b"onnx-bytes-0123456789"))

            produced = by_id[artifact["artifact_id"]]
            self.assertTrue(produced["produced"])               # produced 条目特别标注
            self.assertEqual("produced", produced["kind"])
            self.assertEqual(produced["onnx_bytes"], len(b"produced-onnx-bytes"))

    def test_human_output_marks_produced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp), Path(tmp) / "policies"
            make_package(root)
            pa.build_all(robots_dir=root, out_dir=out, write=True)
            pa.promote_from_run(make_run(root / "ws"), out_dir=out)

            proc = run_cli("artifact", "list", "--out-dir", str(out))
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("go2__walk-100", proc.stdout)
            self.assertIn("produced *", proc.stdout)            # produced 条目标 * 号
            self.assertIn("离线命令", proc.stdout)


class RealRepoArtifactListTest(unittest.TestCase):
    """真实仓库自检：出库索引在位且 CLI 能全部列出（与 test_policy_artifacts 的底数对齐）。"""

    def test_json_lists_real_repo_index(self):
        proc = run_cli("artifact", "list", "--json")
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreaterEqual(payload["count"], 40, "本仓出库索引应有 47 条产物")
        self.assertTrue(all(item["onnx_sha256_prefix"] for item in payload["artifacts"]))


class ContractTest(unittest.TestCase):
    """命令契约：--json 两个位置等价、--help 写明离线语义、既有 10 个命令不受影响。"""

    def test_global_json_flag_before_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "policies"
            make_package(Path(tmp))
            pa.build_all(robots_dir=Path(tmp), out_dir=out, write=True)

            proc = run_cli("--json", "artifact", "list", "--out-dir", str(out))
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)                   # 全局 --json 同样生效
            self.assertEqual(1, payload["count"])

    def test_help_documents_offline_semantics(self):
        for command in ("pack", "run", "artifact"):
            proc = run_cli(command, "list", "--help")
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("离线命令", proc.stdout)
            self.assertIn("无需后端", proc.stdout)

    def test_existing_http_commands_still_registered(self):
        proc = run_cli("--help")
        self.assertEqual(0, proc.returncode, proc.stderr)
        for name in ("algorithms", "hardware", "validate-model", "validate-contract",
                     "validate-scenario", "maps", "simulate", "train", "evaluate", "navigation"):
            self.assertIn(name, proc.stdout, f"既有命令 {name} 不见了")


if __name__ == "__main__":
    unittest.main()
