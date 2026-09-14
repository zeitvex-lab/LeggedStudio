"""E3：奖励目录（四层分组 + 中文名/说明 + 冲突提示）。

## 这一层解决什么

奖励项目录（`registry/rewards/reward_terms.json`）已有中文名/说明/默认值/`supported`，
但编辑器还需要两件事：

1. **四层分组**（Tracking / Regularization / Style / Contact）—— 让"我到底在惩罚什么"
   一眼可见。分组真值在 `adapters/mjlab/reward_layers.py`（曲线着色与编辑器**共用同一映射**，
   否则曲线一种分法、编辑器另一种分法，看的人会被绕晕）。
2. **经典冲突提示** —— 冲突清单是**数据**（`registry/rewards/conflicts.json`），
   判定规则是代码。三条都是结构性/尺度性的，可从一份权重表直接算出来：
   大 tracking 权重→暴力追踪抖动、早期严罚接触→学会不动、tracking 与 Style 目标互斥。

**冲突不是错误**：有时就是要那么配（比如故意做对比实验）。所以这里只**报**，不拦 ——
除非它同时踩到 `training_invariants` 的硬约束（那是另一层的事）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
CONFLICTS_PATH = ROOT / "registry" / "rewards" / "conflicts.json"

#: 冲突判定用到的"结构常数"：哪些项算追踪、哪些层算风格/接触。
#: 与 `reward_layers.py` 的四层口径一致；写在这里是为了**判定可测试**（不藏在 if 里）。
TRACKING_TERMS = ("tracking_lin_vel", "tracking_ang_vel")
CONTACT_TERMS = ("feet_air_time", "contact", "feet_contact")
PENALTY_TERMS = ("torques", "action_rate", "joint_torques")
#: "一枝独秀"的经验阈值：最大正权重 / 第二大正权重。
DOMINANCE_RATIO = 5.0


def _load_conflicts() -> list[dict[str, Any]]:
    try:
        payload = json.loads(CONFLICTS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("conflicts")
    return [dict(item) for item in items] if isinstance(items, list) else []


def _check_tracking_dominates(weights: Mapping[str, float]) -> bool:
    positives = sorted((float(v) for v in weights.values() if float(v) > 0), reverse=True)
    if len(positives) < 2:
        return False
    return positives[0] > DOMINANCE_RATIO * positives[1]


def _check_contact_penalty_dominates(weights: Mapping[str, float]) -> bool:
    """接触/节律类**罚**得比目标还重 → 最省事的解法是站着不动。"""
    contact_penalty = max(
        (abs(float(weights.get(term, 0.0))) for term in CONTACT_TERMS if float(weights.get(term, 0.0)) < 0),
        default=0.0,
    )
    if contact_penalty <= 0.0:
        return False
    targets = max((float(weights.get(term, 0.0)) for term in TRACKING_TERMS), default=0.0)
    return contact_penalty > targets


def _check_tracking_with_style(weights: Mapping[str, float]) -> bool:
    """速度跟踪与"模仿风格"同时当主目标 = 目标打架（两类在仓里本来就分族）。"""
    from adapters.mjlab.reward_layers import get_reward_layer

    tracking_on = any(float(weights.get(term, 0.0)) > 0 for term in TRACKING_TERMS)
    style_on = any(
        float(value) > 0 and get_reward_layer(str(term)) == "Style"
        for term, value in weights.items()
    )
    return tracking_on and style_on


CHECKS = {
    "tracking_dominates": _check_tracking_dominates,
    "contact_penalty_dominates": _check_contact_penalty_dominates,
    "tracking_with_style": _check_tracking_with_style,
}


def check_conflicts(weights: Mapping[str, float]) -> list[dict[str, Any]]:
    """按冲突清单检查一份权重表；返回命中的冲突（**不抛异常**）。"""
    hits: list[dict[str, Any]] = []
    for item in _load_conflicts():
        check = CHECKS.get(str(item.get("check") or ""))
        if check is None:
            continue
        try:
            hit = bool(check(weights))
        except Exception:  # noqa: BLE001  单条判定出错不该炸掉整个编辑器
            hit = False
        if hit:
            hits.append({
                "id": item.get("id"), "kind": item.get("kind"),
                "display_name": item.get("display_name"), "note": item.get("note"),
                "evidence": item.get("evidence"),
            })
    return hits


def catalog() -> dict[str, Any]:
    """编辑器用的一份完整奖励目录：四层分组 + 每项中文名/说明/默认值/支持状态 + 冲突清单。"""
    from adapters.mjlab.reward_layers import get_reward_layer
    from backend.skill_registry import reward_terms

    groups: dict[str, list[dict[str, Any]]] = {}
    for term_id, meta in reward_terms().items():
        layer = get_reward_layer(str(term_id))
        groups.setdefault(layer, []).append({
            "id": term_id,
            "label": meta.get("label"),
            "description": meta.get("description"),
            "default": meta.get("default"),
            "supported": bool(meta.get("supported", True)),
            "reason": meta.get("reason"),
        })
    for items in groups.values():
        items.sort(key=lambda item: str(item["id"]))
    conflicts = _load_conflicts()
    return {
        "groups": groups,
        "layer_order": ["Tracking", "Regularization", "Style", "Contact"],
        "conflicts": [{k: v for k, v in item.items() if k != "check"} for item in conflicts],
    }
