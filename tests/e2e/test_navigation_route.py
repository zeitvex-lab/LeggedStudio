"""H3 导航浏览器实测 —— 「不重训即可走完全程」的逐路线 E2E 证据链。

对 warehouse 地图的 H19 路线集（默认 full + 逐段 leg_i_j + 固定 seed 随机起终点，
``tools/route_regression.build_routes`` 同口径）逐条：
    打开基础仿真页 ?debug=1&robot=<best-navigator>&policy=<基础速度追踪>&nav=warehouse&nav_waypoints=...
    → 等会话就绪（#loading.is-hidden）
    → 断言导航已接线（__sim2simDebug.navigation() 非空、payload 里有 follow_controller）
    → fastForward 同步快进（步长 = follow_controller 0.05s dt × 1200 步 ≈ 60s 仿真时长）
    → 断言：① 规划路径非空且浏览器真的在跟随（当前位姿沿 path 推进）
            ② 到达判据触发（navigation().status.finished 为 true）
            ③ 帧推进过程无页面自身 JS 错误
            ④ 卡住/超时的如实记录（H12 已知短板：lookahead 0.45 在拐角切角、
               部分路线本体侵入——如实报，不修）

    **断言分层（H3 验收边界）**：
      * 链路级缺陷（页面未就绪 / 导航未接线 / payload 缺 follow_controller 或
        arrival / fastForward 异常 / 页面自身 JS 错误）⇒ **测试失败**，这是 H3 要修的真缺陷；
      * 控制器到达短板（跟随在推进但 90s 内到达判据不触发，或完全没跟随）⇒
        **如实记录为 reached=false + classification（h12_overshoot / h12_no_follow）**，
        测试**不因此失败**——控制器本身的改进是 H12 的任务，越界修产品代码会破坏
        证据链的诚实性。

机型选择：默认 unitree_go2 + go2-rlsar-robotlab（45D 速度追踪，task_type=velocity，
基础仿真页默认策略 H30 同款；Windows 实测 baseZ 稳定 0.33）。zex-w（B39 冒烟机型）
在 Windows 实测 policy 加载后站不稳（baseZ 从 0.13 跌到 0.02），故不作为默认导航机型
（登记不修，见本轮汇报）。可用 LEGGED_STUDIO_E2E_NAV_ROBOT / _POLICY 环境变量覆盖。
种子固定（route_regression.build_routes 默认 seed=20260913），逐条可复现。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_navigation_route.py -v
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
sys.path.insert(0, str(ROOT))

from tools.route_regression import build_routes  # noqa: E402

BASELINE_PATH = ROOT / "tools" / "baselines" / "navigation_browser_routes.json"
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "navigation-routes"

READY_TIMEOUT_S = float(os.environ.get("LEGGED_STUDIO_E2E_MODEL_TIMEOUT_S", "120"))
# 仿真时长上限：H19 基线 max_steps=1200 × dt=0.05s = 60s；放宽到 90s 给转弯/恢复留余量
NAV_SIM_SECONDS = float(os.environ.get("LEGGED_STUDIO_E2E_NAV_SIM_SECONDS", "90"))
# 每次 fastForward 调用的秒数（分段推进，避免单次 evaluate 超时）
FF_CHUNK_S = float(os.environ.get("LEGGED_STUDIO_E2E_FF_CHUNK_S", "10"))

#: 机型与策略（同 test_all_models.py 的口径：每包第一条基础策略）。
#: zex-w（B39 冒烟机型）在 Windows 实测 policy 加载后站不稳（baseZ 从 0.13 跌到 0.02，
#: 机器人贴地滑行），故默认改用 unitree_go2 + go2-rlsar-robotlab（45D 速度追踪，
#: 基础仿真页默认策略 H30 同款；Windows 实测 baseZ 稳定在 0.33）。
#: 可用环境变量 LEGGED_STUDIO_E2E_NAV_ROBOT / LEGGED_STUDIO_E2E_NAV_POLICY 覆盖。
ROBOT_ID = os.environ.get("LEGGED_STUDIO_E2E_NAV_ROBOT", "unitree_go2")
POLICY_ID = os.environ.get("LEGGED_STUDIO_E2E_NAV_POLICY", "go2-rlsar-robotlab")

# 资源加载类 console error（"Failed to load resource: ..."）由 response/requestfailed
# 监听按 URL+状态码归类为 resource_errors（诚实记录但不拦）——页面自身 JS 错误才算失败。
_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

pytestmark = [pytest.mark.e2e]


def _routes() -> list[dict]:
    """H19 路线集（warehouse，固定 seed）。"""
    return build_routes("warehouse")


ROUTES = _routes()
assert len(ROUTES) == 7, f"warehouse H19 路线集应为 7 条，实测 {len(ROUTES)}"


def _git_state() -> dict:
    """git commit + dirty（best-effort，对齐 test_all_models.py 的口径）。"""
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


def _provenance() -> dict:
    version_file = ROOT / "VERSION"
    return {
        "product_version": version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None,
        "git": _git_state(),
        "platform": py_platform.platform(),
        "python": sys.version.split()[0],
        "browser": "playwright chromium (headless)",
        "robot": ROBOT_ID,
        "policy": POLICY_ID,
        "route_rule": "tools/route_regression.build_routes(warehouse)（H19 路线集，seed=20260913）",
        "run_params": {
            "ready_timeout_s": READY_TIMEOUT_S,
            "nav_sim_seconds": NAV_SIM_SECONDS,
            "ff_chunk_s": FF_CHUNK_S,
        },
    }


@pytest.fixture(scope="session")
def nav_results(request):
    """会话级收集器：收尾时写 tools/baselines/navigation_browser_routes.json。"""
    rows: list[dict] = []
    yield rows
    if not rows:
        return
    # 逐路线 reason（H12 短板标注，便于回归对比与后续 H12 改进追踪）
    for r in rows:
        cls = r.get("classification")
        if cls == "arrived":
            r["reason"] = None
        elif cls == "h12_overshoot":
            r["reason"] = (
                "follow_controller limitation: overshoot/oscillation around waypoint "
                "(tolerance 0.2m, stable_ticks=2, vx_max=1.2 m/s)"
            )
        elif cls == "h12_no_follow":
            r["reason"] = "follow_controller limitation: body intrusion / stuck (H12 registered)"
        else:
            r["reason"] = None
    arrived_n = sum(1 for r in rows if r["classification"] == "arrived")
    overshoot_n = sum(1 for r in rows if r["classification"] == "h12_overshoot")
    no_follow_n = sum(1 for r in rows if r["classification"] == "h12_no_follow")
    link_defect_n = sum(1 for r in rows if not r.get("link_ok", False))
    payload = {
        "schema": "navigation-browser-routes-1.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "surface": "web/sim2sim/index.html（基础仿真，?debug=1&nav=warehouse&nav_waypoints=...）",
        "mode": "e2e",
        "provenance": _provenance(),
        "summary": {
            "total": len(rows),
            "arrived": arrived_n,
            "failed": len(rows) - arrived_n,
            "classification": {
                "arrived": arrived_n,
                "h12_overshoot": overshoot_n,
                "h12_no_follow": no_follow_n,
                "link_defect": link_defect_n,
            },
            "note": (
                "H3 验收口径：链路级缺陷（导航未接线/payload 缺 follow_controller 或 arrival/"
                "fastForward 异常/页面自身 JS 错误）为 0 ⇒ 浏览器实测走完全程的链路成立。"
                "2026-09-17 H12 浏览器侧收口：跟随器接入卡死检测/恢复动作/终止原因分层"
                "（backend/follow_controller.py 同参数同语义），到达判定改按 "
                "termination_reason==='complete'（此前 finished 混入了 timeout 等提前终止）。"
                "测量口径修正：e2e 先等策略会话就绪（sample().policyLoaded）再快进，"
                "且浏览器侧状态机时钟在策略加载完成前不计时（否则 holdStance 站桩被"
                "误判成卡死——首轮实测 7/7 误判 stuck 即此竞态）。"
                "h12_overshoot=跟随推进但 90s 内未到（过冲/振荡短板）；h12_no_follow=状态机判卡死"
                "（stuck，含恢复轮数）或跟随未推进；如实记录为防退化基线。"
            ),
        },
        "classification_legend": {
            "arrived": "到达判据触发（finished=True，位姿误差 ≤ 容差 0.2m）",
            "h12_overshoot": "跟随在推进（followed=True）但 90s 内到达判据不触发 —— H12 follow_controller 过冲/振荡短板",
            "h12_no_follow": "跟随完全没推进（followed=False）—— H12 本体侵入/卡死登记项",
            "link_defect": "链路级缺陷（导航未接线/payload 缺 follow_controller 或 arrival/fastForward 异常/页面自身 JS 错误）",
        },
        "results": rows,
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def console_watch(page):
    """JS 错误三分类收集：页面异常 / 页面自身 console.error / 资源级错误。"""
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
        lambda req: watched["resource_errors"].append(
            f"FAILED {req.url} {req.failure}"
        ) if not _BENIGN_RESOURCE.search(req.url) else None,
    )
    return watched


def _pose_along_path(pose: dict, path: list[list[float]], lookahead_m: float) -> bool:
    """当前位姿是否沿 path 推进：距路径最近点距离 ≤ lookahead（容忍切角）。"""
    if not path:
        return False
    px, py = pose.get("x", 0), pose.get("y", 0)
    min_dist = min(math.hypot(px - p[0], py - p[1]) for p in path)
    return min_dist <= max(lookahead_m, 0.5)


@pytest.mark.parametrize(
    "route",
    [pytest.param(r, id=r["name"]) for r in ROUTES],
)
def test_navigation_route(route: dict, page, base_url: str, console_watch, nav_results):
    """单条路线浏览器实测：导航接线 → 跟随推进 → 到达判据 → 无 JS 错误。"""
    waypoints = route["waypoints"]
    wp_str = ";".join(f"{p[0]},{p[1]}" for p in waypoints)
    url = (
        f"{base_url}/web/sim2sim/index.html?debug=1"
        f"&robot={ROBOT_ID}&policy={POLICY_ID}"
        f"&nav=warehouse&nav_waypoints={wp_str}"
    )
    row: dict = {
        "route": route["name"],
        "kind": route["kind"],
        "waypoints": waypoints,
        "robot": ROBOT_ID,
        "policy_id": POLICY_ID,
        "started": False,
        "nav_wired": False,
        "policy_wait_s": None,
        "path_nonempty": False,
        "followed": False,
        "arrived": False,
        "termination_reason": None,
        "recoveries_used": None,
        "sim_time_s": None,
        "final_pose": None,
        "final_error_m": None,
        "path_len_m": None,
        "lookahead_m": None,
        "ok": False,
        "first_error": None,
        "page_errors": [],
        "console_errors": [],
        "resource_errors": [],
        "screenshot": None,
    }
    # H12 已知短板如实记录（任务原文：lookahead 0.45 在拐角切角、部分路线本体侵入——如实报，不修）。
    # 判定：跟随在推进（followed=True）但 90s 内到达判据不触发 ⇒ 过冲/振荡是 follow_controller
    # 同源短板；跟随完全没推进（followed=False）⇒ 可能是 H12 本体侵入/卡死，也可能是链路缺陷。
    # 两种都不改产品代码，但要在基线里显式标注 classification，便于回归对比与后续 H12 改进追踪。
    problems: list[str] = []
    link_problems: list[str] = []
    started_at = time.monotonic()
    try:
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_S * 1000)
            row["started"] = True
        except Exception as exc:
            link_problems.append(f"页面未在 {READY_TIMEOUT_S:.0f}s 内就绪: {exc}")
        else:
            # 策略会话就绪才允许开始仿真：#loading 只代表 MuJoCo 场景就绪，
            # ONNX 会话（sim.policy）晚于它——过早 fastForward 会测到 holdStance
            # 站桩（指令正确但执行层没接上），把"没开始"误记成控制器短板。
            policy_t0 = time.monotonic()
            try:
                page.wait_for_function(
                    "() => window.__sim2simDebug?.sample?.()?.policyLoaded === true",
                    timeout=READY_TIMEOUT_S * 1000,
                )
                row["policy_wait_s"] = round(time.monotonic() - policy_t0, 1)
            except Exception as exc:
                link_problems.append(f"策略会话未在 {READY_TIMEOUT_S:.0f}s 内加载（policyLoaded=false）: {exc}")
            # 导航已接线（initNavigationFromUrl 被调，payload 装配成功）
            try:
                nav = page.evaluate("() => window.__sim2simDebug.navigation()")
            except Exception as exc:
                link_problems.append(f"navigation() getter 调用失败: {exc}")
                nav = None
            if nav is None:
                link_problems.append("导航未接线（__sim2simDebug.navigation() 返回 null）")
            else:
                row["nav_wired"] = True
                payload = nav.get("payload") or {}
                follow = payload.get("follow_controller") or {}
                arrival = payload.get("arrival") or {}
                row["lookahead_m"] = follow.get("lookahead_m")
                if not follow:
                    link_problems.append("payload 缺少 follow_controller")
                if not arrival.get("tolerance_m"):
                    link_problems.append("payload 缺少 arrival.tolerance_m")

                # 规划路径非空（服务端 plan.combined_path 通过 payload 下发）
                # 注意：navigation() 返回的 payload 不包含 plan.combined_path（太长），
                # 这里直接调服务端 plan 端点验证（与浏览器同源）。
                plan_resp = page.evaluate(
                    """async (wps) => {
                        const r = await fetch('/api/navigation/plan', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({map_id: 'warehouse', waypoints: wps}),
                        });
                        return r.json();
                    }""",
                    waypoints,
                )
                path = (plan_resp.get("plan") or {}).get("combined_path") or []
                row["path_len_m"] = (plan_resp.get("plan") or {}).get("total_cost_m")
                if len(path) < 2:
                    link_problems.append(f"规划路径为空或太短（len={len(path)}）")
                else:
                    row["path_nonempty"] = True

                # fastForward 推进仿真，分段轮询到达状态
                lookahead = float(follow.get("lookahead_m") or 0.45)
                sim_time = 0.0
                arrived = False
                followed = False
                last_pose = None
                ff_chunk = FF_CHUNK_S
                max_sim_time = NAV_SIM_SECONDS
                while sim_time < max_sim_time and not arrived:
                    try:
                        sample = page.evaluate(
                            f"async () => await window.__sim2simDebug.fastForward({ff_chunk})"
                        )
                    except Exception as exc:
                        link_problems.append(f"fastForward({ff_chunk}) 失败 @sim_time={sim_time:.1f}s: {exc}")
                        break
                    sim_time += ff_chunk
                    nav_now = page.evaluate("() => window.__sim2simDebug.navigation()")
                    status = (nav_now or {}).get("status") or {}
                    # H12 终止原因分层（LightNav 语义）：finished 只说明状态机停了，
                    # **到达 = termination_reason === "complete"**——timeout/stuck 是
                    # 策略结论（如实记为未到达），truncated 是预算拉停（非策略结论）。
                    if status.get("finished"):
                        termination = status.get("termination_reason")
                        row["termination_reason"] = termination
                        row["recoveries_used"] = status.get("recoveries_used")
                        if termination == "complete":
                            arrived = True
                        else:
                            # 状态机已终止且原因不是 complete：早停（stuck/timeout/truncated）
                            break
                    # 位姿沿 path 推进检查
                    qpos = page.evaluate("() => window.__sim2simDebug.state().qpos")
                    if qpos and len(qpos) >= 2:
                        last_pose = {"x": qpos[0], "y": qpos[1]}
                        if _pose_along_path(last_pose, path, lookahead):
                            followed = True

                row["arrived"] = arrived
                row["followed"] = followed
                row["sim_time_s"] = round(sim_time, 1)
                if last_pose:
                    row["final_pose"] = [round(last_pose["x"], 3), round(last_pose["y"], 3)]
                    # 最终误差 = 到最后一个航点的距离
                    tx, ty = waypoints[-1][0], waypoints[-1][1]
                    row["final_error_m"] = round(
                        math.hypot(last_pose["x"] - tx, last_pose["y"] - ty), 3
                    )

                if not followed:
                    problems.append(
                        f"位姿未沿 path 推进（仿真 {sim_time:.1f}s 后仍偏离路径）"
                    )
                if not arrived:
                    nav_final = page.evaluate("() => window.__sim2simDebug.navigation()")
                    status = ((nav_final or {}).get("status") or {})
                    problems.append(
                        f"到达判据未触发（仿真 {sim_time:.1f}s，"
                        f"finished={status.get('finished')}, "
                        f"termination_reason={status.get('termination_reason')}, "
                        f"recoveries_used={status.get('recoveries_used')}, "
                        f"reached={status.get('reached')}/{status.get('waypoint_count')}, "
                        f"route_completion={status.get('route_completion')}）"
                    )

            # 页面自身 JS 错误（资源级错误单独归类，不拦）
            if console_watch["page_errors"]:
                link_problems.append(
                    f"页面 JS 异常 x{len(console_watch['page_errors'])}: {console_watch['page_errors'][0]}"
                )
            if console_watch["console_errors"]:
                link_problems.append(
                    f"console.error x{len(console_watch['console_errors'])}: {console_watch['console_errors'][0]}"
                )
    finally:
        # H12 终止原因补录：90s 未终止的行回查一次最终状态（timeout/stuck/truncated 都要留痕）
        if not row["arrived"] and row["nav_wired"] and row.get("termination_reason") is None:
            try:
                nav_final = page.evaluate("() => window.__sim2simDebug.navigation()")
                status_final = ((nav_final or {}).get("status") or {})
                row["termination_reason"] = status_final.get("termination_reason")
                row["recoveries_used"] = status_final.get("recoveries_used")
            except Exception:
                pass
        row["total_ms"] = round((time.monotonic() - started_at) * 1000)
        row["page_errors"] = console_watch["page_errors"][:10]
        row["console_errors"] = console_watch["console_errors"][:10]
        row["resource_errors"] = console_watch["resource_errors"][:10]
        # H12 短板分类：跟随在推进但没到 ⇒ 控制器过冲/振荡；完全没跟随 ⇒ 本体侵入/卡死（同属 H12 登记项）。
        # 状态机终止原因参与分类：stuck ⇒ h12_no_follow（本体卡死登记项）；
        # timeout/未终止 + followed ⇒ h12_overshoot（过冲振荡从未稳定进容差）。
        if row["arrived"]:
            row["classification"] = "arrived"
        elif row["termination_reason"] == "stuck":
            row["classification"] = "h12_no_follow"
        elif row["followed"]:
            row["classification"] = "h12_overshoot"
        else:
            row["classification"] = "h12_no_follow"
        # 到达短板不改产品代码，如实记录但不作为断言失败（first_error 留给链路缺陷）
        row["first_error"] = link_problems[0] if link_problems else None
        row["link_ok"] = not link_problems
        row["ok"] = not (link_problems + problems)
        try:
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            shot = ARTIFACT_DIR / f"{route['name']}.png"
            page.screenshot(path=str(shot))
            row["screenshot"] = shot.relative_to(ROOT).as_posix()
        except Exception:
            pass
        nav_results.append(row)

    # H3 验收口径：链路级缺陷才判失败；控制器到达短板（H12）如实记录但不修（任务边界）
    assert not link_problems, (
        f"{route['name']} 链路缺陷: " + "; ".join(link_problems)
    )
