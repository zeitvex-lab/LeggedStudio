"""运动指令档位与整形（H9）——纯函数，档位全部来自 ``registry/motion_commands.json``。

三件事，按真机链路的顺序：

1. **死区**：``|v| < min_effective`` 直接置零（真机上小指令只会让机器人抖）；
2. **裁剪**：超出 ``limits`` 的轴被裁到边界，并**如实报告被裁了什么**
   （``clipped`` 列表带 requested/applied/limit，不是悄悄改数）；
3. **加减速限幅**：按 ``slew.accel`` / ``slew.decel`` 与 ``dt`` 限制单步变化量
   （加速与减速分开，减速通常更快）。

契约约定：非有限值（NaN/Inf）按 ``timeout_policy.on_non_finite = reject`` 处理，
返回 ``accepted=False``；这比"把 NaN 传给电机"安全得多，也与 H20 的
「非有限值→拒」一致。
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from backend.runtime_registry import load_registry

#: 规范轴名 ↔ 允许的输入别名
AXIS_ALIASES: dict[str, str] = {
    "vx": "vx",
    "vy": "vy",
    "yaw_rate": "yaw_rate",
    "yaw": "yaw_rate",
    "wz": "yaw_rate",
    "v_yaw": "yaw_rate",
}
AXES: tuple[str, ...] = ("vx", "vy", "yaw_rate")

#: 判定「有效指令」的死区输入（与真机 5% 量级一致，避免浮点抖动触发）
_EPS = 1e-9


def motion_command_profiles() -> dict[str, dict[str, Any]]:
    """全部运动指令档位（``teleop`` / ``nav``）。"""
    payload = load_registry("motion_commands")
    profiles = payload.get("profiles") or {}
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("registry/motion_commands.json 未声明任何档位")
    return {str(name): dict(cfg) for name, cfg in profiles.items()}


def motion_command_profile(name: str | None = None) -> tuple[str, dict[str, Any]]:
    """取一个档位；``name`` 为 ``None`` 时用注册表声明的默认档。"""
    profiles = motion_command_profiles()
    if name is None:
        name = str(load_registry("motion_commands").get("default_profile") or "teleop")
    if name not in profiles:
        raise KeyError(f"未知运动指令档位 {name!r}；可选：{', '.join(sorted(profiles))}")
    return name, profiles[name]


def _canonical_command(command: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    """把输入指令规范化成 ``{vx, vy, yaw_rate}``，返回（指令, 未知/非法键）。"""
    out = {axis: 0.0 for axis in AXES}
    problems: list[str] = []
    for raw_key, raw_value in command.items():
        axis = AXIS_ALIASES.get(str(raw_key))
        if axis is None:
            problems.append(f"未知指令轴 {raw_key!r}")
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            problems.append(f"轴 {raw_key!r} 的值不是数：{raw_value!r}")
            continue
        if not math.isfinite(value):
            problems.append(f"轴 {raw_key!r} 的值非有限：{raw_value!r}")
            continue
        out[axis] = value
    return out, problems


def apply_deadzone(value: float, *, min_effective: float) -> float:
    """死区整形：绝对值小于阈值即置零。"""
    return 0.0 if abs(value) < float(min_effective) else float(value)


def clamp_command(
    command: Mapping[str, Any],
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """死区 + 限幅裁剪。返回带 ``clipped`` 明细与 ``reasons`` 的报告。"""
    name, cfg = motion_command_profile(profile)
    limits = {str(k): float(v) for k, v in (cfg.get("limits") or {}).items()}
    min_effective = float((cfg.get("deadzone") or {}).get("min_effective") or 0.0)

    values, problems = _canonical_command(command)
    if problems:
        return {
            "accepted": False,
            "profile": name,
            "command": None,
            "clipped": [],
            "reasons": problems,
            "limits": limits,
        }

    clipped: list[dict[str, Any]] = []
    shaped: dict[str, float] = {}
    for axis in AXES:
        value = apply_deadzone(values[axis], min_effective=min_effective)
        limit = limits.get(axis)
        if limit is not None and abs(value) > limit:
            clipped.append({"axis": axis, "requested": value, "applied": math.copysign(limit, value), "limit": limit})
            value = math.copysign(limit, value)
        shaped[axis] = value

    reasons: list[str] = []
    if clipped:
        reasons.append(
            "指令超限已裁剪：" + "、".join(f"{c['axis']} {c['requested']:.3f}→{c['applied']:.3f}" for c in clipped)
        )
    if min_effective and any(values[a] and not shaped[a] for a in AXES):
        reasons.append(f"低于死区 min_effective={min_effective} 的轴已置零")

    return {
        "accepted": True,
        "profile": name,
        "command": shaped,
        "requested": values,
        "clipped": clipped,
        "reasons": reasons,
        "limits": limits,
        "deadzone": {"min_effective": min_effective},
    }


def slew_limit(
    previous: Mapping[str, Any] | None,
    target: Mapping[str, Any],
    *,
    dt: float,
    profile: str | None = None,
) -> dict[str, Any]:
    """按加速/减速限幅把 ``previous`` 朝 ``target`` 推进一步（单步变化量 ≤ rate·dt）。"""
    name, cfg = motion_command_profile(profile)
    slew = cfg.get("slew") or {}
    accel = float(slew.get("accel") or 0.0)
    decel = float(slew.get("decel") or accel)
    step = max(0.0, float(dt))

    prev_values, _ = _canonical_command(previous or {})
    target_values, problems = _canonical_command(target)
    if problems:
        return {"accepted": False, "profile": name, "command": None, "reasons": problems}

    shaped: dict[str, float] = {}
    limited: list[dict[str, Any]] = []
    for axis in AXES:
        delta = target_values[axis] - prev_values[axis]
        # 朝零点收敛（|目标| 更小）算减速，用更快的 decel 档
        decelerating = abs(target_values[axis]) < abs(prev_values[axis])
        rate = decel if decelerating else accel
        max_delta = rate * step
        applied_delta = delta if max_delta <= 0 else max(-max_delta, min(max_delta, delta))
        if abs(applied_delta - delta) > _EPS:
            limited.append(
                {
                    "axis": axis,
                    "from": prev_values[axis],
                    "target": target_values[axis],
                    "applied": prev_values[axis] + applied_delta,
                    "rate": rate,
                }
            )
        shaped[axis] = prev_values[axis] + applied_delta

    return {
        "accepted": True,
        "profile": name,
        "command": shaped,
        "rate_limited": limited,
        "accel": accel,
        "decel": decel,
        "dt": step,
        "reasons": [f"{len(limited)} 个轴受加速/减速限幅"] if limited else [],
    }


def resolve_command(
    command: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
    dt: float | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """完整链路：死区 → 裁剪 →（可选）加减速限幅。"""
    clamped = clamp_command(command, profile=profile)
    if not clamped["accepted"]:
        return clamped
    if previous is None or dt is None:
        return clamped
    slewed = slew_limit(previous, clamped["command"], dt=dt, profile=profile)
    if not slewed["accepted"]:
        return slewed
    return {
        **clamped,
        "command": slewed["command"],
        "rate_limited": slewed["rate_limited"],
        "reasons": [*clamped["reasons"], *slewed["reasons"]],
    }


def timeout_policy() -> dict[str, Any]:
    """无指令/非法值的处置口径（供 H20 控制器引用）。"""
    return dict(load_registry("motion_commands").get("timeout_policy") or {})


def follow_controller_spec() -> dict[str, Any]:
    """H12 跟随控制器参数（唯一真值在 ``registry/motion_commands.json#follow_controller``）。

    **为什么放在这份注册表里**：运行时限值契约就是"三份注册表"（H8/H9/H10，有测试锁着），
    为跟随参数新开第四份会把那个契约改掉；而 nav 档本来就住在这个文件里，参数同源更近。

    缺块即报错——跟随参数不许在代码里留旧默认值（先前浏览器跟随器自造过一套，
    与 H12 点名的参考实现不一致，正是这种"悄悄用旧数字"造成的）。
    """
    spec = load_registry("motion_commands").get("follow_controller")
    if not isinstance(spec, dict) or not spec:
        raise ValueError(
            "registry/motion_commands.json 缺 follow_controller 块；"
            "跟随参数只有这一处真值，缺失即报错（不回退到代码默认值）"
        )
    return dict(spec)


def geometric_tracker_spec() -> dict[str, Any]:
    """H14 几何路径跟踪控制器参数（唯一真值在 ``registry/motion_commands.json#geometric_tracker``）。

    与 :func:`local_planner_spec` / :func:`follow_controller_spec` 同源同理：数字是数据，
    缺块即报错、不回退默认值。
    """
    spec = load_registry("motion_commands").get("geometric_tracker")
    if not isinstance(spec, dict) or not spec:
        raise ValueError(
            "registry/motion_commands.json 缺 geometric_tracker 块；"
            "跟踪参数只有这一处真值，缺失即报错（不回退到代码默认值）"
        )
    return dict(spec)


def mpc_tracker_spec() -> dict[str, Any]:
    """H14 可选对照控制器（mpc）参数（唯一真值在 ``registry/motion_commands.json#mpc_tracker``）。

    与 :func:`geometric_tracker_spec` / :func:`local_planner_spec` 同源同理：数字是数据，
    缺块即报错、不回退默认值。字段出处见该块的 ``evidence``（vln_mpc 的 mpc_node.py）。
    """
    spec = load_registry("motion_commands").get("mpc_tracker")
    if not isinstance(spec, dict) or not spec:
        raise ValueError(
            "registry/motion_commands.json 缺 mpc_tracker 块；"
            "MPC 对照参数只有这一处真值，缺失即报错（不回退到代码默认值）"
        )
    return dict(spec)


def route_postprocess_spec() -> dict[str, Any]:
    """H13 规划后处理参数（唯一真值在 ``registry/motion_commands.json#route_postprocess``）。

    与 :func:`local_planner_spec` 同源同理：数字是数据，缺块即报错、不回退默认值。
    """
    spec = load_registry("motion_commands").get("route_postprocess")
    if not isinstance(spec, dict) or not spec:
        raise ValueError(
            "registry/motion_commands.json 缺 route_postprocess 块；"
            "后处理参数只有这一处真值，缺失即报错（不回退到代码默认值）"
        )
    return dict(spec)


def local_planner_spec() -> dict[str, Any]:
    """H11 局部采样规划器（DWA）参数（唯一真值在 ``registry/motion_commands.json#local_planner``）。

    与 :func:`follow_controller_spec` 同源同理：数字是数据，缺块即报错、不回退默认值。
    """
    spec = load_registry("motion_commands").get("local_planner")
    if not isinstance(spec, dict) or not spec:
        raise ValueError(
            "registry/motion_commands.json 缺 local_planner 块；"
            "局部规划参数只有这一处真值，缺失即报错（不回退到代码默认值）"
        )
    return dict(spec)


def motion_command_selftest() -> dict[str, Any]:
    """离线自检：限幅裁剪、死区、非有限值拒绝、限速方向正确性、档位差异。"""
    cases: list[dict[str, Any]] = []

    def case(name: str, ok: bool, detail: dict[str, Any]) -> None:
        cases.append({"name": name, "ok": bool(ok), **detail})

    teleop = clamp_command({"vx": 5.0, "vy": -3.0, "yaw_rate": 3.0}, profile="teleop")
    case(
        "over_limit_is_clipped_and_reported",
        teleop["accepted"]
        and teleop["command"] == {"vx": 1.0, "vy": -1.0, "yaw_rate": 1.0}
        and len(teleop["clipped"]) == 3
        and all("超限已裁剪" in r for r in teleop["reasons"]),
        {"command": teleop["command"], "clipped": teleop["clipped"]},
    )

    dead = clamp_command({"vx": 0.1, "vy": 0.0, "yaw_rate": 0.0}, profile="teleop")
    case(
        "below_deadzone_zeroed",
        dead["command"]["vx"] == 0.0 and any("死区" in r for r in dead["reasons"]),
        {"command": dead["command"], "reasons": dead["reasons"]},
    )

    bad = clamp_command({"vx": float("nan")}, profile="teleop")
    case(
        "non_finite_rejected",
        bad["accepted"] is False and bad["command"] is None and any("非有限" in r for r in bad["reasons"]),
        {"reasons": bad["reasons"]},
    )

    nav = clamp_command({"vx": 5.0, "vy": 5.0, "yaw_rate": 5.0}, profile="nav")
    case(
        "nav_profile_differs_from_teleop",
        nav["command"] == {"vx": 0.9, "vy": 0.5, "yaw_rate": 0.85},
        {"nav_command": nav["command"], "teleop_limits": teleop["limits"]},
    )

    accel = slew_limit({"vx": 0.0}, {"vx": 1.0}, dt=0.1, profile="teleop")      # accel 1.0 → 0.1
    decel = slew_limit({"vx": 1.0}, {"vx": 0.0}, dt=0.1, profile="teleop")      # decel 2.0 → -0.2
    case(
        "slew_uses_accel_and_decel_rates",
        abs(accel["command"]["vx"] - 0.1) < 1e-9 and abs(decel["command"]["vx"] - 0.8) < 1e-9,
        {"accel_step": accel["command"]["vx"], "decel_step": decel["command"]["vx"]},
    )

    free = clamp_command({"vx": 0.5, "vy": 0.0, "yaw_rate": 0.0}, profile="teleop")
    case(
        "in_range_command_passes_untouched",
        free["command"]["vx"] == 0.5 and not free["clipped"] and not free["reasons"],
        {"command": free["command"]},
    )

    failures = [item["name"] for item in cases if not item["ok"]]
    return {
        "success": True,
        "profiles": sorted(motion_command_profiles()),
        "cases": cases,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }
