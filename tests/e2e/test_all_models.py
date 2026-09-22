"""逐机型浏览器实测 sweep —— G1「14 机型即点即玩」的逐机型证据链。

对每个内置机器人包（assets/robots/<id>，与 /api/robots/presets 一一对应）：
    打开基础仿真页 ?debug=1&robot=<id>&policy=<首条基础策略>
    → 等会话就绪（#loading 遮罩隐藏）
    → 断言「仿真真的在跑」：策略选中无回落、状态栏非错误、__probe.playing、
      仿真时钟实时推进、fastForward(0.5s) 全链路（指令→ONNX 推理→mj_step）可推进
    → 收集 JS console error（页面自身错误算失败；资源 404 单独归类不拦）
    → 截图落证 workspace/e2e-screenshots/all-models/<robot>.png（gitignore 内）

两档（tests/e2e/conftest.py 里 pytest_collection_modifyitems 把关）：
    默认（CI）      只跑 smoke 机型（首个「声明策略能被 browser-config 真实下发」的机型，
                    当前为 deeprobotics_m20；browser_default 的 unitree_go2 因 G1 缺陷
                    —— 声明策略被 browser-config 丢弃 —— 只进 sweep 档，见下）
    --sweep / 环境变量 LEGGED_STUDIO_E2E_SWEEP=1   14 机型全量（手动/夜跑工具档）
    sweep 模式结束时把实测矩阵写进 tools/baselines/browser_model_sweep.json
    （provenance 对齐 sim2sim_headless 基线：生成时间 / git commit+dirty / 平台 / 运行参数）。
    smoke 模式不写基线，避免 1 条冒烟覆盖 14 条全量证据。

策略口径：每包**第一条基础策略**（simulation/config.json 里 sim_surface != "advanced"
的第一条），与 app.js 基础仿真的下拉过滤同口径。注意浏览器实际下发的策略清单来自
`/api/simulation/browser-config/<robot>`，其包根由 workspace/package_index.json 决定
（部分机型指向 workspace/packages/<id> 暂存目录而非 assets/robots/<id>）：解析不出
包内 blob 的声明策略会被端点**静默丢弃**，页面随即静默回落（demo 策略或"无策略"）。
本测试请求的是 assets 包里声明的策略——若 browser-config 没把它下发出来，记为失败
（这正是 G1 要抓的「声明了却起不来」类问题，不为绿而放宽）；结果行里的
policy_offered 字段区分「下发缺失」与「下发正确但页面没选中」。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_all_models.py -v            # 冒烟 1 机型
    uv run --no-sync python -m pytest tests/e2e/test_all_models.py -v --sweep    # 全量 14 机型
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
PACKS_DIR = ROOT / "assets" / "robots"
BASELINE_PATH = ROOT / "tools" / "baselines" / "browser_model_sweep.json"
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "all-models"

READY_TIMEOUT_S = float(os.environ.get("LEGGED_STUDIO_E2E_MODEL_TIMEOUT_S", "120"))
OBSERVE_MS = 2_500  # 实时观察窗：等帧循环把仿真时钟推走

# 资源加载类 console error（"Failed to load resource: ..."）由 response/requestfailed
# 监听按 URL+状态码归类为 resource_errors（诚实记录但不拦）——页面自身 JS 错误才算失败。
_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
# favicon 404 与被测会话无关（页面本身没引用它），单独豁免避免每机型一行噪音。
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)

pytestmark = [pytest.mark.e2e]


def _first_basic_policy(config_path: Path) -> str | None:
    """每包第一条基础策略 id（sim_surface != "advanced"），app.js 基础仿真同口径。"""
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    for item in data.get("policies") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("sim_surface") or "basic") == "advanced":
            continue
        policy_id = item.get("id") or item.get("path") or item.get("url")
        if policy_id:
            return str(policy_id)
    return None


def _model_matrix() -> list[tuple[str, str]]:
    """[(robot_id, first_basic_policy_id)]，按包目录名排序保证可重复。"""
    rows: list[tuple[str, str]] = []
    for cfg in sorted(PACKS_DIR.glob("*/simulation/config.json")):
        robot_id = cfg.parents[1].name
        policy_id = _first_basic_policy(cfg)
        if policy_id:
            rows.append((robot_id, policy_id))
    return rows


def _smoke_robot() -> str:
    """CI 冒烟机型：首个「assets 声明的首条基础策略能被 browser 包根解析出包内 blob」的机型。

    不能直接用 browser_default 那台（unitree_go2）：它的 browser 包根被
    workspace/package_index.json 指到 workspace/packages/ 暂存目录，声明策略在
    端点侧解析不出包内 blob 而被静默丢弃（G1 实测缺陷，见 sweep 基线）——拿它当
    冒烟会让 CI 默认档永远红。这里的判定与 browser-config 端点同口径
    （policy_relative_path 解析得出包内相对路径才会进下发清单），纯文件解析、
    不起 HTTP，模块导入期执行也安全。
    """
    try:
        from backend.policy_artifacts import policy_relative_path
        from backend.simulation_browser import browser_package

        for robot_id, policy_id in sorted(MATRIX):
            try:
                root, _preset = browser_package(robot_id)
            except Exception:  # noqa: BLE001 —— 单台解析失败不影响其余
                continue
            config = json.loads((root / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
            for item in config.get("policies") or []:
                if isinstance(item, dict) and str(item.get("id") or "") == policy_id:
                    if policy_relative_path(item, robot_dir=root):
                        return robot_id
                    break
    except Exception:  # noqa: BLE001 —— 探测失败退回静态名单，不阻塞收集
        pass
    return next((rid for rid, _pid in sorted(MATRIX) if rid != SMOKE_FALLBACK_EXCLUDED), "unitree_go2")


#: 已知声明策略会被 browser-config 丢弃的机型不作冒烟首选（G1 sweep 实测缺陷）。
SMOKE_FALLBACK_EXCLUDED = "unitree_go2"


MATRIX = _model_matrix()
assert MATRIX, "assets/robots/ 下没有任何可测的机器人包（每包需有 simulation/config.json 且声明基础策略）"
SMOKE_ROBOT = _smoke_robot()


def _param_marks(robot_id: str) -> list:
    marks = [pytest.mark.sweep]
    if robot_id == SMOKE_ROBOT:
        marks.append(pytest.mark.smoke)
    return marks


def _sweep_enabled(config) -> bool:
    return bool(config.getoption("--sweep")) or os.environ.get("LEGGED_STUDIO_E2E_SWEEP") == "1"


# ---------------------------------------------------------------------------
# 结果收集与基线落盘
# ---------------------------------------------------------------------------

def _git_state() -> dict:
    """git commit + dirty（best-effort，对齐 backend.training.runs._git_state 的口径）。"""
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
        "policy_rule": "每包第一条基础策略（simulation/config.json: sim_surface != advanced 的第一条）",
        "run_params": {"ready_timeout_s": READY_TIMEOUT_S, "observe_ms": OBSERVE_MS},
    }


@pytest.fixture(scope="session")
def sweep_results(request):
    """会话级收集器：sweep 模式收尾时写 tools/baselines/browser_model_sweep.json。

    teardown 在用例失败后也执行 —— 部分失败照样落盘（诚实记录跑到哪）。
    """
    rows: list[dict] = []
    yield rows
    if not _sweep_enabled(request.config) or not rows:
        return
    payload = {
        "schema": "browser-model-sweep-1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "surface": "web/sim2sim/index.html（基础仿真，?debug=1&robot=<id>&policy=<id>）",
        "mode": "sweep",
        "provenance": _provenance(),
        "summary": {
            "total": len(rows),
            "started": sum(1 for r in rows if r["started"]),
            "ok": sum(1 for r in rows if r["ok"]),
            "failed": sum(1 for r in rows if not r["ok"]),
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
            return  # 资源级错误由 response/requestfailed 按 URL 归类
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


def _failure_surface(page) -> str:
    """失败时尽力读页面自己的报错表面（loading 文案 + 两条状态栏），读不到就空串。"""
    try:
        return str(page.evaluate(
            """() => [
                document.querySelector('#loadingText')?.textContent || '',
                document.querySelector('#engineStatus')?.textContent || '',
                document.querySelector('#policyStatus')?.textContent || '',
            ].filter(Boolean).join(' | ')"""
        ))
    except Exception:  # noqa: BLE001 —— 页面可能已崩到 evaluate 都失败
        return ""


def _sim_clock(page) -> float:
    """#simClock 的「时间 X.XX」读数（帧循环每帧刷新）；读不到返回 -1。"""
    text = str(page.evaluate("() => document.querySelector('#simClock')?.textContent || ''"))
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else -1.0


@pytest.mark.parametrize(
    "robot_id,policy_id",
    [pytest.param(robot_id, policy_id, id=f"{robot_id}[{policy_id}]", marks=_param_marks(robot_id))
     for robot_id, policy_id in MATRIX],
)
def test_browser_session_runs(robot_id: str, policy_id: str, page, base_url: str, console_watch, sweep_results):
    """单机型浏览器实测：会话就绪 + 策略真加载 + 仿真真在跑 + 无页面自身 JS 错误。"""
    url = f"{base_url}/web/sim2sim/index.html?debug=1&robot={robot_id}&policy={policy_id}"
    row: dict = {
        "robot": robot_id,
        "policy_id": policy_id,
        "started": False,       # loading 遮罩隐藏（会话建起来了）
        "policy_loaded": False, # 选中请求的策略且状态栏非错误
        "policy_offered": False, # browser-config 下发的下拉清单里含请求策略
        "sim_running": False,   # 帧循环 + 物理时钟实时推进
        "ok": False,
        "base_z": None,
        "fps": None,
        "ready_ms": None,
        "total_ms": None,
        "first_error": None,
        "page_errors": [],
        "console_errors": [],
        "resource_errors": [],
        "screenshot": None,
    }
    problems: list[str] = []
    started_at = time.monotonic()
    try:
        page.goto(url, wait_until="domcontentloaded")
        try:
            # state="attached"：is-hidden 本身把元素置为不可见，不能等 visible（见 test_sim2sim.py 注释）。
            page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_S * 1000)
            row["started"] = True
            row["ready_ms"] = round((time.monotonic() - started_at) * 1000)
        except Exception as exc:  # noqa: BLE001 —— 超时/页面崩溃都归为未就绪
            surface = _failure_surface(page)
            problems.append(
                f"页面未在 {READY_TIMEOUT_S:.0f}s 内就绪：{surface or exc}"
            )
        else:
            state = page.evaluate("() => window.__sim2simDebug.state()")
            status = state.get("status") or {}
            engine_status = str(status.get("engine") or "")
            policy_status = str(status.get("policy") or "")

            if state.get("model") is None:
                problems.append("MuJoCo 模型未构建（__sim2simDebug.state().model 为 null）")
            if any(k in engine_status for k in ("错误", "异常")):
                problems.append(f"引擎状态异常: {engine_status}")

            # 策略真的加载了所请求那条（loadPlatformConfig 对未匹配 id 会静默回落默认策略）
            selected = str(page.evaluate("() => document.querySelector('#policySelect')?.value || ''"))
            offered = page.evaluate(
                """() => Array.from(document.querySelector('#policySelect')?.options || [])
                        .map((o) => o.value).filter(Boolean)"""
            )
            row["policy_offered"] = policy_id in offered
            if selected != policy_id:
                if policy_id in offered:
                    problems.append(f"策略未选中请求项：请求 {policy_id}，页面实际 {selected or '无'}")
                else:
                    problems.append(
                        f"策略未被 browser-config 下发：请求 {policy_id}，下拉仅有 {offered} "
                        f"（包根分流/索引解析问题，声明被静默丢弃）"
                    )
            if any(k in policy_status for k in ("不可用", "错误", "失败")):
                problems.append(f"策略状态异常: {policy_status}")
            row["policy_loaded"] = selected == policy_id and not any(
                k in policy_status for k in ("不可用", "错误", "失败")
            )

            # 帧循环：先等首个渲染帧把诊断探针写出来（#loading 隐藏与第一帧之间存在
            # 空窗——首帧要编译着色器 + 跑第一次 ONNX 推理，实测可达数秒，直接读会
            # 撞到 undefined），再断言探针在播。
            try:
                page.wait_for_function(
                    "() => window.__probe && Number.isFinite(window.__probe.z)", timeout=30_000,
                )
            except Exception as exc:  # noqa: BLE001
                problems.append(f"渲染帧循环未产出诊断探针（__probe 30s 未出现）: {exc}")
                probe = None
            else:
                probe = page.evaluate("() => window.__probe || null")
            if probe is not None and probe.get("playing") is not True:
                problems.append(f"帧循环未在运行（__probe={probe}）")

            clock_before = _sim_clock(page)
            page.wait_for_timeout(OBSERVE_MS)
            clock_after = _sim_clock(page)
            perf_text = str(page.evaluate("() => document.querySelector('#perfStats')?.textContent || ''"))
            perf_match = re.search(r"(\d+) 帧/秒 · ([\d.]+)x", perf_text)
            if perf_match:
                row["fps"] = int(perf_match.group(1))
            if clock_after <= clock_before:
                problems.append(f"仿真时钟未推进（{clock_before} → {clock_after}，perfStats={perf_text}）")
            else:
                row["sim_running"] = True

            # 全链路（指令 → ONNX 推理 → mj_step）同步快进 0.5s 仿真时间
            try:
                sample = page.evaluate("async () => await window.__sim2simDebug.fastForward(0.5)")
                row["base_z"] = sample.get("baseZ")
                sim_time = sample.get("time")
                if not isinstance(sim_time, (int, float)) or sim_time < 0.5:
                    problems.append(f"快进 0.5s 后仿真时间异常: {sim_time}")
                base_z = sample.get("baseZ")
                if base_z is None or not math.isfinite(base_z):
                    problems.append(f"快进后基座高度非有限值: {base_z}")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"fastForward(0.5) 失败: {exc}")

            # 观察+快进期间累积的页面自身错误也算失败（资源级错误单独归类，不拦）
            if console_watch["page_errors"]:
                problems.append(f"页面 JS 异常 x{len(console_watch['page_errors'])}: {console_watch['page_errors'][0]}")
            if console_watch["console_errors"]:
                problems.append(f"console.error x{len(console_watch['console_errors'])}: {console_watch['console_errors'][0]}")
    finally:
        row["total_ms"] = round((time.monotonic() - started_at) * 1000)
        row["page_errors"] = console_watch["page_errors"][:10]
        row["console_errors"] = console_watch["console_errors"][:10]
        row["resource_errors"] = console_watch["resource_errors"][:10]
        row["first_error"] = problems[0] if problems else None
        row["ok"] = not problems
        try:
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            shot = ARTIFACT_DIR / f"{robot_id}.png"
            page.screenshot(path=str(shot))
            row["screenshot"] = shot.relative_to(ROOT).as_posix()
        except Exception:  # noqa: BLE001 —— 截图失败不掩盖主判定
            pass
        sweep_results.append(row)

    assert not problems, f"{robot_id}[{policy_id}]: " + "; ".join(problems)
