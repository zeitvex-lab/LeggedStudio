"""浏览器 sim2sim 端到端验收：起真实后端 → 打开页面 → 确定性回放 → 采样/截图。

这是「浏览器是刚需」那条需求的闭环：同一 URL（策略 + 模型 + seed）在任何机器
上回放出同一条轨迹，因此这里的断言与截图都可以作为回归判据。

前置：页面必须通过 FastAPI 访问（COOP/COEP 头 → SharedArrayBuffer），
故 base_url 由 conftest 提供，不用 file://。

运行：
    pip install pytest playwright pytest-playwright && playwright install chromium
    pytest tests/e2e -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "workspace" / "e2e-screenshots"

# 页面就绪判据：loading 遮罩加上 is-hidden（app.js 在 sim.ready 置位后隐藏 loading）。
# 注意用 state="attached"，不能用默认的 visible —— is-hidden 本身就把元素设为不可见，
# 等 visible 会永远等不到。
READY_TIMEOUT_MS = 180_000


def _open_sim2sim(page: Page, base_url: str, query: str = "") -> None:
    url = f"{base_url}/web/sim2sim/index.html?debug=1{query}"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_MS)


def _first_robot(base_url: str) -> str:
    import urllib.request

    with urllib.request.urlopen(f"{base_url}/api/robots/presets") as response:
        payload = json.loads(response.read().decode("utf-8"))
    presets = payload.get("presets") or []
    assert presets, "no robot presets exposed by /api/robots/presets"
    return presets[0]["robot_id"]


def test_sim2sim_page_loads_and_exposes_debug_probe(page: Page, base_url: str):
    _open_sim2sim(page, base_url)
    state = page.evaluate("() => window.__sim2simDebug.state()")
    # 调试状态里模型已构建、物理已推进过时间
    assert state["model"] is not None

    # __probe 由渲染循环写入，等一帧；用轮询而非固定等待。
    page.wait_for_function("() => window.__probe && Number.isFinite(window.__probe.z)",
                           timeout=30_000)
    probe = page.evaluate("() => window.__probe")
    assert isinstance(probe["z"], (int, float))


def test_deterministic_replay_is_stable(page: Page, base_url: str):
    """同一 replay 指令 + seed，两次加载采样必须逐字段一致（确定性契约）。"""
    robot = _first_robot(base_url)
    query = f"&robot={robot}&replay=0.6,0,0&seed=42"

    _open_sim2sim(page, base_url, query)
    first = page.evaluate("async () => await window.__sim2simDebug.fastForward(1.0)")

    _open_sim2sim(page, base_url, query)
    second = page.evaluate("async () => await window.__sim2simDebug.fastForward(1.0)")

    assert first["cmd"] == pytest.approx(second["cmd"])
    # 基座高度与姿态是可复现的回放指纹
    assert first["baseZ"] == pytest.approx(second["baseZ"], abs=1e-6)
    assert first["quat"] == pytest.approx(second["quat"], abs=1e-6)


def test_robot_survives_replay_and_can_be_captured(page: Page, base_url: str):
    """回放 2 秒后机器人未摔（骨盆高度保持在合理区间），并落一张对比截图。"""
    robot = _first_robot(base_url)
    _open_sim2sim(page, base_url, f"&robot={robot}&replay=0.6,0,0&seed=42")

    sample = page.evaluate("async () => await window.__sim2simDebug.fastForward(2.0)")
    assert sample["baseZ"] is not None and sample["baseZ"] > 0.05, f"robot fell: {sample}"

    # fastForward 期间渲染循环被暂停，恢复后要让相机/场景同步几帧再截图，
    # 否则无头 Chromium 可能抓到空白视口（实测：不等待会得到只有 HUD 的图）。
    page.evaluate("() => window.__sim2simDebug.setPaused(false)")
    page.wait_for_function("() => window.__probe && window.__probe.z !== null", timeout=30_000)
    page.wait_for_timeout(1500)

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    shot = SCREENSHOT_DIR / f"sim2sim-{robot}-replay.png"
    page.screenshot(path=str(shot))
    assert shot.is_file() and shot.stat().st_size > 0
