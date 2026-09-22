"""高级仿真页**布局** e2e：仿真视口优先，场景编辑器是可收起的浮层。

## 用户口径（2026-09-23）

> "基础仿真 UI 没问题，但高级仿真非常突兀地在左边加了个很复杂的 UI，同时大幅度挤占了
> 机器人仿真的空间，请修复。"

现场：`advanced_sim.html` 里编辑器是 `flex: 0 0 340px` 的**实占布局** ⇒ 1440 宽的窗口里
机器人视口只剩 ~1100；在更窄的窗口上更明显。修法：编辑器改成**浮层 + 可收起**（默认收起、
选择记 localStorage），并给顶栏加一个常驻「启动仿真」，避免"收起后启动不了"。

## 本文件锁四件事（都是这次修复的判据）

1. **默认收起** —— 首访不该一上来就盖住仿真；
2. **收起/展开都不挤仿真** —— 浮层开合时 iframe 宽度**必须不变**（这条是核心：回归"实占布局"就会红）；
3. **顶栏启动按钮与编辑器内那个同权** —— 禁用态同步、且真能启动（收起状态下点了要能跑）；
4. **Esc 可收起** —— 键盘出口。
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = [pytest.mark.e2e]

URL_PATH = "/web/advanced_sim.html"


def _open(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}{URL_PATH}", wait_until="domcontentloaded")
    page.wait_for_selector("#advSimFrame", timeout=60_000)
    # 等编辑器 init **真的跑完**再动手：init 里的取数（地图/机器人/策略/任务插件）耗时随机器差异大，
    # 固定 sleep 会在慢机器上"点了个还没绑上事件的按钮"（实测就是这么 flake 的）。
    # 判据取顶栏摘要 —— 它在 init 末尾的 `refresh()` 里写，且始终可见（不受浮层开合影响）。
    page.wait_for_function(
        "() => { const el = document.getElementById('scSummary');"
        " return el && el.textContent && !el.textContent.includes('尚未生成场景'); }", timeout=60_000)


def _frame_width(page: Page) -> float:
    return page.evaluate("() => document.getElementById('advSimFrame').getBoundingClientRect().width")


def _panel_visible(page: Page) -> bool:
    return page.evaluate(
        """() => {
          const el = document.getElementById('scEditorPanel');
          if (!el) return false;
          const r = el.getBoundingClientRect();
          // 收起态是 translateX(-102%)，元素仍在 DOM 里 —— 判"可见"要看它是否真在视口内，
          // 不能只看 display（这正是浮层最容易写成"看着收了其实还在挡"的地方）。
          return r.right > 8 && r.left < window.innerWidth - 8;
        }"""
    )


def test_editor_is_collapsed_by_default_and_does_not_squeeze_the_sim(base_url: str, page: Page) -> None:
    _open(page, base_url)
    assert not _panel_visible(page), "首访不该默认展开编辑器（会盖住/挤占仿真视口）"
    assert page.get_attribute("#advEditorToggle", "aria-expanded") == "false"
    frame = _frame_width(page)
    body = page.evaluate("() => document.querySelector('.adv-body').getBoundingClientRect().width")
    assert frame >= body - 2, f"仿真视口没有占满容器：iframe={frame} 容器={body}"


def test_opening_the_editor_does_not_change_the_sim_viewport(base_url: str, page: Page) -> None:
    """**核心判据**：浮层开合不改变 iframe 宽度（实占布局回归的话，这里会立刻变小 340）。"""

    _open(page, base_url)
    before = _frame_width(page)
    page.click("#advEditorToggle")
    page.wait_for_timeout(400)
    assert _panel_visible(page), "点了「场景编辑器」但浮层没出来"
    assert page.get_attribute("#advEditorToggle", "aria-expanded") == "true"
    assert page.inner_text("#advEditorToggle").strip() == "收起编辑器"
    after = _frame_width(page)
    assert abs(after - before) < 1.5, f"展开编辑器把仿真视口挤窄了：{before} → {after}"

    # Esc 收起，且宽度仍然不变
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assert not _panel_visible(page), "Esc 没收起浮层"
    assert abs(_frame_width(page) - before) < 1.5


def test_top_bar_start_button_shares_gate_with_the_editor_one(base_url: str, page: Page) -> None:
    """顶栏的常驻「启动仿真」与编辑器内那个**同权**：禁用态同步；收起状态下点了真能启动。"""

    _open(page, base_url)
    # 默认场景（go2 平地速度追踪）必然可跑 ⇒ 两个按钮都该是可用状态
    page.wait_for_function(
        "() => document.getElementById('scStart').disabled === false"
        " && document.getElementById('scStartTop').disabled === false", timeout=30_000)

    page.click("#scStartTop")
    # 先等到"已启动"（start() 自己写的）或"生效"（仿真页回执覆盖的）——两者都表示真的启动了；
    # `#scLastLaunch` 在浮层里，收起时 `inner_text` 取不到，故一律读 textContent。
    page.wait_for_function(
        "() => { const t = document.getElementById('scLastLaunch').textContent || '';"
        " return t.includes('已启动') || t.includes('生效') || t.includes('拒收'); }", timeout=30_000)
    launched = page.eval_on_selector("#scLastLaunch", "el => el.textContent || ''")
    assert "拒收" not in launched, f"仿真页拒收了场景：{launched!r}"
    src = page.eval_on_selector("#advSimFrame", "el => el.src")
    assert "surface=advanced" in src and "autoplay=1" in src, f"iframe 没按场景重写：{src}"
    # 交运回执：默认场景（policy 驱动）在高级面上**不该**再报"运行面 basic 需在打开页面时指定"
    # （那个 skip 是页面自己造成的噪声：高级面跑基础场景是常态，见 app.js 的运行面判据）
    page.wait_for_function(
        "() => (document.getElementById('scLastLaunch').textContent || '').includes('生效')", timeout=30_000)
    receipt = page.eval_on_selector("#scLastLaunch", "el => el.textContent || ''")
    assert "运行面" not in receipt, f"高级面跑基础场景仍白报运行面未应用：{receipt!r}"
    # 启动后应自动收起浮层（把视口让给仿真），且按钮回到"可再启动"
    assert not _panel_visible(page), "启动后浮层没自动收起"
    assert page.is_enabled("#scStartTop")

    # 把场景改坏（planner 无航点）⇒ 两个按钮必须同时禁用（不许一个亮一个灭）
    page.click("#advEditorToggle")
    page.wait_for_timeout(300)
    # 编辑器一次只显示当前步骤的段：`command_source` 在「任务」段，不先切过去它不可见
    page.click('#scSteps [data-step="task"]')
    page.wait_for_selector("#scCommandSource", state="visible", timeout=30_000)
    page.select_option("#scCommandSource", "planner")
    page.wait_for_function(
        "() => document.getElementById('scStart').disabled === true"
        " && document.getElementById('scStartTop').disabled === true", timeout=30_000)
