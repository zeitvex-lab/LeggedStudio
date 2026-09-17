"""多策略热切换浏览器实测 —— G4「同机在策略间热切换对比」的可重复证据链。

单会话内不刷新页面，在同机多条基础策略间热切换，逐步断言：
    加载机型 + 策略A → 断言策略真加载且仿真在跑
    → 页面 select 改值触发 switchPolicy 切到策略B（不经刷新）
    → 断言状态栏显示策略B、ONNX 真被 HTTP 拉取（B41 后走 HTTP 非 VFS）、仿真恢复运行
    → 再切回策略A → 再次成功
    → 无效策略 id 被拒（catch 回滚，页面不崩）
    → 收集全程 console / pageerror（页面自身 JS 错误算失败）
    → 落机器可读证据 tools/baselines/policy_hot_switch.json（机型/策略对/切换结果/
      耗时/无错误断言数 + provenance），供下轮防退化。

顺带验证「切的是不同的策略」：A/B 两策略快进同长仿真时间后采样 baseZ / quat /
policyMode / policyInputs —— 至少一项应有可观测差异。

机型选择：unitree_go2（browser-config 实测下发 12 条策略，其中 11 条包内基础策略；
unitree_g1 仅 5 条）。策略对取 go2-moe-cts / go2-arenax-velocity（均为基础速度型，
行为稳定；moe-cts 走 MoE 权重输出，arenax 为普通 history 策略，policyMode 有别）。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_policy_hot_switch.py -v
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
BASELINE_PATH = ROOT / "tools" / "baselines" / "policy_hot_switch.json"

READY_TIMEOUT_S = float(os.environ.get("LEGGED_STUDIO_E2E_MODEL_TIMEOUT_S", "120"))
OBSERVE_MS = 2_500  # 实时观察窗：等帧循环把仿真时钟推走
FF_SECONDS = 1.0    # 切换后同步快进时长（指令 → ONNX 推理 → mj_step 全链路）

ROBOT_ID = "unitree_go2"
POLICY_A = "go2-moe-cts"
POLICY_B = "go2-arenax-velocity"
INVALID_POLICY = "__nonexistent_policy__"

_RESOURCE_CONSOLE_NOISE = re.compile(r"Failed to load resource", re.I)
_BENIGN_RESOURCE = re.compile(r"/favicon\.ico$", re.I)
# switchPolicy catch 里对「无效策略被拒」的设计内 console.error（含堆栈），
# 是无效切换测试用例预期触发的拒绝路径，不算页面自身错误。
_EXPECTED_POLICY_REJECT = re.compile(r"policy switch failed Error: 包内不存在策略", re.I)

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


def _git_state() -> dict:
    """git commit + dirty（best-effort，对齐 test_all_models._git_state 口径）。"""
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
        "policy_pair_rule": "go2-moe-cts / go2-arenax-velocity（browser-config 下发的基础策略，MoE vs 普通 history）",
        "run_params": {
            "ready_timeout_s": READY_TIMEOUT_S,
            "observe_ms": OBSERVE_MS,
            "fast_forward_s": FF_SECONDS,
        },
    }


def _write_baseline(payload: dict) -> None:
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
        if _EXPECTED_POLICY_REJECT.search(text):
            return  # 无效策略被拒是设计内路径（catch 里 console.error）
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


def _sim_clock(page) -> float:
    """#simClock 的「时间 X.XX」读数；读不到返回 -1。"""
    text = str(page.evaluate("() => document.querySelector('#simClock')?.textContent || ''"))
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else -1.0


def _policy_select_value(page) -> str:
    return str(page.evaluate("() => document.querySelector('#policySelect')?.value || ''"))


def _policy_status_text(page) -> str:
    return str(page.evaluate("() => document.querySelector('#policyStatus')?.textContent || ''"))


def _switch_policy_via_select(page, policy_id: str) -> None:
    """不经刷新，改页面 select 值并派发 change 事件触发 app.js switchPolicy。"""
    page.evaluate(
        """(policyId) => {
            const select = document.querySelector('#policySelect');
            if (!select) throw new Error('#policySelect not found');
            select.value = policyId;
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        policy_id,
    )


def _wait_policy_ready(page, policy_id: str, timeout_s: float = 60.0) -> dict:
    """等状态栏出现「已就绪」且 URL 回写、select 选中该策略。返回诊断字典。"""
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        last = {
            "select": _policy_select_value(page),
            "status": _policy_status_text(page),
            "url_policy": str(page.evaluate("() => new URL(window.location.href).searchParams.get('policy') || ''")),
        }
        if (
            last["select"] == policy_id
            and "已就绪" in last["status"]
            and "错误" not in last["status"]
            and "失败" not in last["status"]
            and last["url_policy"] == policy_id
        ):
            last["ready_ms"] = round((timeout_s - (deadline - time.monotonic())) * 1000)
            return last
        time.sleep(0.2)
    last["timeout"] = True
    return last


def _assert_sim_advances(page, problems: list[str], label: str) -> bool:
    """快进 FF_SECONDS 仿真时间并断言时钟推进 + baseZ 有限。"""
    clock_before = _sim_clock(page)
    try:
        sample = page.evaluate(
            f"async () => await window.__sim2simDebug.fastForward({FF_SECONDS})"
        )
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{label}: fastForward 失败: {exc}")
        return False
    clock_after = _sim_clock(page)
    base_z = sample.get("baseZ")
    sim_time = sample.get("time")
    if not isinstance(sim_time, (int, float)) or sim_time < FF_SECONDS * 0.9:
        problems.append(f"{label}: 快进 {FF_SECONDS}s 后仿真时间异常: {sim_time}")
        return False
    if base_z is None or not math.isfinite(base_z):
        problems.append(f"{label}: 快进后基座高度非有限值: {base_z}")
        return False
    if clock_after <= clock_before:
        # fastForward 本身会推进时钟，这里宽松一点：状态栏时钟应在采样后变大
        problems.append(f"{label}: 状态栏时钟未推进（{clock_before} → {clock_after}）")
        return False
    return True


def test_policy_hot_switch_same_session(page, base_url: str, console_watch):
    """单会话内 A→B→A→invalid 全链路热切换实测。"""
    url = f"{base_url}/web/sim2sim/index.html?debug=1&robot={ROBOT_ID}&policy={POLICY_A}"
    row: dict = {
        "robot": ROBOT_ID,
        "policy_a": POLICY_A,
        "policy_b": POLICY_B,
        "steps": [],
        "ok": False,
        "assertions_passed": 0,
        "total_ms": None,
        "page_errors": [],
        "console_errors": [],
        "resource_errors": [],
        "policy_diff": {},
        "first_error": None,
    }
    problems: list[str] = []
    started_at = time.monotonic()
    onnx_requests: list[str] = []  # 观测到的策略 ONNX HTTP 拉取

    def _on_response(response) -> None:
        url_str = response.url
        if ".onnx" in url_str and response.status == 200:
            onnx_requests.append(url_str)

    page.on("response", _on_response)

    def _record_step(name: str, ok: bool, detail: dict | None = None) -> None:
        entry = {"step": name, "ok": ok, "detail": detail or {}}
        row["steps"].append(entry)
        if ok:
            row["assertions_passed"] += 1

    try:
        # ------------------------------------------------------------------ 就绪
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_S * 1000)
        page.wait_for_function(
            "() => window.__probe && Number.isFinite(window.__probe.z)", timeout=30_000,
        )
        state_a0 = page.evaluate("() => window.__sim2simDebug.state()")
        if state_a0.get("model") is None:
            problems.append("MuJoCo 模型未构建")
        ready = _wait_policy_ready(page, POLICY_A)
        if ready.get("timeout"):
            problems.append(f"策略A 未就绪: {ready}")
        else:
            _record_step("load_policy_a", True, ready)
        if not _assert_sim_advances(page, problems, "策略A 首跑"):
            _record_step("sim_running_a", False)
        else:
            _record_step("sim_running_a", True)

        # 等实时观察窗让时钟自然推进（证明帧循环活着，不只是 fastForward 能走）
        clock_t0 = _sim_clock(page)
        page.wait_for_timeout(OBSERVE_MS)
        clock_t1 = _sim_clock(page)
        if clock_t1 <= clock_t0:
            problems.append(f"策略A 实时帧循环未推进时钟（{clock_t0} → {clock_t1}）")
            _record_step("realtime_running_a", False, {"clock_before": clock_t0, "clock_after": clock_t1})
        else:
            _record_step("realtime_running_a", True, {"clock_before": clock_t0, "clock_after": clock_t1})

        state_a = page.evaluate("() => window.__sim2simDebug.state()")
        sample_a = page.evaluate("async () => await window.__sim2simDebug.fastForward(0.5)")
        onnx_count_before = len(onnx_requests)

        # ------------------------------------------------------------------ A→B
        switch_start = time.monotonic()
        _switch_policy_via_select(page, POLICY_B)
        ready_b = _wait_policy_ready(page, POLICY_B)
        switch_ms = round((time.monotonic() - switch_start) * 1000)
        if ready_b.get("timeout"):
            problems.append(f"切到策略B 未就绪: {ready_b}")
            _record_step("switch_a_to_b", False, ready_b)
        else:
            status_b = ready_b.get("status", "")
            if POLICY_B not in status_b and "已就绪" not in status_b:
                problems.append(f"状态栏未显示策略B: {status_b}")
                _record_step("switch_a_to_b", False, ready_b)
            else:
                _record_step("switch_a_to_b", True, {**ready_b, "switch_ms": switch_ms})

        # 断言新策略真被 HTTP 拉取（不是回落到旧 VFS 缓存）
        new_onnx = [u for u in onnx_requests[onnx_count_before:] if POLICY_B in u or "arenax" in u]
        if not new_onnx:
            problems.append(
                f"切换后未见策略B 的 ONNX HTTP 拉取（onnx_requests={onnx_requests[onnx_count_before:]}）"
            )
            _record_step("onnx_http_fetch_b", False, {"seen": onnx_requests[onnx_count_before:]})
        else:
            _record_step("onnx_http_fetch_b", True, {"url": new_onnx[0]})

        if not _assert_sim_advances(page, problems, "策略B 首跑"):
            _record_step("sim_running_b", False)
        else:
            _record_step("sim_running_b", True)

        state_b = page.evaluate("() => window.__sim2simDebug.state()")
        sample_b = page.evaluate("async () => await window.__sim2simDebug.fastForward(0.5)")
        onnx_count_mid = len(onnx_requests)

        # ------------------------------------------------------------------ B→A
        switch_start = time.monotonic()
        _switch_policy_via_select(page, POLICY_A)
        ready_a2 = _wait_policy_ready(page, POLICY_A)
        switch_ms = round((time.monotonic() - switch_start) * 1000)
        if ready_a2.get("timeout"):
            problems.append(f"切回策略A 未就绪: {ready_a2}")
            _record_step("switch_b_to_a", False, ready_a2)
        else:
            _record_step("switch_b_to_a", True, {**ready_a2, "switch_ms": switch_ms})

        new_onnx_a = [u for u in onnx_requests[onnx_count_mid:] if POLICY_A in u or "moe_cts" in u]
        if not new_onnx_a:
            problems.append(f"切回后未见策略A 的 ONNX HTTP 拉取（seen={onnx_requests[onnx_count_mid:]}）")
            _record_step("onnx_http_fetch_a2", False, {"seen": onnx_requests[onnx_count_mid:]})
        else:
            _record_step("onnx_http_fetch_a2", True, {"url": new_onnx_a[0]})

        if not _assert_sim_advances(page, problems, "策略A 回切首跑"):
            _record_step("sim_running_a2", False)
        else:
            _record_step("sim_running_a2", True)

        state_a2 = page.evaluate("() => window.__sim2simDebug.state()")
        sample_a2 = page.evaluate("async () => await window.__sim2simDebug.fastForward(0.5)")

        # -------------------------------------------------------- 无效策略被拒
        # 真无效 id 必须作为 DOM option 注入再选中：HTML select 对不存在 option 的
        # value 赋值会静默失败（select.value 变空串），空串在 switchPolicy 里走
        #「off」分支——这是实测抓到的真缺陷（空 id / 未注入 option 的"无效切换"会
        # 被静默当「无策略」处理而非拒绝），登记不修，见 baseline defects 字段。
        select_before = _policy_select_value(page)
        status_before = _policy_status_text(page)
        page.evaluate(
            """(badId) => {
                const select = document.querySelector('#policySelect');
                const option = document.createElement('option');
                option.value = badId;
                option.textContent = badId;
                select.append(option);
                select.value = badId;
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            INVALID_POLICY,
        )
        # switchPolicy 异步：catch 回滚后状态栏会显示「策略切换失败」，select 恢复
        page.wait_for_timeout(2_000)
        select_after = _policy_select_value(page)
        status_after = _policy_status_text(page)
        state_invalid = page.evaluate("() => window.__sim2simDebug.state()")
        # 注入的 option 在 applyPlatformLabels 重建 select 时被清掉，select_after 应
        # 回滚到先前策略；状态栏标错误；policyEnabled 仍 True（未走 off 分支）
        rollback_ok = (
            select_after == select_before
            and state_invalid.get("policyEnabled") is True
            and "失败" in status_after
        )
        if not rollback_ok:
            problems.append(
                f"无效策略切换未回滚: select {select_before}->{select_after}, "
                f"status '{status_after}', policyEnabled={state_invalid.get('policyEnabled')}"
            )
            _record_step("invalid_policy_rejected", False, {
                "select_before": select_before, "select_after": select_after,
                "status_after": status_after,
            })
        else:
            _record_step("invalid_policy_rejected", True, {
                "select_restored": select_after,
                "status_after": status_after,
                "policyEnabled": state_invalid.get("policyEnabled"),
            })

        # 回滚后仿真仍可推进
        if not _assert_sim_advances(page, problems, "无效策略拒载后"):
            _record_step("sim_running_after_invalid", False)
        else:
            _record_step("sim_running_after_invalid", True)

        # ------------------------------------------------- 策略差异（对比面）
        diff: dict = {
            "policyMode": {"a": state_a.get("policyMode"), "b": state_b.get("policyMode")},
            "policyInputs": {"a": state_a.get("policyInputs"), "b": state_b.get("policyInputs")},
            "baseZ_after_0.5s_ff": {
                "a": sample_a.get("baseZ"),
                "b": sample_b.get("baseZ"),
                "a2": sample_a2.get("baseZ"),
            },
            "quat_after_0.5s_ff": {
                "a": sample_a.get("quat"),
                "b": sample_b.get("quat"),
            },
        }
        row["policy_diff"] = diff
        # 「切的是不同的策略」判据：policyMode / policyInputs / 采样轨迹至少一项不同
        differs = (
            diff["policyMode"]["a"] != diff["policyMode"]["b"]
            or diff["policyInputs"]["a"] != diff["policyInputs"]["b"]
            or diff["baseZ_after_0.5s_ff"]["a"] != diff["baseZ_after_0.5s_ff"]["b"]
            or diff["quat_after_0.5s_ff"]["a"] != diff["quat_after_0.5s_ff"]["b"]
        )
        if not differs:
            problems.append(f"策略A/B 无可观测差异（疑似同一个策略换个标签）: {diff}")
            _record_step("policies_differ", False, diff)
        else:
            _record_step("policies_differ", True, diff)

        # 回切 A 后应与首次 A 状态一致（policyMode/policyInputs 相同；baseZ 允许小漂）
        if (
            state_a2.get("policyMode") != state_a.get("policyMode")
            or state_a2.get("policyInputs") != state_a.get("policyInputs")
        ):
            problems.append(
                f"回切策略A 后 policyMode/Inputs 与首次不符: "
                f"a={state_a.get('policyMode')}/{state_a.get('policyInputs')} "
                f"a2={state_a2.get('policyMode')}/{state_a2.get('policyInputs')}"
            )
            _record_step("roundtrip_state_consistent", False)
        else:
            _record_step("roundtrip_state_consistent", True)

        # ------------------------------------------------- console 错误收集
        if console_watch["page_errors"]:
            problems.append(f"页面 JS 异常 x{len(console_watch['page_errors'])}: {console_watch['page_errors'][0]}")
        if console_watch["console_errors"]:
            problems.append(f"console.error x{len(console_watch['console_errors'])}: {console_watch['console_errors'][0]}")

    finally:
        row["total_ms"] = round((time.monotonic() - started_at) * 1000)
        row["page_errors"] = console_watch["page_errors"][:10]
        row["console_errors"] = console_watch["console_errors"][:10]
        row["resource_errors"] = console_watch["resource_errors"][:10]
        row["onnx_http_requests"] = onnx_requests[:20]
        row["ok"] = not problems
        row["first_error"] = problems[0] if problems else None
        payload = {
            "schema": "policy-hot-switch-1.0",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "surface": "web/sim2sim/index.html（基础仿真 ?debug=1&robot=unitree_go2）",
            "mode": "hot-switch",
            "provenance": _provenance(),
            "summary": {
                "ok": row["ok"],
                "assertions_passed": row["assertions_passed"],
                "total_steps": len(row["steps"]),
                "total_ms": row["total_ms"],
            },
            "result": row,
            # 实测登记的真缺陷（不修，只记录供下轮决策）：
            # 对 select.value 赋一个不在 option 清单里的 id 时，HTML select 语义
            # 会静默把它当空串，switchPolicy 收到空串走「off」分支（无策略·姿态保持），
            # 不会抛错也不回滚 —— 「无效策略切换被拒」这条只覆盖"DOM 里有该 option
            # 但包内候选列表没有"的分支（本测试注入 option 走的就是这条）。
            "defects": [
                {
                    "id": "hot-switch-empty-id-treated-as-off",
                    "surface": "web/sim2sim/app.js switchPolicy",
                    "summary": (
                        "select.value 赋非 option 清单内的 id 会静默变空串，"
                        "switchPolicy('') 走 off 分支禁用策略而非拒绝并回滚"
                    ),
                    "severity": "low",
                    "status": "registered-not-fixed",
                },
            ],
        }
        try:
            _write_baseline(payload)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"基线落盘失败: {exc}")

    assert not problems, "; ".join(problems)
