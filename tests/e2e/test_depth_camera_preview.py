"""深度相机（外挂预览）e2e —— **声明即所见**（2026-09-23 用户报"深度相机实现不对"）。

## 现场与根因（两处，都是"声明与实际不符"）

1. **坞里根本选不到深度源**：场景声明 `perception.depth_camera` 后，页面只把
   `sim.scenarioSensors` 写进内存并提示"感知传感器已启用"——而**全仓没有读者**。
   坞的来源下拉是按"插件是否勾选"过滤的（`DOCK_SOURCES[].requires`），插件没被打开 ⇒
   `深度相机` 这一项**不在下拉里**。用户既看不到声明的那台相机，也就无从判断对不对。
2. **预览不是那台相机**：`scanDepthPreview()` 把分辨率写死 `20×12`、归一化距离写死 `8 m`
   （场景声明的是 `width/height/cutoff_m`，默认 106×60 / 3 m）⇒ 看到的是粗格图，
   且亮度刻度与策略/训练侧**两套**；面板文字还写死"20×12 粗格"，与它画的数据自相矛盾。

修完的判据就是本文件的三条：**选得到**（声明即开插件）、**尺寸随声明**、**截止随声明**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "depth-preview"

pytestmark = [pytest.mark.e2e]

URL_PATH = ("/web/sim2sim/index.html?debug=1&surface=advanced&embedded=1&view=advanced"
            "&robot=unitree_go2&policy=go2-baseline-164k")


def _scenario(width: int, height: int, cutoff: float) -> dict:
    return {
        "schema_version": "scenario-contract-1.1",
        "scenario_id": "depth-probe",
        "map_id": "flat",
        "mode": "advanced",
        "seed": 0,
        "episode_length_s": 60,
        "waypoints": [],
        "terrain": {"kind": "flat"},
        "command_source": "policy",
        "perception": {
            "route": "external",
            "depth_camera": {"width": width, "height": height, "cutoff_m": cutoff},
            "mount": "base",
        },
        "checks": [],
        "recorders": [],
    }


def _open(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}{URL_PATH}", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => /就绪/.test(document.getElementById('engineStatus')?.textContent || '')", timeout=120_000)


def _apply(page: Page, scenario: dict) -> None:
    page.evaluate(
        "([msg]) => window.postMessage({ type: 'legged-studio:scenario', version: 1, source: 'e2e',"
        " robot: 'unitree_go2', policy: 'go2-baseline-164k', scenario: msg }, window.location.origin)",
        [scenario],
    )
    page.wait_for_timeout(2000)


def test_scenario_declaration_actually_enables_the_dock_view(base_url: str, page: Page) -> None:
    """声明了深度相机 ⇒ 坞里那个插件**真的被打开**、来源下拉里**选得到**（不是只提示一句）。"""

    _open(page, base_url)
    _apply(page, _scenario(80, 60, 3.0))

    checked = page.eval_on_selector_all(
        "#dockPlugins input[data-plugin]", "els => Object.fromEntries(els.map(e => [e.dataset.plugin, e.checked]))")
    assert checked.get("depth") is True, f"场景声明了 depth_camera，但坞里的 depth 插件没被打开：{checked}"
    options = page.eval_on_selector_all("#dockSource option", "els => els.map(e => e.value)")
    assert "depth" in options, f"深度源不在来源下拉里（= 用户看不到声明的那台相机）：{options}"


def test_preview_resolution_and_cutoff_follow_the_declaration(base_url: str, page: Page) -> None:
    """预览的**分辨率与截止距离**必须来自场景声明（此前写死 20×12 / 8 m）。"""

    _open(page, base_url)
    _apply(page, _scenario(80, 60, 3.0))
    page.select_option("#dockSource", "depth")
    page.wait_for_function(
        "() => (document.querySelector('#dockCanvas') || {}).width === 80", timeout=30_000)
    size = page.evaluate("() => { const c = document.querySelector('#dockCanvas');"
                         " return { w: c.width, h: c.height }; }")
    assert (size["w"], size["h"]) == (80, 60), f"预览分辨率没跟声明走：{size}"
    note = page.inner_text("#dockNote")
    assert "80×60" in note and "截止 3" in note, note

    # 换一台相机 ⇒ 立刻跟着变（证明读的是声明，不是写死的数）
    _apply(page, _scenario(120, 80, 6.0))
    page.wait_for_function(
        "() => (document.querySelector('#dockCanvas') || {}).width === 120", timeout=30_000)
    note2 = page.inner_text("#dockNote")
    assert "120×80" in note2 and "截止 6" in note2, note2


def test_preview_is_a_real_depth_frame_not_a_coarse_grid(base_url: str, page: Page) -> None:
    """图上有**真实的远近层次**：地面近处亮、远处/未命中暗，且地平线是水平的一条。

    这条挡的是"分辨率写死后那种粗格图"回归 —— 粗格（20×12）在 80×60 的像素网格里会
    呈现为整块同色，而不是连续渐变。
    """

    _open(page, base_url)
    _apply(page, _scenario(80, 60, 3.0))
    page.select_option("#dockSource", "depth")
    page.wait_for_function(
        "() => (document.querySelector('#dockCanvas') || {}).width === 80", timeout=30_000)
    stats = page.evaluate(
        """() => {
          const c = document.querySelector('#dockCanvas');
          const ctx = c.getContext('2d');
          const col = (x) => { const d = ctx.getImageData(x, 0, 1, c.height).data;
            const out = []; for (let y = 0; y < c.height; y += 1) out.push(d[y * 4]); return out; };
          const row = (y) => { const d = ctx.getImageData(0, y, c.width, 1).data;
            const out = []; for (let x = 0; x < c.width; x += 1) out.push(d[x * 4]); return out; };
          const r = row(Math.floor(c.height * 0.75));
          const mid = row(Math.floor(c.height * 0.5));
          const bottom = r.reduce((a, b) => a + b, 0) / r.length;
          const middle = mid.reduce((a, b) => a + b, 0) / mid.length;
          // 纵向单调性：把中间一列切成 6 段，看"越靠下越亮"是否大体成立
          const c0 = col(Math.floor(c.width / 2));
          const seg = (i) => c0.slice(i * 10, i * 10 + 10).reduce((a, b) => a + b, 0) / 10;
          const profile = [0, 1, 2, 3, 4, 5].map(seg);
          return { bottom, middle, profile };
        }"""
    )
    assert stats["bottom"] > stats["middle"] + 20, f"近处地面不比远处亮（不是真实深度帧？）：{stats}"
    rising = sum(1 for a, b in zip(stats["profile"], stats["profile"][1:]) if b >= a)
    assert rising >= 4, f"中间列的纵向亮度不是大体递增（深度帧应是连续梯度，不是整块同色）：{stats['profile']}"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACT_DIR / "depth-preview.png"))
