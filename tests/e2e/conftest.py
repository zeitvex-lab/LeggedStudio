"""Playwright E2E 公共夹具：起一个真实 uvicorn 控制面，等就绪后再跑用例。

设计约束（踩过的坑，别再踩）：
  - 服务必须监听 0.0.0.0/127.0.0.1 的真实端口，不能 `file://` 直开页面：
    sim2sim 依赖 SharedArrayBuffer，后端中间件给 /web/sim2sim/* 加了
    COOP/COEP 头（backend/api_complete.py），file:// 下没有这些头，WASM 起不来。
  - 就绪判定用轮询 /health，不用固定 sleep（冷启动时间随机器差异很大）。
  - 子进程日志必须重定向到**文件**，绝不能用 `subprocess.PIPE` 后不读：
    启动期就有数 KB 输出，管道缓冲写满会把整个服务阻塞成"页面全部超时"
    （曾被误判为机器争抢/假红），排查时看这里落盘的日志即可。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_healthy(base_url: str, timeout_s: float = 90.0, log_path: Path | None = None) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:  # server still warming up
            last_error = exc
        time.sleep(0.5)
    tail = ""
    if log_path and log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = "\n--- server log tail ---\n" + "\n".join(lines[-20:])
    raise RuntimeError(f"control plane not healthy within {timeout_s}s: {last_error}{tail}")


@pytest.fixture(scope="session")
def base_url() -> str:
    """会话级：整个 e2e 只起一次后端。"""
    external = os.environ.get("LEGGED_STUDIO_E2E_BASE_URL")
    if external:
        _wait_healthy(external.rstrip("/"))
        yield external.rstrip("/")
        return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    log_path = Path(tempfile.gettempdir()) / f"legged-studio-e2e-{port}.log"
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api_complete:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=log_file, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_healthy(url, log_path=log_path)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--sweep", action="store_true", default=False,
        help="跑全量逐机型浏览器 sweep（默认只跑冒烟机型，见 test_all_models.py）",
    )


def pytest_configure(config) -> None:
    # 标记在 e2e conftest 里注册即可，不动 pyproject 的全局 markers 清单。
    config.addinivalue_line(
        "markers", "sweep: 逐机型全量 sweep（默认跳过；--sweep 或 LEGGED_STUDIO_E2E_SWEEP=1 显式触发）",
    )
    config.addinivalue_line("markers", "smoke: 冒烟机型（默认档进 CI）")


def pytest_collection_modifyitems(config, items) -> None:
    sweep_enabled = config.getoption("--sweep") or os.environ.get("LEGGED_STUDIO_E2E_SWEEP") == "1"
    if sweep_enabled:
        return
    skip = pytest.mark.skip(reason="全量逐机型 sweep 默认跳过：用 --sweep 或 LEGGED_STUDIO_E2E_SWEEP=1 显式触发")
    for item in items:
        if item.get_closest_marker("sweep") and not item.get_closest_marker("smoke"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """让页面内 SharedArrayBuffer 可用；截图用固定视口，保证可比性。"""
    return {
        **browser_context_args,
        "viewport": {"width": 1440, "height": 900},
        "device_scale_factor": 1,
    }
