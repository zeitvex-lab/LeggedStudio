"""Playwright E2E 公共夹具：起一个真实 uvicorn 控制面，等就绪后再跑用例。

设计约束（踩过的坑，别再踩）：
  - 服务必须监听 0.0.0.0/127.0.0.1 的真实端口，不能 `file://` 直开页面：
    sim2sim 依赖 SharedArrayBuffer，后端中间件给 /web/sim2sim/* 加了
    COOP/COEP 头（backend/api_complete.py），file:// 下没有这些头，WASM 起不来。
  - 就绪判定用轮询 /health，不用固定 sleep（冷启动时间随机器差异很大）。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_healthy(base_url: str, timeout_s: float = 90.0) -> None:
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
    raise RuntimeError(f"control plane not healthy within {timeout_s}s: {last_error}")


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
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api_complete:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_healthy(url)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """让页面内 SharedArrayBuffer 可用；截图用固定视口，保证可比性。"""
    return {
        **browser_context_args,
        "viewport": {"width": 1440, "height": 900},
        "device_scale_factor": 1,
    }
