"""E4：观测/动作映射板的数据（维度自动校验 + 观测五元组可视化）。

## 五元组（重构方案 §5.1）

观测组件 = ``(source, role[actor|critic|teacher|student], history, encoder, deployment_available)``。
**部署观测 = 过滤 `deployment_available=true ∧ role=actor`** —— 这条规则让"训练能看、部署看不到"
的特权信息无处可藏；`observation_convergence` 是同一规则的运行时校验器。

## 为什么这层必须"控制面安全"

它要进 HTTP 端点，而端点在控制面（V5：控制面不 import torch/mjlab）。所以这里**只读契约声明**
（`observation` / `action` / `joints`），不建环境、不编译模型 —— 因此它能在没有 GPU 的机器上
给编辑器画板子，也能在训练前就把"维度不符"拦下来。

## 判据原文："维度不符即时报错"

`problems` 是**结论**（不是日志）：动作数与契约不符、`joint_order` 指到未驱动关节、
组件宽度之和与声明宽度不符 —— 任意一条命中，板子上直接标红。
"""

from __future__ import annotations

from typing import Any, Mapping

#: 五元组的规范字段名（缺哪个就报哪个，不猜默认值）。
FIVE_TUPLE = ("source", "role", "history", "encoder", "deployment_available")
#: 部署侧允许出现的角色（`deployment_available=true ∧ role=actor`）。
DEPLOYABLE_ROLE = "actor"


def _components(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    observation = contract.get("observation") or {}
    raw = observation.get("components")
    return [dict(item) for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _actuated_joints(contract: Mapping[str, Any]) -> list[str]:
    joints = contract.get("joints") or {}
    actuated = joints.get("actuated")
    names: list[str] = []
    if isinstance(actuated, list):
        for item in actuated:
            if isinstance(item, Mapping) and item.get("name"):
                names.append(str(item["name"]))
            elif isinstance(item, str):
                names.append(item)
    return names


def observation_board(contract: Mapping[str, Any]) -> dict[str, Any]:
    """观测侧：组件（含五元组）、声明宽度、部署可用宽度与缺失字段。"""
    observation = contract.get("observation") or {}
    declared = observation.get("dimension")
    components = _components(contract)
    problems: list[str] = []

    rows: list[dict[str, Any]] = []
    for item in components:
        missing = [key for key in FIVE_TUPLE if key not in item]
        width = item.get("width")
        rows.append({
            "id": item.get("id") or item.get("name"),
            "width": width,
            **{key: item.get(key) for key in FIVE_TUPLE},
            "missing_fields": missing,
            "deployable": bool(item.get("deployment_available")) and str(item.get("role")) == DEPLOYABLE_ROLE,
        })
        if missing:
            problems.append(
                f"组件 {item.get('id') or item.get('name')}：五元组缺字段 {missing}"
                "（缺的字段会一路传到部署侧，必须补齐）",
            )

    widths = [row["width"] for row in rows if isinstance(row["width"], int)]
    total = sum(widths) if len(widths) == len(rows) and rows else None
    if total is not None and isinstance(declared, int) and total != declared:
        problems.append(
            f"组件宽度之和 {total} 与契约声明 dimension {declared} 不符 —— 维度不符即时报错",
        )

    deployable_dim = sum(row["width"] for row in rows
                         if row.get("deployable") and isinstance(row["width"], int)) if rows else None
    return {
        "declared_dimension": declared,
        "components_declared": len(rows),
        "components": rows,
        # 组件一个都没声明时**如实说"未声明"**，不拿 dimension 假充组件之和
        "components_total": total,
        "deployment_dimension": deployable_dim if rows else None,
        "note": None if rows else "契约未声明 observation.components：仅能给出声明宽度，"
                                  "五元组与部署宽度无从校验（不猜）",
        "problems": problems,
    }


def action_board(contract: Mapping[str, Any]) -> dict[str, Any]:
    """动作侧：策略输出槽位 ↔ 机器人真实关节（顺序、缺件、多余）。"""
    action = contract.get("action") or {}
    order = [str(item) for item in (action.get("joint_order") or [])]
    actuated = _actuated_joints(contract)
    problems: list[str] = []

    unknown = [name for name in order if actuated and name not in actuated]
    missing = [name for name in actuated if order and name not in order]
    if unknown:
        problems.append(f"joint_order 指向未被驱动的关节：{unknown}")
    if missing:
        problems.append(f"被驱动的关节没进 joint_order：{missing}（策略永远动不了它们）")
    if order and actuated and len(order) != len(actuated):
        problems.append(f"动作维度 {len(order)} 与驱动关节数 {len(actuated)} 不符")

    return {
        "action_dim": len(order),
        "joint_order": order,
        "actuated_joints": actuated,
        "action_scale": action.get("action_scale"),
        "unknown_in_order": unknown,
        "missing_from_order": missing,
        "problems": problems,
    }


def board(contract: Mapping[str, Any]) -> dict[str, Any]:
    """整块板子：观测侧 + 动作侧 + 总判定（**维度不符即时报错**）。"""
    observations = observation_board(contract)
    actions = action_board(contract)
    problems = [f"观测：{item}" for item in observations["problems"]] + \
               [f"动作：{item}" for item in actions["problems"]]
    return {
        "robot_id": contract.get("robot_id"),
        "contract_id": contract.get("contract_id"),
        "observations": observations,
        "actions": actions,
        "ok": not problems,
        "problems": problems,
    }
