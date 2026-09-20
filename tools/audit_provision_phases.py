#!/usr/bin/env python3
"""A1 桌面环境供应"四段"的静态门禁（可在 CI 跑，**不代替 Windows 实机验证**）。

## 为什么要有它

A1 的四段（只读启动 → 点配置才下载 → 镜像源切换 → 离线 wheelhouse）落在
`electron/launcher/main.js` 与 `scripts/provision_windows_runtime.ps1` 里，**只能在 Windows 上真跑**。
而"只能人工验"的功能最容易在后续改动里悄悄退化（少一个档位、回退路径被删、离线档又开始联网）。

本门禁把四段的**结构契约**钉成机器可校验的判据：关键参数、回退路径、离线硬保证
（`--no-index` + `--find-links`）、以及"启动路径不自动下载"。全绿只是"结构还在"，
**不等于** Windows 上跑得通 —— 所以输出里会明确写这一句，避免有人把绿读成"实机验证过"。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provision_windows_runtime.ps1"
LAUNCHER = ROOT / "electron" / "launcher" / "main.js"

#: **stdout 永不因编码崩**（2026-09-20 实测踩到）：本门禁的输出含 `✓`（U+2713）与中文，
#: 而 Windows 上 stdout 被**重定向/管道**时按 locale（GBK）编码 —— 于是
#: `print("✓ …")` 抛 `UnicodeEncodeError`，**门禁自己崩掉（exit 1）而不是报告结论**。
#: 触发场景很平常：任何 PS/批处理脚本把它的输出收进文件或 `*>` 掉（`scripts/verify_windows_real_machine.ps1`
#: 第一次就这么撞上）。直跑不撞只因为调用方碰巧设了 `PYTHONIOENCODING=utf-8`，属"环境对了才活"。
#: 与今日修的子进程解码缺陷（`validate_training_smoke` / `simulation_api` / `training_config_helpers`
#: / `replay_gate` 的 `encoding="utf-8"`）同族，只是发生在**自身的输出端**。
#: `errors="replace"` 是第二道保险：真出现编码不了的字符也只损失那几个字符，绝不中断判据。
try:  # pragma: no cover - 平台相关，Linux/CI 上本就 UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # 极老的解释器或不可重配的流：照旧跑
    pass

#: 实机验证状态（**不随静态门禁变绿而变绿**）
WINDOWS_E2E_VERIFIED = False


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _find(lines: list[str], pattern: str) -> list[int]:
    regex = re.compile(pattern)
    return [index + 1 for index, line in enumerate(lines) if regex.search(line)]


def audit() -> dict:
    checks: list[dict] = []

    def check(phase: str, name: str, ok: bool, evidence: list[int] | str = "") -> None:
        checks.append({
            "phase": phase, "check": name, "ok": bool(ok),
            "evidence": evidence if isinstance(evidence, str) else (
                f"第 {evidence[0]} 行" if len(evidence) == 1 else f"第 {evidence[0]}~{evidence[-1]} 行" if evidence else ""
            ),
        })

    if not SCRIPT.is_file() or not LAUNCHER.is_file():
        return {
            "ok": False,
            "windows_e2e_verified": WINDOWS_E2E_VERIFIED,
            "checks": [{"phase": "-", "check": "两个落点文件都在", "ok": False,
                        "evidence": f"{SCRIPT.name} / {LAUNCHER.name}"}],
            "problems": [f"缺文件：{SCRIPT} 或 {LAUNCHER}"],
        }

    ps = _lines(SCRIPT)
    js = _lines(LAUNCHER)

    # ---- 第 1 段：只读启动器（启动路径不自动下载；探测是只读开关） ----
    provision_calls = _find(js, r"provisionWindowsRuntime\(\)")
    ipc_lines = _find(js, r"ipcMain\.handle\(\s*'environment:provision-windows'")
    check("1-只读启动", "启动路径不自动下载（provision 只由 IPC 触发）",
          bool(ipc_lines) and set(provision_calls) == set(ipc_lines) | {line for line in _find(js, r"function provisionWindowsRuntime")},
          ipc_lines)
    detect_lines = _find(js, r"'\-DetectGpus'")
    check("1-只读启动", "GPU 探测走只读开关 -DetectGpus", bool(detect_lines), detect_lines)
    list_profiles = _find(ps, r"\$ListProfiles")
    check("1-只读启动", "脚本提供只读查询 -ListProfiles（不写盘、不下载）", len(list_profiles) >= 2, list_profiles)

    # ---- 第 2 段：点配置才下载（显式入口 + 进度如实发布） ----
    check("2-显式配置", "启动器有显式配置入口 environment:provision-windows", bool(ipc_lines), ipc_lines)
    progress = _find(js, r"runtime-progress")
    check("2-显式配置", "配置过程有进度事件（阶段/百分比/文案）", len(progress) >= 2, progress)
    stages = _find(ps, r"Publish-Stage\s+'")
    check("2-显式配置", "脚本按阶段发布进度", len(stages) >= 4, stages)

    # ---- 第 3 段：镜像源切换（档位 + 自定义必须显式 + 回退） ----
    profile_param = _find(ps, r"ValidateSet\('cn', 'official', 'custom', 'offline'\)")
    check("3-镜像切换", "镜像档位四态可切换", bool(profile_param), profile_param)
    custom_guard = _find(ps, r"MirrorProfile -eq 'custom'")
    env_required = _find(ps, r"MirrorProfile=custom 需要")
    check("3-镜像切换", "custom 档必须显式给源（不能靠猜）", bool(custom_guard) and bool(env_required),
          env_required or custom_guard)
    fallback = _find(ps, r"official-fallback|回退官方源")
    check("3-镜像切换", "国内镜像失败会回退官方源并如实报出", len(fallback) >= 2, fallback)

    # ---- 第 4 段：离线 wheelhouse（必须是真的离线） ----
    wheelhouse_param = _find(ps, r"\[string\]\$Wheelhouse")
    offline_mode = _find(ps, r"\$offlineMode\s*=")
    check("4-离线wheelhouse", "提供 -Wheelhouse 且判定 offlineMode",
          bool(wheelhouse_param) and bool(offline_mode), wheelhouse_param or offline_mode)
    no_index = _find(ps, r"'--no-index'")
    find_links = _find(ps, r"'--find-links'")
    check("4-离线wheelhouse", "离线下用 --no-index + --find-links（不联网是硬保证）",
          bool(no_index) and bool(find_links), no_index + find_links)
    guards = _find(ps, r"MirrorProfile=offline 需要|wheelhouse 目录不存在")
    check("4-离线wheelhouse", "离线档缺 wheelhouse 时明确报错（不静默联网）", len(guards) >= 2, guards)
    manifest = _find(ps, r"\$manifest\.(mirror_profile|offline_mode|wheelhouse)")
    check("4-离线wheelhouse", "manifest 里登记档位/离线来源（可追溯）", len(manifest) >= 3, manifest)

    problems = [f"{item['phase']}｜{item['check']}" for item in checks if not item["ok"]]
    return {
        "ok": not problems,
        "windows_e2e_verified": WINDOWS_E2E_VERIFIED,
        "checks": checks,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A1 环境供应四段静态门禁")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 78)
        print("A1 环境供应四段（静态/契约核对）")
        print("=" * 78)
        for phase in ("1-只读启动", "2-显式配置", "3-镜像切换", "4-离线wheelhouse"):
            items = [item for item in report["checks"] if item["phase"] == phase]
            mark = "✓" if all(item["ok"] for item in items) else "✗"
            print(f"{mark} {phase}")
            for item in items:
                flag = "  ✓" if item["ok"] else "  ✗"
                print(f"{flag} {item['check']}" + (f"（{item['evidence']}）" if item["evidence"] else ""))
        print("-" * 78)
        print("注意：本门禁只做**结构/契约**核对，**不代替 Windows 实机验证**。"
              f"实机端到端：{'已验证' if report['windows_e2e_verified'] else '**未验证**（需真 Windows 上双击→配置→启动）'}")
        if report["problems"]:
            print(f"\n✗ 缺项 {len(report['problems'])} 项：")
            for item in report["problems"]:
                print(f"  - {item}")
        else:
            print("四段结构齐备。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
