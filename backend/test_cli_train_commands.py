"""I1 第二批 CLI 训练在线命令测试：``train create`` / ``train status`` / ``train stop`` / ``train list``。

四个命令都**需要后端在跑**（走 ``/api/training/*`` HTTP 契约）。测试**不依赖真实后端**：
用标准库 ``http.server`` 在线程内起一个 stub，按后端真实形状返回构造好的 JSON
（status 端点外层 ``success`` + **内层** ``status`` 词表；create 响应含 ``smoke_gate``），
CLI 用 ``--base`` 指向 stub 端口，subprocess 真调 ``scripts/legged_studio_cli.py`` 断言
输出/退出码；另覆盖两条失败路径：

* stub 返回 409（冒烟前置门拒）→ 退出码非 0 且输出含 reason 片段；
* 端口拒绝连接（绑定但不 listen 的端口）→ 退出码非 0 且中文提示含「后端」，
  绝不静默编造结果。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "legged_studio_cli.py"

#: 控制面 venv 的 python（测试正是跑在里面）；不存在则退回当前解释器。
_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.is_file() else sys.executable

#: stub 里两个任务：一个运行中、一个已完成（完成态词表是 train_completed）
TASK_RUNNING = {
    "task_id": "tid-run-0001", "status": "running",
    "current_iteration": 3, "max_iterations": 5, "reward": 2.5, "error": None,
}
TASK_DONE = {
    "task_id": "tid-done-0002", "status": "train_completed",
    "current_iteration": 5, "max_iterations": 5, "reward": 12.5, "error": None,
}

#: 409 冒烟门拒绝时 stub 返回的 reason 片段（测试断言输出里含它）
SMOKE_REASON = "冒烟前置门拒绝：同输入指纹没有冒烟通过的 Run（digest ab12cd34 无证据）"


class _StubState:
    """stub 后端的可观测状态：记录收到的每个请求 + 可切换的应答模式。"""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.mode = "ok"  # ok | smoke_reject

    def last(self, method: str, path: str) -> dict | None:
        """取最后一条匹配 (method, path) 的请求记录。"""

        for record in reversed(self.requests):
            if record["method"] == method and record["path"] == path:
                return record
        return None


class _StubHandler(BaseHTTPRequestHandler):
    """线程内 stub 后端：按训练 API 的真实响应形状返回构造好的 JSON。"""

    def log_message(self, fmt, *args):  # 静默，避免污染测试输出
        return

    @property
    def state(self) -> _StubState:
        return self.server.state  # type: ignore[attr-defined]

    def _reply(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> object | None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _record(self, body: object | None) -> None:
        self.state.requests.append({
            "method": self.command,
            "path": urlparse(self.path).path,
            "headers": {key.lower(): value for key, value in self.headers.items()},
            "body": body,
        })

    def do_POST(self):  # noqa: N802（http.server 的约定命名）
        body = self._read_body()
        path = urlparse(self.path).path
        if path == "/api/training/create":
            self._record(body)
            if self.state.mode == "smoke_reject":
                self._reply(409, {"detail": {
                    "message": SMOKE_REASON,
                    "smoke_gate": {"digest": "ab12cd34", "required": True, "ok": False, "reason": SMOKE_REASON},
                }})
                return
            payload = {
                "success": True,
                "task_id": "unitree_go2_task_000000000001",
                "smoke_gate": {"digest": "ab12cd34", "required": True, "ok": True, "reason": None},
                "message": "Training task created successfully",
            }
            if self.headers.get("Idempotency-Key"):
                # 幂等重放：真实后端对重复 key 返回既有任务并带 idempotent_replay 标记
                payload["idempotent_replay"] = True
                payload["message"] = "Idempotent replay: returning existing task"
            self._reply(200, payload)
            return
        match = re.fullmatch(r"/api/training/([^/]+)/stop", path)
        if match:
            self._record(body)
            self._reply(200, {"success": True, "message": f"Training task {match.group(1)} stopped"})
            return
        self._record(body)
        self._reply(404, {"detail": f"unknown POST {path}"})

    def do_GET(self):  # noqa: N802（http.server 的约定命名）
        path = urlparse(self.path).path
        self._record(None)
        if path == "/api/training/list":
            self._reply(200, {"success": True, "tasks": [TASK_RUNNING, TASK_DONE], "count": 2})
            return
        match = re.fullmatch(r"/api/training/([^/]+)/status", path)
        if match:
            task_id = match.group(1)
            inner = TASK_DONE if task_id == TASK_DONE["task_id"] else dict(TASK_RUNNING, task_id=task_id)
            self._reply(200, {"success": True, "status": inner})
            return
        self._reply(404, {"detail": f"unknown GET {path}"})


@contextlib.contextmanager
def stub_backend(mode: str = "ok"):
    """起一个线程内 stub 后端（127.0.0.1 随机端口），yield ``(base_url, state)``。"""

    state = _StubState()
    state.mode = mode
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextlib.contextmanager
def refused_port():
    """占一个**绑定但不 listen** 的端口：连接必然被拒，用于测断连提示。"""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """以仓库根为 cwd 真调 CLI；强制 UTF-8，保证中文/JSON 在 Windows 管道下不乱码。"""

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [PYTHON, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(ROOT), env=env, timeout=180,
    )


class TrainCreateTest(unittest.TestCase):
    """``train create``：预设契约组装、task_id 输出、--json 完整响应、幂等键。"""

    def test_create_posts_preset_contract_and_prints_task_id(self):
        """人读输出打印 task_id 与冒烟门；stub 收到的 body 与预设契约/参数一致。"""
        with stub_backend() as (base, state):
            proc = run_cli(
                "train", "create", "--robot", "unitree_go2", "--profile", "go2-velocity-flat",
                "--envs", "16", "--iters", "5", "--seed", "7", "--smoke", "--base", base,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("unitree_go2_task_000000000001", proc.stdout)
            self.assertIn("冒烟前置门", proc.stdout)

            sent = state.last("POST", "/api/training/create")
            self.assertIsNotNone(sent)
            body = sent["body"]
            self.assertEqual("unitree_go2", body["contract"]["robot_id"])   # 契约来自预设
            self.assertEqual("PPO", body["algorithm"])
            self.assertEqual(16, body["num_envs"])
            self.assertEqual(5, body["max_iterations"])
            self.assertEqual(7, body["seed"])
            self.assertTrue(body["smoke"])
            self.assertEqual("go2-velocity-flat", body["profile_id"])
            self.assertEqual("forward_walk", body["task_name"])
            self.assertEqual("auto", body["device"])

    def test_create_json_outputs_full_response_with_smoke_gate(self):
        """--json 输出完整响应且可 json.loads，smoke_gate 字段原样在内。"""
        with stub_backend() as (base, _):
            proc = run_cli(
                "train", "create", "--robot", "unitree_go2", "--profile", "go2-velocity-flat",
                "--base", base, "--json",
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["success"])
            self.assertEqual("unitree_go2_task_000000000001", payload["task_id"])
            self.assertIn("smoke_gate", payload)                            # --json 含 smoke_gate 字段
            self.assertTrue(payload["smoke_gate"]["ok"])

    def test_create_sends_idempotency_key_header_and_reports_replay(self):
        """--key 变成 Idempotency-Key 请求头；重放响应里的人读输出标明幂等重放。"""
        with stub_backend() as (base, state):
            proc = run_cli(
                "train", "create", "--robot", "unitree_go2", "--profile", "go2-velocity-flat",
                "--key", "cli-test-key-1", "--base", base,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("幂等重放", proc.stdout)

            sent = state.last("POST", "/api/training/create")
            self.assertEqual("cli-test-key-1", sent["headers"].get("idempotency-key"))

    def test_create_contract_file_keeps_legacy_request_fields(self):
        """--contract 保留旧顶层 train <file> 用法：契约读文件、字段与默认规模不变。"""
        fixture = ROOT / "contracts" / "fixtures" / "unitree_go2.v2.json"
        with stub_backend() as (base, state):
            proc = run_cli(
                "train", "create", "--contract", str(fixture),
                "--envs", "8", "--iters", "3", "--base", base,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)

            sent = state.last("POST", "/api/training/create")
            body = sent["body"]
            self.assertEqual(json.loads(fixture.read_text(encoding="utf-8")), body["contract"])
            self.assertEqual(8, body["num_envs"])
            self.assertEqual(3, body["max_iterations"])
            self.assertEqual("native_mjlab", body["backend"])               # 旧用法的字段原样保留
            self.assertIsNone(body["profile_id"])

    def test_create_unknown_robot_fails_honestly(self):
        """未知机器人预设：CLI 如实报错（列出可用项），不去打扰后端。"""
        with stub_backend() as (base, state):
            proc = run_cli("train", "create", "--robot", "no_such_robot", "--base", base)
            self.assertNotEqual(0, proc.returncode)
            self.assertIn("no_such_robot", proc.stderr)
            self.assertIn("unitree_go2", proc.stderr)                       # 可用清单里给出正确选项
            self.assertIsNone(state.last("POST", "/api/training/create"))   # 没发请求


class TrainStatusTest(unittest.TestCase):
    """``train status``：解包**内层** status 词表，输出状态/迭代/奖励。"""

    def test_status_unwraps_inner_status_human_output(self):
        """人读输出：完成态 train_completed、迭代 5 / 5、奖励 12.5。"""
        with stub_backend() as (base, _):
            proc = run_cli("train", "status", TASK_DONE["task_id"], "--base", base)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("train_completed", proc.stdout)
            self.assertIn("5 / 5", proc.stdout)
            self.assertIn("12.5", proc.stdout)
            self.assertIn("已完成", proc.stdout)

    def test_status_running_task_shows_progress(self):
        """运行中任务：running、迭代 3 / 5、奖励 2.5。"""
        with stub_backend() as (base, _):
            proc = run_cli("train", "status", TASK_RUNNING["task_id"], "--base", base)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("running", proc.stdout)
            self.assertIn("3 / 5", proc.stdout)
            self.assertIn("2.5", proc.stdout)

    def test_status_json_parses_inner_status(self):
        """--json 输出可 json.loads，且 status 是内层词表（后端响应原样）。"""
        with stub_backend() as (base, _):
            proc = run_cli("train", "status", TASK_DONE["task_id"], "--base", base, "--json")
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["success"])
            self.assertEqual("train_completed", payload["status"]["status"])  # 内层才是词表
            self.assertEqual(12.5, payload["status"]["reward"])


class TrainStopListTest(unittest.TestCase):
    """``train stop`` / ``train list``：对应端点、表格与 --json。"""

    def test_stop_posts_and_confirms(self):
        """stop 打到 /api/training/<id>/stop，人读输出确认并回显后端消息。"""
        with stub_backend() as (base, state):
            proc = run_cli("train", "stop", TASK_RUNNING["task_id"], "--base", base)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("已请求停止", proc.stdout)
            self.assertIn("stopped", proc.stdout)

            sent = state.last("POST", f"/api/training/{TASK_RUNNING['task_id']}/stop")
            self.assertIsNotNone(sent)

    def test_list_human_output_is_table(self):
        """list 人读输出：两个 task_id、状态与汇总行都在。"""
        with stub_backend() as (base, _):
            proc = run_cli("train", "list", "--base", base)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn(TASK_RUNNING["task_id"], proc.stdout)
            self.assertIn(TASK_DONE["task_id"], proc.stdout)
            self.assertIn("train_completed", proc.stdout)
            self.assertIn("汇总：2 个任务", proc.stdout)

    def test_list_json_parses_tasks(self):
        """list --json 输出可 json.loads，tasks 数量与 stub 一致。"""
        with stub_backend() as (base, _):
            proc = run_cli("train", "list", "--base", base, "--json")
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(2, payload["count"])
            self.assertEqual([TASK_RUNNING["task_id"], TASK_DONE["task_id"]],
                             [task["task_id"] for task in payload["tasks"]])


class TrainFailureTest(unittest.TestCase):
    """失败路径：409 冒烟门拒、端口拒绝连接 —— 都必须非 0 退出且不编造结果。"""

    def test_smoke_gate_409_rejected_nonzero_with_reason(self):
        """stub 返回 409（冒烟门拒）：退出码非 0，输出含 reason 片段。"""
        with stub_backend(mode="smoke_reject") as (base, _):
            proc = run_cli(
                "train", "create", "--robot", "unitree_go2", "--profile", "go2-velocity-flat",
                "--envs", "4096", "--iters", "1000", "--base", base,
            )
            self.assertNotEqual(0, proc.returncode)
            combined = proc.stdout + proc.stderr
            self.assertIn("冒烟前置门拒绝", combined)                        # reason 片段可见
            self.assertIn("409", combined)

    def test_connection_refused_hint_mentions_backend(self):
        """端口拒绝连接：退出码非 0，中文提示含「后端」与可操作启动命令。"""
        with refused_port() as port:
            for args in (
                ("train", "list", "--base", f"http://127.0.0.1:{port}"),
                ("train", "create", "--robot", "unitree_go2", "--profile", "go2-velocity-flat",
                 "--base", f"http://127.0.0.1:{port}"),
            ):
                proc = run_cli(*args)
                self.assertNotEqual(0, proc.returncode, args)
                self.assertIn("后端", proc.stderr)
                self.assertIn("npm start", proc.stderr)                      # 可操作提示
                self.assertIn("uvicorn backend.api_complete:app", proc.stderr)
                self.assertNotIn("task_id", proc.stdout)                     # 不静默编造结果


class TrainHelpTest(unittest.TestCase):
    """命令契约：--help 写明在线语义（需后端），--json 两位置等价。"""

    def test_help_documents_online_semantics(self):
        """train 组与四个子命令的 --help 都写明「需后端」（在线命令语义）。"""
        proc = run_cli("train", "--help")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("需后端", proc.stdout)
        for subcommand in ("create", "status", "stop", "list"):
            proc = run_cli("train", subcommand, "--help")
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("需后端", proc.stdout)
            self.assertIn("在线命令", proc.stdout)

    def test_global_json_flag_before_train_subcommand(self):
        """全局 --json 放在子命令前同样生效（与离线命令的两位置约定一致）。"""
        with stub_backend() as (base, _):
            proc = run_cli("--json", "train", "list", "--base", base)
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(2, payload["count"])


if __name__ == "__main__":
    unittest.main()
