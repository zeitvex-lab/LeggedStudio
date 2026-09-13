"""到达判据的唯一实现（H10）——阈值全部来自 ``registry/arrival_criteria.json``。

**修的是什么**：同一件「到没到」的事此前有三处数字——
``backend/navigation_api.py`` 的 ``waypoint_tolerance=0.35``（默认值）、
``backend/camera_projection.py`` 的 ``arrival_verdict(tolerance_m=0.3)``（默认值），
以及 ``00_resources/unitree_go2_edu_movement`` 里真机在用的 3 cm / 3 cm / 2.5°。
默认值分散 = 改一处不会同步。现在：

* 阈值只有 ``registry/arrival_criteria.json`` 一处；
* ``waypoint_arrival`` / ``visual_dock_arrival`` 是唯一判定实现，导航与相机投影都调它；
* 调用方**仍可**显式传入旧值（``0.35`` / ``0.3``），但结果会带 ``deviation`` 字段
  说明「你给的值偏离单一真值」，避免旧调用悄悄把口径带回去。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from backend.runtime_registry import load_registry

DEG = math.pi / 180.0


def arrival_criteria() -> dict[str, Any]:
    """完整的到达判据注册表。"""
    return dict(load_registry("arrival_criteria"))


def _section(name: str) -> dict[str, Any]:
    section = arrival_criteria().get(name)
    if not isinstance(section, dict):
        raise ValueError(f"registry/arrival_criteria.json 缺少 {name!r} 段")
    return section


def waypoint_spec() -> dict[str, Any]:
    """航点到达阈值（单一真值）。"""
    return _section("waypoint")


def visual_dock_spec() -> dict[str, Any]:
    """视觉停靠阈值（单一真值）。"""
    return _section("visual_dock")


def _legacy_alias_note(key: str, value: float, canonical: float) -> dict[str, Any] | None:
    """调用方显式传入的值偏离单一真值时给出提示（不阻断）。"""
    aliases = (arrival_criteria().get("legacy_aliases") or {}).get(key) or []
    if abs(float(value) - float(canonical)) < 1e-12:
        return None
    return {
        "field": key,
        "given": float(value),
        "canonical": float(canonical),
        "known_aliases": [float(a) for a in aliases],
        "hint": "该值偏离 registry/arrival_criteria.json 的单一真值；请统一到注册表",
    }


def waypoint_arrival(
    position_xy: Sequence[float],
    target_xy: Sequence[float],
    *,
    heading_rad: float | None = None,
    target_heading_rad: float | None = None,
    consecutive_ticks: int = 0,
    tolerance_m: float | None = None,
    heading_tolerance_rad: float | None = None,
    stable_ticks: int | None = None,
) -> dict[str, Any]:
    """航点到达判定：平面距离 + 停航向 + 连续稳定拍数三条件同时满足。

    返回 ``{arrived, distance_m, heading_error_rad, stable, thresholds, deviation, reasons}``。
    ``deviation`` 非空表示调用方用了偏离注册表的阈值。
    """
    spec = waypoint_spec()
    canonical_tolerance = float(spec["tolerance_m"])
    canonical_heading = float(spec["heading_tolerance_rad"])
    canonical_ticks = int(spec["stable_ticks"])

    tolerance = canonical_tolerance if tolerance_m is None else float(tolerance_m)
    heading_tol = canonical_heading if heading_tolerance_rad is None else float(heading_tolerance_rad)
    ticks_required = canonical_ticks if stable_ticks is None else int(stable_ticks)

    distance = math.dist(
        (float(position_xy[0]), float(position_xy[1])),
        (float(target_xy[0]), float(target_xy[1])),
    )
    heading_error: float | None = None
    if heading_rad is not None and target_heading_rad is not None:
        raw = float(heading_rad) - float(target_heading_rad)
        heading_error = math.atan2(math.sin(raw), math.cos(raw))  # 归一化到 (-π, π]

    reasons: list[str] = []
    in_position = distance <= tolerance
    if not in_position:
        reasons.append(f"位置未到：{distance:.3f} m > {tolerance:.3f} m")
    in_heading = True
    if heading_error is not None:
        in_heading = abs(heading_error) <= heading_tol
        if not in_heading:
            reasons.append(f"航向未对齐：{abs(heading_error):.3f} rad > {heading_tol:.3f} rad")
    stable = int(consecutive_ticks) >= ticks_required
    if not stable:
        reasons.append(f"稳定拍数不足：{int(consecutive_ticks)} < {ticks_required}")

    deviations = [
        note
        for note in (
            _legacy_alias_note("waypoint_tolerance", tolerance, canonical_tolerance),
            _legacy_alias_note("waypoint_heading_tolerance", heading_tol, canonical_heading),
        )
        if note
    ]

    return {
        "arrived": bool(in_position and in_heading and stable),
        "distance_m": distance,
        "heading_error_rad": heading_error,
        "stable": stable,
        "consecutive_ticks": int(consecutive_ticks),
        "thresholds": {
            "tolerance_m": tolerance,
            "heading_tolerance_rad": heading_tol,
            "stable_ticks": ticks_required,
        },
        "canonical_thresholds": {
            "tolerance_m": canonical_tolerance,
            "heading_tolerance_rad": canonical_heading,
            "stable_ticks": canonical_ticks,
        },
        "deviation": deviations,
        "reasons": reasons,
    }


def visual_dock_arrival(
    *,
    lateral_m: float,
    forward_m: float,
    yaw_error_rad: float,
    lost_frame_s: float = 0.0,
) -> dict[str, Any]:
    """视觉停靠判定：横向/前向/航向三项容差 + 丢帧时长（超时即判失败）。"""
    spec = visual_dock_spec()
    lateral_tol = float(spec["lateral_tolerance_m"])
    forward_tol = float(spec["forward_tolerance_m"])
    yaw_tol = float(spec["yaw_tolerance_rad"])
    lose_frame = float(spec["lose_frame_s"])
    lose_confirm = float(spec["lose_confirm_s"])

    in_lateral = abs(lateral_m) <= lateral_tol
    in_forward = abs(forward_m) <= forward_tol
    in_yaw = abs(yaw_error_rad) <= yaw_tol
    lost = float(lost_frame_s) >= lose_confirm

    reasons: list[str] = []
    if not in_lateral:
        reasons.append(f"横向偏差 {abs(lateral_m):.4f} m > {lateral_tol:.4f} m")
    if not in_forward:
        reasons.append(f"前向偏差 {abs(forward_m):.4f} m > {forward_tol:.4f} m")
    if not in_yaw:
        reasons.append(f"航向偏差 {abs(yaw_error_rad):.4f} rad > {yaw_tol:.4f} rad")
    if lost:
        reasons.append(f"目标丢失 {float(lost_frame_s):.2f} s ≥ {lose_confirm:.2f} s，判定停靠失败")
    elif float(lost_frame_s) > lose_frame:
        # 短暂丢失不判定失败，但要在原因里显式说明「正在等待」
        reasons.append(f"目标短暂丢失 {float(lost_frame_s):.2f} s（阈值 {lose_frame:.2f} s），保持等待")

    return {
        "docked": bool(in_lateral and in_forward and in_yaw and not lost),
        "lost": lost,
        "lost_frame_s": float(lost_frame_s),
        "thresholds": {
            "lateral_tolerance_m": lateral_tol,
            "forward_tolerance_m": forward_tol,
            "yaw_tolerance_rad": yaw_tol,
            "lose_frame_s": lose_frame,
            "lose_confirm_s": lose_confirm,
        },
        "reasons": reasons,
    }


def effective_thresholds() -> dict[str, Any]:
    """打印用：当前**生效**的全部到达阈值 + 出处（工具 / 健康检查共用）。"""
    criteria = arrival_criteria()
    return {
        "source": "registry/arrival_criteria.json",
        "schema": criteria.get("schema"),
        "waypoint": waypoint_spec(),
        "visual_dock": visual_dock_spec(),
    }


def arrival_selftest() -> dict[str, Any]:
    """离线自检：到点/超差、航向、稳定拍、停靠容差、丢帧、旧值偏离提示。"""
    cases: list[dict[str, Any]] = []

    def case(name: str, ok: bool, detail: dict[str, Any]) -> None:
        cases.append({"name": name, "ok": bool(ok), **detail})

    spec = waypoint_spec()
    ticks = int(spec["stable_ticks"])

    arrived = waypoint_arrival((0.0, 0.0), (0.1, 0.0), consecutive_ticks=ticks)
    missed = waypoint_arrival((0.0, 0.0), (1.0, 0.0), consecutive_ticks=ticks)
    case(
        "waypoint_arrival_respects_single_source_tolerance",
        arrived["arrived"] and not missed["arrived"] and arrived["thresholds"]["tolerance_m"] == float(spec["tolerance_m"]),
        {"arrived": arrived["arrived"], "distance": arrived["distance_m"], "tolerance": arrived["thresholds"]["tolerance_m"]},
    )

    unstable = waypoint_arrival((0.0, 0.0), (0.1, 0.0), consecutive_ticks=0)
    case(
        "waypoint_requires_stable_ticks",
        not unstable["arrived"] and any("稳定拍数不足" in r for r in unstable["reasons"]),
        {"reasons": unstable["reasons"], "required": int(spec["stable_ticks"])},
    )

    turned = waypoint_arrival((0.0, 0.0), (0.1, 0.0), heading_rad=math.pi / 2, target_heading_rad=0.0, consecutive_ticks=ticks)
    case(
        "waypoint_heading_gate",
        not turned["arrived"] and any("航向未对齐" in r for r in turned["reasons"]),
        {"heading_error_rad": turned["heading_error_rad"], "tolerance": turned["thresholds"]["heading_tolerance_rad"]},
    )

    legacy = waypoint_arrival((0.0, 0.0), (0.1, 0.0), consecutive_ticks=ticks, tolerance_m=0.35)
    case(
        "legacy_tolerance_is_flagged",
        legacy["deviation"] and legacy["deviation"][0]["canonical"] == float(spec["tolerance_m"]),
        {"deviation": legacy["deviation"]},
    )

    dock_spec = visual_dock_spec()
    docked = visual_dock_arrival(lateral_m=0.01, forward_m=0.02, yaw_error_rad=0.01)
    off = visual_dock_arrival(lateral_m=0.10, forward_m=0.02, yaw_error_rad=0.01)
    lost = visual_dock_arrival(lateral_m=0.01, forward_m=0.02, yaw_error_rad=0.01, lost_frame_s=3.0)
    case(
        "visual_dock_tolerances_and_lost_frame",
        docked["docked"] and not off["docked"] and lost["lost"] and not lost["docked"],
        {
            "lateral_tolerance_m": dock_spec["lateral_tolerance_m"],
            "yaw_tolerance_rad": dock_spec["yaw_tolerance_rad"],
            "lost_reasons": lost["reasons"],
        },
    )

    failures = [item["name"] for item in cases if not item["ok"]]
    return {
        "success": True,
        "thresholds": effective_thresholds(),
        "cases": cases,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }


__all__ = [
    "arrival_criteria",
    "waypoint_spec",
    "visual_dock_spec",
    "waypoint_arrival",
    "visual_dock_arrival",
    "effective_thresholds",
    "arrival_selftest",
    "DEG",
]
