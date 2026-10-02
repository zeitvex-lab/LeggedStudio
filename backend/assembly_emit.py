"""assembly_emit — 部署契约的**机械导出**（契约导出原则的落地点，2026-10-02）。

## 为什么存在（06 §0.4「契约导出原则」）

部署所需的全部信息在训练时刻就已存在（effective-config 的动作段/观测段/命令域），
但契约 historically 靠"读着产物手写第二份文档"——每个新机器人 × 新任务重新法证，
每步可能静默错（缩放 0.35/轮 35/观测错序三次事故同一根因）。本模块把它变成
**一次实现、处处免费**的导出：`emit_assembly(effective, snapshot) -> assembly 块`。

## 口径

* **段序真值 = effective-config 的 terms 序**（训练装配顺序）；contract_snapshot 的
  组件序是**部署视图**、可融合可换序，不可作段序来源（2026-10-02 混合 57 实测教训）。
* 宽度：fixed 语义段（ang/gravity/cmd）查表；关节段 = params 列表**长度**（序列化
  掩码保留长度，名字不可信但长度可信）；actions 段 = 快照动作序长度。
* `wrap` 标记（wheel pos 段）按名称规则导出为**数据**——通用解释器支持前它只是
  如实记录（专用 builder 消费同一语义）；"契约没写的 = 训练没用的"原则不变。
* 本模块**只导出不裁决**：产出随 promote 盖进条目 `contract.assembly`，消费方
  （评测/浏览器）逐字段读取；行为差异由 assembly_parity 门（对拍 effective-config）
  兜底。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: 固定宽度语义段（与评测器 frame_from_spec 词汇表同源）
FIXED_WIDTHS: dict[str, int] = {
    "base_ang_vel": 3,
    "projected_gravity": 3,
    "command": 3,
    "base_lin_vel": 3,
}


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def emit_assembly(effective: Mapping[str, Any], snapshot: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """effective-config → ``assembly`` 块（行为字段全量）。

    返回 ``None`` = 结构不认识（调用方如实缺，不编造）。
    """
    env = effective.get("environment") if isinstance(effective, Mapping) else None
    if not isinstance(env, Mapping):
        return None

    # ① 动作段表（顺序 = env actions 装配序）
    action_terms: list[dict[str, Any]] = []
    for name, term in (env.get("actions") or {}).items():
        if not isinstance(term, Mapping):
            continue
        joints = [str(x) for x in (term.get("actuator_names") or term.get("joint_names") or [])]
        if not joints:
            continue
        mode = "velocity" if "vel" in str(name).lower() else "position"
        entry: dict[str, Any] = {"term": str(name), "mode": mode, "joints": joints}
        scale = term.get("scale")
        if isinstance(scale, Mapping):
            entry["scale_by_joint"] = {str(k): float(v) for k, v in scale.items()}
        else:
            s = _num(scale)
            if s is not None:
                entry["scale"] = s
        offset = _num(term.get("offset"))
        if offset not in (None, 0.0):
            entry["offset"] = offset
        cutoff = _num(term.get("cut_off_frequency"))
        if cutoff is not None:
            entry["cutoff_hz"] = cutoff
            cf = _num(term.get("control_frequency"))
            if cf is not None:
                entry["control_frequency_hz"] = cf
        action_terms.append(entry)

    # ② 观测段表（顺序 = actor terms 装配序；宽度 = 语义宽或关节列表长度）
    obs_terms = (((env.get("observations") or {}).get("actor") or {}).get("terms")) or {}
    # actions 段宽 = effective-config 各动作段关节数之和（**训练真值**）；
    # 快照 joint_order 是部署视图（go2w legs-only 训练 12 动作、快照却写 16 名序——
    # 2026-10-02 sweep 实测 20 run 全部因此假阳性），只作兜底。
    action_dim = sum(
        len(term.get("actuator_names") or term.get("joint_names") or [])
        for term in (env.get("actions") or {}).values()
        if isinstance(term, Mapping)
    ) or (len(((snapshot or {}).get("action") or {}).get("joint_order") or []) if snapshot else None)
    # 快照组件**按名宽度表**（部署视图的宽度可用——宽度不是序敏感信息；
    # 序永远信 effective-config）。名字冲突时以 effective-config 优先。
    snap_widths: dict[str, int] = {}
    for c in ((snapshot or {}).get("observation") or {}).get("components") or []:
        if isinstance(c, Mapping) and c.get("name") and c.get("width"):
            snap_widths[str(c["name"])] = int(c["width"])
    obs_segments: list[dict[str, Any]] = []
    for name, term in obs_terms.items():
        params = (term.get("params") or {}) if isinstance(term, Mapping) else {}
        asset = params.get("asset_cfg") or {}
        joint_names = asset.get("joint_names") if isinstance(asset, Mapping) else None
        joint_names = joint_names or params.get("joint_names") or params.get("actuator_names") or []
        if name == "actions":
            width = action_dim
        elif name in FIXED_WIDTHS:
            width = FIXED_WIDTHS[name]
        elif isinstance(joint_names, list) and joint_names:
            width = len(joint_names)
        elif name in snap_widths:
            width = snap_widths[name]
        else:
            width = None
        seg: dict[str, Any] = {"term": str(name), "width": width}
        if "wheel" in str(name).lower() and "pos" in str(name).lower():
            seg["wrap"] = True
        obs_segments.append(seg)

    # ③ 命令域（ranges + 课程 stages——stages 是 env-steps 口径，随契约下发）
    twist = ((env.get("commands") or {}).get("twist")) or {}
    ranges_raw = twist.get("ranges") or {}
    command_ranges = {
        str(k): [float(v[0]), float(v[1])]
        for k, v in ranges_raw.items()
        if isinstance(v, (list, tuple)) and len(v) == 2
    } if isinstance(ranges_raw, Mapping) else {}
    stages_raw = (((env.get("curriculum") or {}).get("command_vel") or {}).get("params") or {}).get("velocity_stages")
    command_stages = stages_raw if isinstance(stages_raw, list) else None

    if not action_terms and not obs_segments:
        return None

    return {
        "schema": "assembly-emit-1.0",
        "action_terms": action_terms,
        "obs_segments": obs_segments,
        **({"command_ranges": command_ranges} if command_ranges else {}),
        **({"command_stages": command_stages} if command_stages else {}),
    }
