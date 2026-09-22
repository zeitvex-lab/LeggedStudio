"""高级仿真页「任务插件」消费的**浏览器实测**（真 uvicorn + 真 Chromium，H 组任务插件闭环）。

## 为什么值得一条 e2e

任务插件的服务端半边此前只有单测（`backend/test_task_plugins.py`）：接口能列出、能实例化
—— 但**页面上到底有没有这个入口、点下去表单会不会真的变**，单测一条都答不了。本仓对
"两个文件靠字符串对齐"的耦合一贯做法是写成测试（`scenario_editor_ui.test.mjs` 就是），
那条只核 id 存在；**真点一遍**只有浏览器能给证据。

## 口径（与 `test_ui_audit*.py` 一致）

* 页面自身 JS 错误 / console error ⇒ **失败**；
* 资源加载类 console error（`Failed to load resource`）按 URL 归类为 `resource_errors`，
  如实记录但不拦（数据缺失类降级是页面设计行为）；
* 就绪度文案**必须诚实**：传感器插件当前止步 `registered` ⇒ 只能写"声明可实例化"，
  页面上出现"已验证"这类字样即为缺陷（本用例专门断言这一点）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "task-plugin"

_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

pytestmark = [pytest.mark.e2e]


def _watch(page: Page) -> dict[str, list[str]]:
    watched: dict[str, list[str]] = {"page_errors": [], "console_errors": [], "resource_errors": []}
    page.on("pageerror", lambda exc: watched["page_errors"].append(str(exc)[:400]))

    def _on_console(msg) -> None:
        if msg.type != "error":
            return
        text = str(msg.text or "")
        if _RESOURCE_CONSOLE_NOISE.search(text):
            return
        watched["console_errors"].append(text[:400])

    page.on("console", _on_console)
    page.on("response", lambda response: watched["resource_errors"].append(f"{response.status} {response.url}")
            if response.status >= 400 and not _BENIGN_RESOURCE.search(response.url) else None)
    return watched


def _shot(page: Page, name: str) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACT_DIR / name))


def _open_editor(page: Page, base_url: str) -> dict[str, list[str]]:
    """打开编辑器并等到**任务插件清单真的来自服务端**（不是"不可用"占位）。"""

    watched = _watch(page)
    page.goto(f"{base_url}/web/advanced_sim.html", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => { const sel = document.getElementById('scTaskPlugin');"
        " return sel && sel.options.length > 1 && !(sel.textContent || '').includes('不可用'); }",
        timeout=60_000,
    )
    return watched


def _goto_task_step(page: Page) -> None:
    """编辑器一次只显示当前步骤的段（`scenario_editor_ui.selectStep`）——任务插件在「任务」段，
    不先切过去它**不可见**（Playwright 会拒绝对不可见元素操作）。

    这条是浏览器实测才能发现的接线前提：纯 DOM id 测试与纯逻辑测试都不会暴露它。
    """

    page.click('#scSteps [data-step="task"]')
    page.wait_for_selector("#scTaskPlugin", state="visible", timeout=30_000)


def test_dropdown_lists_server_registry(base_url: str, page: Page) -> None:
    """下拉里的每一条都来自 `GET /api/task-plugins`（页面不编清单）。"""

    watched = _open_editor(page, base_url)
    options = page.eval_on_selector_all(
        "#scTaskPlugin option",
        "els => els.map(e => ({ value: e.value, text: e.textContent }))",
    )
    assert len(options) >= 10, f"内置任务插件应有 ≥10 条，实际 {len(options)}：{options[:3]}"
    values = {item["value"] for item in options}
    assert {"odom-waypoint-nav", "wheel-leg-terrain"} <= values, values
    assert all(item["text"].strip() for item in options), "下拉项不许有空标签"
    assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    _shot(page, "dropdown.png")


def test_one_click_fill_applies_server_scenario(base_url: str, page: Page) -> None:
    """「一键填入」把服务端实例化结果写进表单，并且**不谎称能跑**。"""

    watched = _open_editor(page, base_url)
    _goto_task_step(page)
    page.select_option("#scTaskPlugin", "wheel-leg-terrain")
    page.click("#scTaskFill")
    page.wait_for_function(
        "() => document.getElementById('scTaskPluginResult').textContent.includes('已填入')",
        timeout=60_000,
    )

    # ① 服务端补的字段真的落到了表单上（A 类：感知进观测）
    assert page.input_value("#scRoute") == "obs"
    assert page.is_checked("#scHeightfield") is True
    assert page.is_checked("#scFootContact") is True
    assert page.is_checked("#scDepthCamera") is False, "插件没声明深度 ⇒ 不许顺手打开"

    # ② 诚实面：只许说"声明可实例化"，不许说"能跑"/"已验证"
    text = page.inner_text("#scTaskPluginResult")
    assert "声明可实例化" in text, text
    assert "不能声称" in text, text
    assert "已验证" not in text, f"就绪度文案越界（传感器插件止步 registered）：{text}"

    # ③ 标题栏摘要跟着更新（说明填进去的确实是 A 类感知场景）
    summary = page.inner_text("#scSummary")
    assert "感知 obs" in summary, summary

    # ④ 场景仍能通过服务端校验（填入后的表单是自洽的）
    page.click("#scValidate")
    page.wait_for_function(
        "() => document.getElementById('scReport').textContent.includes('服务端场景校验')",
        timeout=30_000,
    )
    report = page.inner_text("#scReport")
    assert "服务端场景校验：通过" in report, report

    assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    assert watched["console_errors"] == [], f"console error：{watched['console_errors']}"
    _shot(page, "filled-wheel-leg-terrain.png")


def test_planner_task_asks_for_waypoints_instead_of_silently_passing(base_url: str, page: Page) -> None:
    """`odom-waypoint-nav` 是 planner 驱动 ⇒ 填入后必须**显出航点区**且因缺航点判不合法。

    这是"填入 ≠ 一键跑起来"的边界：插件负责"这个任务要什么"，**目标点得人给**
    （契约：`planner|perception ⇒ 必须有航点`）。页面在这里如实拦住，而不是让它启动。
    """

    watched = _open_editor(page, base_url)
    _goto_task_step(page)
    page.select_option("#scTaskPlugin", "odom-waypoint-nav")
    page.click("#scTaskFill")
    page.wait_for_function(
        "() => document.getElementById('scTaskPluginResult').textContent.includes('已填入')",
        timeout=60_000,
    )

    assert page.input_value("#scCommandSource") == "planner"
    assert page.is_hidden("#scWaypointsRow") is False, "planner 驱动必须显出航点编辑区"
    assert page.is_disabled("#scStart") is True, "缺航点不许启动（契约硬约束）"
    report = page.inner_text("#scReport")
    assert "航点" in report, report

    # 补一个航点 ⇒ 恢复可启动（证明拦的是"缺目标"，不是别的）
    page.fill("#scWaypoints", "1,1\n2,2")
    page.wait_for_function(
        "() => document.getElementById('scStart').disabled === false",
        timeout=30_000,
    )
    assert watched["page_errors"] == [], f"页面 JS 异常：{watched['page_errors']}"
    _shot(page, "filled-odom-waypoint.png")
