"""任务坞 E2E —— 「任务 = 机器人的插件」从选任务到判据报告的**全链路**（高级仿真）。

与既有 e2e 的分工（不重复）：
    test_navigation_route.py  URL 直驱导航（?nav=...）：证明 planner 跟随链路本身；
    test_policy_yaw_hold.py   单策略姿态遍历存活；
    → 本文件补**任务坞入口**：用户在页面上选任务档（registry/tasks）→ 服务端组装
      （/api/task-profiles/{id}/assemble）→ 「应用到仿真」→ applyScenario →
      planner 导航执行 → 场景面板出判据报告。这是"任务插件层"的用户面入口——
      2026-09-30 盘点时它曾是**假面**：apply 按钮无 handler、选中只实例化错误 id
      空间、app.js 导入名对不上导致整页起不来；本用例把"选任务真能跑、跑完真出
      判据"钉成回归锁。

**断言分层（与 test_navigation_route.py 同一口径）**：
  * 链路级缺陷 ⇒ **测试失败**：任务坞不可见/下拉为空、goal_nav 组装带阻断、应用被拒、
    导航未接线（payload 缺 follow_controller 或 arrival）、fastForward 异常、
    页面自身 JS 错误、跑完场景面板没有判据报告；
  * 控制器短板（follow 过冲/振荡，90s 内到达判据不触发）⇒ **如实记录**到基线
    （arrived=false + classification），不因 H12 短板失败——那是 follow_controller 的任务。

顺带钉住**诚实阻断**：选 traversal（availability 无 browser）⇒ 读出阻断原因 +
「应用到仿真」禁用（声明可跑 ≠ 能跑）。

机型/策略：unitree_go2 + go2-rlsar-robotlab（与 test_navigation_route.py 同口径，
Windows 实测 baseZ 稳定 0.33 的导航机型）；环境变量
LEGGED_STUDIO_E2E_NAV_ROBOT / _POLICY 覆盖。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_task_dock_apply.py -v
"""

from __future__ import annotations

import json
import math
import os
import platform as py_platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "task-dock"

READY_TIMEOUT_S = float(os.environ.get("LEGGED_STUDIO_E2E_MODEL_TIMEOUT_S", "120"))
#: 仿真时长上限（场景 episode 60s + 余量给转弯/恢复）
TASK_SIM_SECONDS = float(os.environ.get("LEGGED_STUDIO_E2E_TASK_SIM_SECONDS", "90"))
FF_CHUNK_S = float(os.environ.get("LEGGED_STUDIO_E2E_FF_CHUNK_S", "10"))

ROBOT_ID = os.environ.get("LEGGED_STUDIO_E2E_NAV_ROBOT", "unitree_go2")
POLICY_ID = os.environ.get("LEGGED_STUDIO_E2E_NAV_POLICY", "go2-rlsar-robotlab")

_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

pytestmark = [pytest.mark.e2e]


def _git_state() -> dict:
    try:
        commit = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=20, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", timeout=20, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return {"commit": commit, "dirty": bool(status.strip())}


@pytest.fixture(scope="module")
def task_dock_result(request):
    """模块级结果收集器：收尾落基线 JSON + 截图路径，供回归对比。"""
    row: dict = {}
    yield row
    if not row:
        return
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "task-dock-browser-1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "surface": "web/sim2sim/index.html?surface=advanced（任务坞 → /api/task-profiles 组装 → 应用）",
        "mode": "e2e",
        "provenance": {
            "product_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip()
            if (ROOT / "VERSION").is_file() else None,
            "git": _git_state(),
            "platform": py_platform.platform(),
            "python": sys.version.split()[0],
            "browser": "playwright chromium (headless)",
            "robot": ROBOT_ID,
            "policy": POLICY_ID,
        },
        "result": row,
    }
    (ARTIFACT_DIR / "task_dock_baseline.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@pytest.fixture()
def console_watch(page):
    """JS 错误三分类收集（与 test_navigation_route.py 同口径）。"""
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

    def _on_response(response) -> None:
        if response.status >= 400 and not _BENIGN_RESOURCE.search(response.url):
            watched["resource_errors"].append(f"{response.status} {response.url}")

    page.on("response", _on_response)
    page.on(
        "requestfailed",
        lambda req: watched["resource_errors"].append(f"FAILED {req.url} {req.failure}")
        if not _BENIGN_RESOURCE.search(req.url) else None,
    )
    return watched


def _wait_ready(page: pytest, base_url: str) -> list[str]:
    """打开高级仿真页并等到策略会话就绪；返回链路问题列表（空 = 就绪）。"""
    problems: list[str] = []
    url = (
        f"{base_url}/web/sim2sim/index.html?debug=1&surface=advanced&view=advanced"
        f"&robot={ROBOT_ID}&policy={POLICY_ID}&terrain=flat"
    )
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_S * 1000)
    except Exception as exc:
        problems.append(f"页面未在 {READY_TIMEOUT_S:.0f}s 内就绪: {exc}")
        return problems
    try:
        page.wait_for_function(
            "() => window.__sim2simDebug?.sample?.()?.policyLoaded === true",
            timeout=READY_TIMEOUT_S * 1000,
        )
    except Exception as exc:
        problems.append(f"策略会话未在 {READY_TIMEOUT_S:.0f}s 内加载: {exc}")
    return problems


def test_task_dock_goal_navigation(page, base_url: str, console_watch, task_dock_result):
    """选 goal_nav_warehouse → 组装无阻断 → 应用 → 导航执行 → 判据报告可见。"""
    row = task_dock_result
    row.update({
        "robot": ROBOT_ID, "policy_id": POLICY_ID,
        "task_id": "goal_nav_warehouse",
        "dock_visible": False, "options_filled": False,
        "blocked_task_honest": None, "assembled": False, "apply_enabled": False,
        "applied": False, "nav_wired": False,
        "followed": False, "arrived": False, "termination_reason": None,
        "summary_rendered": False, "summary_passed": None,
        "final_pose": None, "final_error_m": None,
        "sim_time_s": None, "screenshot": None,
        "ok": False, "problems": [], "classification": None,
        **{k: [] for k in ("page_errors", "console_errors", "resource_errors")},
    })
    problems: list[str] = []
    link_problems: list[str] = []

    ready_problems = _wait_ready(page, base_url)
    problems.extend(ready_problems)
    if ready_problems:
        row["problems"] = problems
        pytest.fail(f"链路级缺陷（页面/策略未就绪）：{ready_problems}")

    # ① 任务坞可见、下拉由服务端清单填充（goal_nav_warehouse 在列）。
    # 注意 <option> 在闭合 <select> 里是零尺寸盒（Playwright 判 hidden），
    # 用 wait_for_function 查选项存在性，不查可见性。
    try:
        page.wait_for_function(
            "() => !!document.querySelector(\"#taskDockSelect option[value='goal_nav_warehouse']\")",
            timeout=15_000,
        )
        row["dock_visible"] = page.is_visible("#taskDock")
        row["options_filled"] = page.eval_on_selector(
            "#taskDockSelect", "el => el.options.length"
        )
    except Exception as exc:
        link_problems.append(f"任务坞没有 goal_nav_warehouse 选项（服务端清单未接通？）: {exc}")
    if link_problems:
        row["problems"] = problems + link_problems
        pytest.fail(f"链路级缺陷：{link_problems}")

    # ② 诚实阻断：traversal 未声明浏览器端口 ⇒ 应用按钮禁用 + 原因可见
    page.select_option("#taskDockSelect", "traversal_obstacle_course")
    try:
        page.wait_for_function(
            "() => (document.querySelector('#taskDockReadout')?.textContent || '').includes('浏览器不可跑')",
            timeout=10_000,
        )
        apply_disabled = page.eval_on_selector("#taskDockApply", "el => el.disabled")
        row["blocked_task_honest"] = bool(apply_disabled)
    except Exception as exc:
        row["blocked_task_honest"] = False
        problems.append(f"traversal 阻断未如实展示（或应用按钮未禁用）: {exc}")

    # ③ 选 goal_nav_warehouse：组装无阻断、应用按钮点亮
    page.select_option("#taskDockSelect", "goal_nav_warehouse")
    try:
        page.wait_for_function(
            "() => (document.querySelector('#taskDockReadout')?.textContent || '').includes('已组装')",
            timeout=15_000,
        )
        row["assembled"] = True
        row["apply_enabled"] = page.eval_on_selector("#taskDockApply", "el => !el.disabled")
    except Exception as exc:
        link_problems.append(f"goal_nav 组装未就绪（组装带阻断或接口异常）: {exc}"
                             + f"｜readout={page.eval_on_selector('#taskDockReadout', 'el => el.textContent')}")
    if link_problems:
        row["problems"] = problems + link_problems
        pytest.fail(f"链路级缺陷：{problems + link_problems}")

    # ④ 应用 → applyScenario → planner 导航接线
    page.click("#taskDockApply")
    try:
        page.wait_for_function(
            "() => (document.querySelector('#taskDockReadout')?.textContent || '').includes('已应用')",
            timeout=30_000,
        )
        row["applied"] = True
    except Exception as exc:
        link_problems.append(
            f"应用未成功：{exc}｜readout={page.eval_on_selector('#taskDockReadout', 'el => el.textContent')}"
        )
    nav = None
    try:
        nav = page.evaluate("() => window.__sim2simDebug.navigation()")
    except Exception as exc:
        link_problems.append(f"navigation() 调用失败: {exc}")
    if not nav:
        link_problems.append("应用后导航未接线（__sim2simDebug.navigation() 为空）")
    else:
        row["nav_wired"] = True
        payload = nav.get("payload") or {}
        if not (payload.get("follow_controller") or {}):
            link_problems.append("payload 缺少 follow_controller")
        if not (payload.get("arrival") or {}).get("tolerance_m"):
            link_problems.append("payload 缺少 arrival.tolerance_m")
    if link_problems:
        row["problems"] = problems + link_problems
        pytest.fail(f"链路级缺陷：{problems + link_problems}")

    # ⑤ fastForward 分段推进：到达判据触发 / 跟随状态机终止 / 场景时长上限三者任一后
    # 继续推进到**场景面板出判据报告**为止（导航状态机 30s 级先停、场景 60s 才收尾）。
    # 位姿读 state().qpos（sample() 无 x/y——与 test_navigation_route.py 同一来源）；
    # 跟随 = 位姿沿**规划路径**推进（距路径 ≤ lookahead，test_navigation_route 同口径）。
    goal = (nav.get("payload") or {}).get("waypoints", [{"x": 6.0, "y": 0.0}])[-1]
    final_wp = [float(goal.get("x", 6.0)), float(goal.get("y", 0.0))]
    plan = page.evaluate(
        """async (wps) => {
            const r = await fetch('/api/navigation/plan', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({map_id: 'warehouse', waypoints: wps}),
            });
            return r.json();
        }""",
        [[0.0, 0.0], final_wp],
    )
    path = (plan.get("plan") or {}).get("combined_path") or []
    lookahead = float(((nav.get("payload") or {}).get("follow_controller") or {}).get("lookahead_m") or 0.6)
    sim_time = 0.0
    arrived = False
    followed = False
    terminated = None
    pose = {}
    panel_text = ""
    while sim_time < TASK_SIM_SECONDS:
        page.evaluate(f"() => window.__sim2simDebug.fastForward({FF_CHUNK_S})")
        sim_time += FF_CHUNK_S
        qpos = page.evaluate("() => window.__sim2simDebug.state().qpos") or []
        if len(qpos) >= 2:
            pose = {"x": qpos[0], "y": qpos[1]}
            if path and min(math.hypot(pose["x"] - p[0], pose["y"] - p[1]) for p in path) <= max(lookahead, 0.5):
                followed = True
            if math.hypot(pose["x"] - final_wp[0], pose["y"] - final_wp[1]) <= 0.45:
                followed = True
        status = (page.evaluate("() => window.__sim2simDebug.navigation()") or {}).get("status") or {}
        # H12 终止分层：complete = 到达；timeout/stuck = 策略短板（如实记录，继续跑到场景收尾）
        if status.get("finished") and terminated is None:
            terminated = status.get("termination_reason")
            if terminated == "complete":
                arrived = True
                followed = True
        panel_text = page.eval_on_selector("#scenarioPanel", "el => el.textContent") \
            if page.query_selector("#scenarioPanel") else ""
        if panel_text and ("✓" in panel_text or "✗" in panel_text):
            break
    row["sim_time_s"] = sim_time
    row["arrived"] = arrived
    row["followed"] = followed
    row["termination_reason"] = terminated
    row["final_pose"] = {k: round(pose[k], 3) for k in ("x", "y") if k in pose}
    row["final_error_m"] = round(math.hypot(pose.get("x", 0) - final_wp[0], pose.get("y", 0) - final_wp[1]), 3)

    # ⑥ 场景面板必须出**判据报告**（链路级：没有报告 = 任务坞白做）。
    # 注意"· 通过"才算通过——"未通过"包含子串"通过"，子串判断会假绿。
    panel_text = page.eval_on_selector("#scenarioPanel", "el => el.textContent") if page.query_selector("#scenarioPanel") else ""
    row["summary_rendered"] = bool(panel_text) and ("✓" in panel_text or "✗" in panel_text)
    if not row["summary_rendered"]:
        link_problems.append(f"场景面板没有判据报告（内容：{panel_text[:120]!r}）")
    else:
        row["summary_passed"] = "· 通过" in panel_text

    # ⑦ 页面自身 JS 错误 = 链路缺陷
    row["page_errors"] = console_watch["page_errors"]
    row["console_errors"] = console_watch["console_errors"]
    row["resource_errors"] = console_watch["resource_errors"]
    if console_watch["page_errors"] or console_watch["console_errors"]:
        link_problems.append(
            f"页面自身 JS 错误：{console_watch['page_errors'][:2] + console_watch['console_errors'][:2]}"
        )

    screenshot_path = ARTIFACT_DIR / "task_dock_goal_nav.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=False)
        row["screenshot"] = str(screenshot_path)
    except Exception:
        pass

    row["problems"] = problems + link_problems
    # 分层：链路缺陷 = 失败；控制器短板（推进了但没到）= 如实记录
    if link_problems:
        pytest.fail(f"链路级缺陷：{link_problems}")
    if arrived:
        row["classification"] = "arrived"
    elif followed:
        row["classification"] = "h12_overshoot"
    else:
        row["classification"] = "h12_no_follow"
    row["ok"] = True
