"""指令仲裁（H20）——纯函数：多源选一 + 超时失效 + 急停 latch + 模式门控。

与 H9 的分工：H9（``motion_commands.py``）做**单条指令的整形**（死区 / 裁剪 /
加减速限幅），本模块做**选哪条指令**（多源仲裁 + 失效判定 + 安全锁存），整形**复用 H9**。

上游依据（逐条可核）：

- ``cmd_mux_node.py``（rc_old .../sim2real_runtime/src/cmd_mux_node.py）：模式
  ``DISABLED/REMOTE/WEB/NAV/KEEP``、超时阶梯 ``250/300/500 ms``（``declare_parameter``
  默认值）、急停时 ``mode → DISABLED`` 并强制零输出（``on_estop`` + ``on_timer``）。
- ``LightNav-0/.../go2_adapter/safety.py``：``robot_mode not in {STAND, WALK}`` 不可走；
  源超时 → ``None``；非有限值 → ``None``。

三种"停"要分清（不能都糊成"零指令"）：

1. **超时→停**：源失效（``age_ms > timeout``）→ 输出零，但这是"该源没资格"，``accepted=True``；
2. **非有限值→拒**：指令含 NaN/Inf → ``accepted=False``（复用 H9 的 ``clamp_command``，
   它与 ``timeout_policy.on_non_finite=reject`` 一致）；
3. **急停/门控→零**：estop latch、robot_mode 非 STAND/WALK、DISABLED/KEEP 模式 →
   输出零，``accepted=True`` 且 ``reasons`` 说清为什么是零（不是"悄悄不动"）。
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.motion_commands import clamp_command, slew_limit

#: 合法模式（大小写不敏感；未知值一律回落到 DISABLED —— 安全默认）。
MODES: tuple[str, ...] = ("DISABLED", "REMOTE", "WEB", "NAV", "KEEP")

#: 各源超时阶梯（毫秒），逐字取自 ``cmd_mux_node.py`` 的 declare_parameter 默认值。
#: 处置语义（超时即停）由 ``registry/motion_commands.json#timeout_policy.on_timeout=stop``
#: 声明；这里只声明**每个源多少毫秒算失效**（控制器实现细节，与 timeout_policy.note 一致）。
TIMEOUT_MS: dict[str, float] = {"remote": 250.0, "web": 300.0, "nav": 500.0}

#: 允许行走的机器人模式（LightNav-0 safety.py 的 ``robot_mode not in {STAND, WALK}``）。
ALLOWED_ROBOT_MODES: frozenset[str] = frozenset({"STAND", "WALK"})

#: 仲裁的三个指令源（与 TIMEOUT_MS 键一一对应）。
_SOURCES: tuple[str, ...] = ("remote", "web", "nav")


def parse_mode(value: Any) -> str:
    """把任意输入解析成合法模式；未知/非法值回落到 ``DISABLED``（安全默认）。"""
    text = str(value or "").strip().upper()
    return text if text in MODES else "DISABLED"


def _normalize_sources(
    sources: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """把输入源归一化成 ``{remote: {command, age_ms}, ...}``；缺失的源记为 ``{}``（无数据）。"""
    normalized: dict[str, dict[str, Any]] = {}
    for key in _SOURCES:
        entry = (sources or {}).get(key) or {}
        normalized[key] = dict(entry) if isinstance(entry, Mapping) else {}
    return normalized


def _is_fresh(age_ms: Any, timeout_ms: float) -> bool:
    """源是否新鲜（``age_ms <= timeout_ms``，含边界 —— 与上游 ``is_fresh`` 一致）。

    ``age_ms`` 缺失 / 非数 / 为 ``None`` 一律视为**不新鲜**（从未收到过数据）。
    """
    if age_ms is None:
        return False
    try:
        return float(age_ms) <= float(timeout_ms)
    except (TypeError, ValueError):
        return False


def arbitrate_command(
    *,
    mode: str,
    estop: bool = False,
    robot_mode: str = "WALK",
    enabled: Mapping[str, bool] | None = None,
    sources: Mapping[str, Any] | None = None,
    previous: Mapping[str, Any] | None = None,
    dt: float | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """仲裁一条最终运动指令。

    - ``mode``：DISABLED/REMOTE/WEB/NAV/KEEP（未知 → DISABLED）；
    - ``estop``：急停锁存 —— 为真时强制零输出，且 ``mode_effective`` 落到 DISABLED
      （纯函数表达"锁存"：调用方看到 mode_effective=DISABLED，就知道要重新选模式才能恢复）；
    - ``robot_mode``：机器人状态（STAND/WALK 才允许行走，其它一律零）；
    - ``enabled``：``{remote/web/nav: bool}`` 各源使能（缺省全开）；
    - ``sources``：``{remote/web/nav: {command, age_ms}}`` 各源最新指令与距上次更新的毫秒；
    - ``previous``/``dt``：给 H9 的加减速限幅（可省）；
    - ``profile``：H9 运动档位（默认注册表默认档）。

    返回 ``{accepted, mode, mode_effective, source, command, reasons, ...}``：
    整形失败（非有限值）透传 H9 的 ``accepted=False``；其余"零输出"都 ``accepted=True``
    并在 ``reasons`` 里说清"为什么是零"。
    """
    resolved_mode = parse_mode(mode)
    enabled_map = {key: bool((enabled or {}).get(key, True)) for key in _SOURCES}
    source_map = _normalize_sources(sources)
    reasons: list[str] = []

    mode_effective = resolved_mode
    if estop:
        mode_effective = "DISABLED"
        reasons.append("急停锁存：输出强制为零，需解除急停并重新选模式才能恢复")
        return {
            "accepted": True,
            "mode": resolved_mode,
            "mode_effective": mode_effective,
            "source": "estop",
            "command": {"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0},
            "requested": None,
            "reasons": reasons,
            "clipped": [],
            "rate_limited": [],
        }

    if str(robot_mode).upper() not in ALLOWED_ROBOT_MODES:
        reasons.append(f"robot_mode={robot_mode!r} 不在 {sorted(ALLOWED_ROBOT_MODES)}，禁止行走")
        return {
            "accepted": True,
            "mode": resolved_mode,
            "mode_effective": mode_effective,
            "source": "stand",
            "command": {"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0},
            "requested": None,
            "reasons": reasons,
            "clipped": [],
            "rate_limited": [],
        }

    # 选源：DISABLED / KEEP 与超时失效都落零。
    source = "zero"
    target: dict[str, Any] | None = None
    if resolved_mode == "DISABLED":
        source = "disabled"
        reasons.append("模式 DISABLED：指令源关闭")
    elif resolved_mode == "KEEP":
        source = "keep"
        reasons.append("模式 KEEP：朝零收敛（减速停）")
    elif resolved_mode in ("REMOTE", "WEB", "NAV"):
        key = resolved_mode.lower()
        if not enabled_map[key]:
            source = "zero"
            reasons.append(f"源 {key} 未使能（enabled.{key}=False）")
        else:
            entry = source_map[key]
            if not entry:
                reasons.append(f"源 {key} 从未收到数据（视为超时）")
            elif not _is_fresh(entry.get("age_ms"), TIMEOUT_MS[key]):
                reasons.append(f"源 {key} 超时（age {entry.get('age_ms')} ms > {TIMEOUT_MS[key]:.0f} ms）→ 停")
            else:
                source = key
                target = entry.get("command")

    if target is None:
        return {
            "accepted": True,
            "mode": resolved_mode,
            "mode_effective": mode_effective,
            "source": source,
            "command": {"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0},
            "requested": None,
            "reasons": reasons,
            "clipped": [],
            "rate_limited": [],
        }

    # 复用 H9 整形：死区 + 裁剪 +（可选）加减速限幅。非有限值在此被拒（accepted=False）。
    clamped = clamp_command(target, profile=profile)
    if not clamped["accepted"]:
        return {
            "accepted": False,
            "mode": resolved_mode,
            "mode_effective": mode_effective,
            "source": source,
            "command": None,
            "requested": None,
            "reasons": [*reasons, *clamped["reasons"]],
            "clipped": clamped["clipped"],
            "rate_limited": [],
        }

    if previous is None or dt is None:
        return {
            "accepted": True,
            "mode": resolved_mode,
            "mode_effective": mode_effective,
            "source": source,
            "command": clamped["command"],
            "requested": clamped["requested"],
            "reasons": [*reasons, *clamped["reasons"]],
            "clipped": clamped["clipped"],
            "rate_limited": [],
        }

    slewed = slew_limit(previous, clamped["command"], dt=dt, profile=profile)
    if not slewed["accepted"]:
        return {
            "accepted": False,
            "mode": resolved_mode,
            "mode_effective": mode_effective,
            "source": source,
            "command": None,
            "requested": None,
            "reasons": [*reasons, *slewed["reasons"]],
            "clipped": clamped["clipped"],
            "rate_limited": [],
        }
    return {
        "accepted": True,
        "mode": resolved_mode,
        "mode_effective": mode_effective,
        "source": source,
        "command": slewed["command"],
        "requested": clamped["requested"],
        "reasons": [*reasons, *clamped["reasons"], *slewed["reasons"]],
        "clipped": clamped["clipped"],
        "rate_limited": slewed["rate_limited"],
    }
