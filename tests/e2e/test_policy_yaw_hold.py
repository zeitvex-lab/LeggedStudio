"""高级仿真页 · **边走边转穿过 180° 的存活判据**（?debug=1 的会话类断言）。

与既有 e2e 的分工（不重复）：
    test_sim2sim.py           基础页：加载/确定性回放/物理存活
    test_all_models.py        14 机型 sweep
    test_policy_hot_switch.py 策略热切换
    test_navigation_route.py  导航 7 路线
    test_ui_audit*.py         页面结构与 UI 细节
    → 本文件补**单一策略的姿态遍历行为**：让机器人带指令边走边转，穿过 ±180°，
      断言"不掉下去、角速度读数物理合理"。

**为什么专门守这一条**（2026-09-22 用户报障的回归锁）：`captureImuSample` 曾把自由关节
`qvel[3:6]`（**本就是机体系角速度**）再乘一次 `Rᵀ` ⇒ 双重旋转。yaw≈0 处 R≈I 完全看不出来
（策略照走），yaw→180° 时水平两轴翻号 ⇒ 角速度反馈成正反馈 ⇒ 机器人乱动失衡——用户原话
"转到 180° 左右会完全失去平衡，直接开始乱动，稳定复现"。修复见 `utils.js::imuSampleFromQpos`；
本用例把"穿过 180° 仍站立"钉成断言。

**判据（三条，全部取自页面自身的调试句柄）**：
  ① 姿态遍历到位：`|yaw| ≥ 150°`（没转过去就谈不上"穿越大角度"）；
  ② 全程站立：`baseZ ≥ 0.20`（go2 站高 ≈0.30；掉下去会 <0.2）；
  ③ 读数合理：`|ω| ≤ 8 rad/s`（机身真实角速度不可能达到的量级；缺陷态实测冲到 −13.6）。

证据落 `workspace/e2e-screenshots/yaw/`（gitignore 内）：截图 + 逐拍 JSON。

运行：
    uv run --no-sync python -m pytest tests/e2e/test_policy_yaw_hold.py -v
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "workspace" / "e2e-screenshots" / "yaw"

READY_TIMEOUT_MS = 180_000
POLICY_URL = (
    "/web/sim2sim/index.html?debug=1&embedded=1&surface=advanced"
    "&robot=unitree_go2&policy=go2-rlsar-robotlab&terrain=flat"
)
#: 12 s 仿真时长（24 × 0.5 s）。yaw 指令 1.0 rad/s ⇒ 期望转过 2 圈左右，必然穿越 ±180°。
SIM_SECONDS = 12.0
STEP_SECONDS = 0.5
YAW_CMD = 1.0
VX_CMD = 0.5
MIN_BASE_Z = 0.20
MAX_OMEGA = 8.0
MIN_YAW_SWEEP_DEG = 150.0

pytestmark = [pytest.mark.e2e]


@pytest.fixture(scope="session")  # 与 pytest-playwright 的同名夹具同作用域（session）
def browser_type_launch_args(browser_type_launch_args):
    """强制软件光栅（SwiftShader）：本用例判的是**物理/策略行为**，与帧率无关，
    而没有 GPU 的容器里 WebGL 起不来就会一直等 `#loading` ⇒ 假红。
    无头容器（CI/云开发）实测必须显式给这两个参数。"""
    args = list(browser_type_launch_args.get("args") or [])
    return {**browser_type_launch_args, "args": [*args, "--use-gl=angle", "--use-angle=swiftshader"]}


def _watch(page: Page) -> dict[str, list[str]]:
    """页面级 JS 错误收集（资源级 4xx/5xx 不在这里判，避免把"多看一眼"变成噪声）。"""
    watched: dict[str, list[str]] = {"page_errors": [], "console_errors": []}
    page.on("pageerror", lambda exc: watched["page_errors"].append(str(exc)[:400]))

    def _on_console(msg) -> None:
        if msg.type == "error" and "Failed to load resource" not in str(msg.text or ""):
            watched["console_errors"].append(str(msg.text or "")[:400])

    page.on("console", _on_console)
    return watched


def _open_ready(page: Page, base_url: str) -> None:
    """打开页面并等到"策略真的加载完"（policyEnabled 只是开关，加载没完成时走站桩）。"""
    page.goto(f"{base_url}{POLICY_URL}", wait_until="domcontentloaded")
    page.wait_for_selector("#loading.is-hidden", state="attached", timeout=READY_TIMEOUT_MS)
    page.wait_for_function(
        "() => window.__sim2simDebug && window.__sim2simDebug.sample().policyLoaded",
        timeout=READY_TIMEOUT_MS,
    )
    page.wait_for_function(
        "() => window.__sim2simDebug.sample().time > 0.5",
        timeout=60_000,
    )


def _yaw_deg(quat: list[float]) -> float:
    w, x, y, z = quat
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _set_commands(page: Page) -> None:
    """滑条 = 指令（默认勾选"接管 idle 指令"）。打 input/change 两个事件，别只改 value。"""
    page.evaluate(
        """([vx, yaw]) => {
          const set = (id, value) => {
            const el = document.querySelector(id);
            if (!el) throw new Error(`缺少控件 ${id}`);
            el.value = String(value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
          };
          set('#velCmdVx', vx);
          set('#velCmdYaw', yaw);
        }""",
        [VX_CMD, YAW_CMD],
    )
    page.evaluate("() => window.__sim2simDebug.setPolicyEnabled(true)")
    page.evaluate("() => window.__sim2simDebug.setPaused(true)")


def test_policy_holds_through_180_degree_turn(page: Page, base_url: str) -> None:
    watched = _watch(page)
    _open_ready(page, base_url)
    _set_commands(page)

    rows: list[dict] = []
    elapsed = 0.0
    while elapsed < SIM_SECONDS:
        page.evaluate("(s) => window.__sim2simDebug.fastForward(s)", STEP_SECONDS)
        sample = page.evaluate("() => window.__sim2simDebug.sample()")
        elapsed += STEP_SECONDS
        omega = [float(v) for v in (sample.get("bodyAngularVel") or [])]
        rows.append({
            "t": sample.get("time"),
            "yawDeg": round(_yaw_deg(sample["quat"]), 1),
            "baseZ": sample.get("baseZ"),
            "omega": [round(v, 3) for v in omega],
            "omegaNorm": round(math.sqrt(sum(v * v for v in omega)), 3) if omega else None,
        })

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACT_DIR / "yaw-sweep.png"))
    (ARTIFACT_DIR / "yaw-sweep.json").write_text(
        json.dumps({"policy": "go2-rlsar-robotlab", "yawCmd": YAW_CMD, "vxCmd": VX_CMD,
                    "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    for row in rows:
        print(f"  t={row['t']:>6}  yaw={row['yawDeg']:>7}°  baseZ={row['baseZ']:>6}"
              f"  |ω|={row['omegaNorm']}  ω={row['omega']}")

    zs = [r["baseZ"] for r in rows if r["baseZ"] is not None]
    sweep = max(abs(r["yawDeg"]) for r in rows)
    peak_omega = max((r["omegaNorm"] or 0.0) for r in rows)

    assert not watched["page_errors"], f"页面 JS 错误：{watched['page_errors']}"
    assert not watched["console_errors"], f"console 错误：{watched['console_errors']}"
    assert sweep >= MIN_YAW_SWEEP_DEG, (
        f"姿态没遍历到位：最大 |yaw| = {sweep:.0f}° < {MIN_YAW_SWEEP_DEG:.0f}°"
        f"（指令 ωz={YAW_CMD} rad/s 时应转过去）"
    )
    assert min(zs) >= MIN_BASE_Z, (
        f"转到大角度时掉下去了：最低 baseZ = {min(zs):.3f} < {MIN_BASE_Z}"
        f"（转 180° 抽风的特征是角速度反馈反号 ⇒ 乱动失衡）"
    )
    assert peak_omega <= MAX_OMEGA, (
        f"角速度读数不合理：峰值 |ω| = {peak_omega:.2f} rad/s > {MAX_OMEGA}"
        f"（机身真实角速度达不到这个量级；双重旋转会让读数爆表）"
    )
