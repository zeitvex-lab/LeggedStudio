#!/usr/bin/env python3
"""print_runtime_limits.py — 打印**当前生效**的运行时档位与阈值（H8 / H9 / H10）。

验收口径里那句「工具可打印生效阈值」就是本脚本：所有数字都从
``registry/*.json`` 现读，打印结果即运行时会用到的值，因此**改注册表后重跑即可
看到变化**，不需要读代码、也不会有第二份数字。

用法：
    python tools/print_runtime_limits.py            # 人类可读
    python tools/print_runtime_limits.py --json     # 机器可读
    python tools/print_runtime_limits.py --selftest # 附带三份自检结果
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.arrival_criteria import effective_thresholds  # noqa: E402
from backend.camera_projection import camera_profiles, distortion_impact  # noqa: E402
from backend.motion_commands import motion_command_profiles, timeout_policy  # noqa: E402
from backend.runtime_registry import registry_snapshot  # noqa: E402


def collect(include_selftest: bool = False) -> dict:
    payload: dict = {
        "registries": registry_snapshot(),
        "motion_commands": {
            "profile": "registry/motion_commands.json",
            "profiles": motion_command_profiles(),
            "timeout_policy": timeout_policy(),
        },
        "arrival_criteria": effective_thresholds(),
        "cameras": {
            "profile": "registry/cameras.json",
            "distortion_impact_px": {
                str(profile.get("id")): {
                    "model": profile.get("model"),
                    "max_delta_px": round(distortion_impact(str(profile.get("id")))["max_delta_px"], 3),
                    "mean_delta_px": round(distortion_impact(str(profile.get("id")))["mean_delta_px"], 3),
                }
                for profile in camera_profiles()
            },
        },
    }
    if include_selftest:
        from backend.arrival_criteria import arrival_selftest
        from backend.camera_projection import camera_projection_selftest
        from backend.motion_commands import motion_command_selftest

        payload["selftest"] = {
            "camera_projection": camera_projection_selftest()["verdict"],
            "motion_commands": motion_command_selftest()["verdict"],
            "arrival_criteria": arrival_selftest()["verdict"],
        }
    return payload


def _print_human(payload: dict) -> None:
    print("=" * 72)
    print("运动指令档位（H9）— registry/motion_commands.json")
    print("-" * 72)
    for name, cfg in payload["motion_commands"]["profiles"].items():
        limits = cfg.get("limits") or {}
        slew = cfg.get("slew") or {}
        deadzone = cfg.get("deadzone") or {}
        print(f"  [{name}] {cfg.get('label', '')}")
        print(f"      限速      vx ±{limits.get('vx')}  vy ±{limits.get('vy')}  yaw_rate ±{limits.get('yaw_rate')}  (m/s, rad/s)")
        print(f"      频率/超时 {cfg.get('command_hz')} Hz / {cfg.get('timeout_s')} s")
        print(f"      死区      min_effective {deadzone.get('min_effective')}")
        print(f"      加减速    accel {slew.get('accel')} / decel {slew.get('decel')}")
    policy = payload["motion_commands"]["timeout_policy"]
    print(f"  超时处置      {policy.get('on_timeout')} / 非有限值 {policy.get('on_non_finite')}")

    arrival = payload["arrival_criteria"]
    print()
    print("到达判据（H10）— registry/arrival_criteria.json")
    print("-" * 72)
    waypoint = arrival["waypoint"]
    dock = arrival["visual_dock"]
    print(f"  航点       容差 {waypoint['tolerance_m']} m ｜ 停航向 {waypoint['heading_tolerance_rad']} rad ｜ 稳定 {waypoint['stable_ticks']} 拍")
    print(f"  视觉停靠   横向 {dock['lateral_tolerance_m']} m ｜ 前向 {dock['forward_tolerance_m']} m ｜ 航向 {dock['yaw_tolerance_rad']:.6f} rad"
          f" ｜ 丢帧 {dock['lose_frame_s']} s / 确认 {dock['lose_confirm_s']} s")

    print()
    print("相机档位与畸变位移（H8）— registry/cameras.json")
    print("-" * 72)
    for profile_id, impact in payload["cameras"]["distortion_impact_px"].items():
        print(f"  {profile_id:32s} model={impact['model']:20s} max {impact['max_delta_px']:8.3f} px  mean {impact['mean_delta_px']:7.3f} px")

    if "selftest" in payload:
        print()
        print("自检")
        print("-" * 72)
        for name, verdict in payload["selftest"].items():
            print(f"  [{verdict}] {name}")
    print("=" * 72)


def main() -> int:
    ap = argparse.ArgumentParser(description="打印生效的运行时档位与阈值")
    ap.add_argument("--json", action="store_true", help="输出机器可读")
    ap.add_argument("--selftest", action="store_true", help="附带三份自检结果")
    args = ap.parse_args()

    payload = collect(include_selftest=args.selftest)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)

    if args.selftest and any(v != "pass" for v in payload["selftest"].values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
