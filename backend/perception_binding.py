"""感知观测绑定校验（H4 / H24）：**场景要求 A 类 ⇒ 策略必须真的声明了那项观测**。

要解决的假象
------------
`perception_route: obs`（A 类）的含义是"策略吃传感器"。但场景里写了 `heightfield: true`
并不等于策略真的吃了高度场——**那是训练 profile 的事**（`assets/robots/<pkg>/training/profiles/*.json`
里的 `obs_groups` / `depth` / `height_scan` 声明，例如 `go2-parkour` 的
`obs_groups.actor = [actor, proprio_history, camera]` + `depth.shape = [2,60,86]`）。

不校验的后果有两种，都是静默的：
* 策略没声明 → 运行时要么维度不匹配报错、要么**这一项被忽略**，而人以为它在生效；
* 声明的形状与场景要求不一致（如场景要 106×60、策略吃 2×60×86 的裁剪版）→ 结果对不上却查不出原因。

因此这里做**fail-closed 绑定**：场景声明 A 类感知 ⇒ 逐项对照策略 profile 的声明，
缺项即报出"缺什么 + 两种修法"（补 profile 声明，或把 route 改成 `external` 走 B 类）。

声明认定口径（**优先显式，其次扫描，并给出证据**）
--------------------------------------------------
1. profile 里显式写 `perception_items: ["heightfield", …]`（**推荐的新写法**，ids 取自
   `backend/perception_observations.py` 的目录）——最明确，不再依赖词形猜测；
2. 否则做**词形扫描**（兼容既有已移植 profile）：在 profile 的键与字符串值里找
   `depth` / `height_scan` / `heightfield` / `foot_contact` / `lidar` 等 token，
   以及观测项目录的 `sample_dot_path` 尾段；命中即视为声明，并把命中位置记进 `evidence`
   供人复核（扫描是保守的，宁可多报声明，也不许把"未声明"当"已声明"的相反方向出错）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: 场景 `perception` 字段 → 观测项目录 id（`perception_observations.PERCEPTION_ITEMS`）
FIELD_TO_ITEM: dict[str, str] = {
    "heightfield": "heightfield",
    "depth_camera": "depth_camera",
    "foot_contact": "foot_contact",
}

#: 词形扫描用的 token → 目录 id（profile 里出现即视为"声明了该项"）
TOKEN_TO_ITEM: dict[str, str] = {
    "depth_camera": "depth_camera",
    "depth_scan": "depth_camera",
    "camera": "depth_camera",
    "depth": "depth_camera",
    "heightfield": "heightfield",
    "height_scan": "heightfield",
    "foot_contact": "foot_contact",
    "contact_force": "foot_contact",
    "lidar_height_scan": "lidar_height_scan",
    "lidar": "lidar_height_scan",
}


def _as_dict(perception: Any) -> dict[str, Any] | None:
    if perception is None:
        return None
    if isinstance(perception, dict):
        return perception
    dump = getattr(perception, "model_dump", None)
    if callable(dump):  # pydantic 模型（contracts.scenario_contract.PerceptionSpec）
        return dump(mode="json")
    raise TypeError(f"无法解析 perception 声明（类型 {type(perception).__name__}）")


def required_items(perception: Any) -> list[str]:
    """场景声明里**真正启用**的观测项（True 或非空对象才算）。"""
    data = _as_dict(perception)
    if not data:
        return []
    enabled: list[str] = []
    for field, item in FIELD_TO_ITEM.items():
        value = data.get(field)
        if isinstance(value, dict):
            if value:
                enabled.append(item)
        elif value is True:
            enabled.append(item)
    return sorted(set(enabled))


def _walk_tokens(profile: Any, path: str = "") -> list[tuple[str, str]]:
    """递归收集 (token, 位置) —— 只在**键名与字符串值**上匹配，不看数字。"""
    found: list[tuple[str, str]] = []
    if isinstance(profile, dict):
        for key, value in profile.items():
            key_text = str(key).lower()
            for token in TOKEN_TO_ITEM:
                if token in key_text:
                    found.append((token, f"{path}.{key}"))
            found.extend(_walk_tokens(value, f"{path}.{key}"))
    elif isinstance(profile, list):
        for index, value in enumerate(profile):
            found.extend(_walk_tokens(value, f"{path}[{index}]"))
    elif isinstance(profile, str):
        text = profile.lower()
        for token in TOKEN_TO_ITEM:
            if token in text:
                found.append((token, path))
    return found


def profile_declared_items(profile: dict[str, Any] | None) -> dict[str, Any]:
    """策略 profile 声明的感知观测项。

    返回 ``{"declared": [...], "evidence": {item: [位置…]}, "source": "explicit"|"scan"}``。
    """
    if not isinstance(profile, dict):
        return {"declared": [], "evidence": {}, "source": "missing-profile"}
    explicit = profile.get("perception_items")
    if isinstance(explicit, list) and all(isinstance(x, str) for x in explicit):
        return {
            "declared": sorted(set(explicit)),
            "evidence": {item: ["perception_items"] for item in sorted(set(explicit))},
            "source": "explicit",
        }
    evidence: dict[str, list[str]] = {}
    for token, where in _walk_tokens(profile):
        item = TOKEN_TO_ITEM[token]
        evidence.setdefault(item, [])
        if len(evidence[item]) < 5 and where not in evidence[item]:
            evidence[item].append(where)
    return {"declared": sorted(evidence), "evidence": evidence, "source": "scan"}


def check_perception_binding(
    perception: Any,
    profile: dict[str, Any] | None,
    *,
    policy_id: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """A 类感知的绑定校验（fail-closed）。

    ``verdict``：
      * ``not_applicable`` —— 未声明 A 类（``route=external`` 或没写 perception）：B 类策略
        不必吃传感器，**不校验**（这正是"两条路径都算合格"的落地）；
      * ``ok`` —— 场景要求的每一项都被 profile 声明；
      * ``missing`` —— 有缺项（``ok=False``，含 ``missing`` / ``required`` / ``declared`` / ``fix``）。
    """
    data = _as_dict(perception)
    if data is None:
        return {"ok": True, "verdict": "not_applicable", "reason": "场景未声明 perception"}
    if str(data.get("route", "external")) != "obs":
        return {
            "ok": True,
            "verdict": "not_applicable",
            "route": str(data.get("route", "external")),
            "reason": "route=external（B 类：感知在策略外）⇒ 策略无需吃该传感器",
        }

    required = required_items(data)
    declared = profile_declared_items(profile)
    missing = [item for item in required if item not in declared["declared"]]
    result = {
        "ok": not missing,
        "verdict": "ok" if not missing else "missing",
        "route": "obs",
        "policy_id": policy_id,
        "profile_id": profile_id,
        "required": required,
        "declared": declared["declared"],
        "declaration_source": declared["source"],
        "evidence": declared["evidence"],
        "missing": missing,
    }
    if not required:
        result["ok"] = True
        result["verdict"] = "not_applicable"
        result["reason"] = "route=obs 但未启用任何感知观测项"
        return result
    if missing:
        result["reason"] = (
            f"A 类感知要求策略声明 {missing}，但 profile {profile_id or '<未知>'} 未声明"
            f"（已声明：{declared['declared'] or '无'}）"
        )
        result["fix"] = [
            "在该策略的训练 profile 里补声明（推荐显式写 perception_items: ["
            + ", ".join(repr(item) for item in missing)
            + "]），或",
            "把场景 perception.route 改为 external（B 类：RL 只管运动，感知在外挂模块）",
        ]
    return result


def load_profile_for_policy(package_root: Path, sim_cfg: dict[str, Any], policy_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """按策略 id 找到它的训练 profile（``simulation/config.json`` → ``training/profiles/*.json``）。

    返回 ``(profile_dict, profile_id)``；策略或 profile 文件缺失时返回 ``(None, profile_id)``
    —— **不抛错**：调用方据此把 verdict 判成 missing（fail-closed），而不是静默放行。
    """
    policies = sim_cfg.get("policies") or []
    entry = next((p for p in policies if str(p.get("id")) == str(policy_id)), None)
    if entry is None:
        return None, None
    profile_id = str((entry.get("training_ref") or {}).get("profile") or "") or None
    if not profile_id:
        return None, None
    profile_path = Path(package_root) / "training" / "profiles" / f"{profile_id}.json"
    if not profile_path.is_file():
        return None, profile_id
    try:
        return json.loads(profile_path.read_text(encoding="utf-8-sig")), profile_id
    except json.JSONDecodeError:
        return None, profile_id
