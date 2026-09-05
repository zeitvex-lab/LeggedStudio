"""自动参数目录：从内省树构建全量、分组的参数表（无人工精选）。

结构即分组（树的第一/二层）、段名标签词典中文化、深度规则渐进披露。
输出供前端抽屉渲染的分组树：

  groups = [
    {"title": "仿真器", "node": "environment.sim.mujoco",
     "params": [{"id","label","path","type","value","advanced"}, ...]},
    ...
  ]
"""

from __future__ import annotations

from typing import Any

from adapters.mjlab.param_catalog import (
    CATEGORY_BY_PREFIX,
    CATEGORY_TITLES,
    is_structural,
    label_for,
)


def _category_for(path: str) -> str:
    for prefix, cat in CATEGORY_BY_PREFIX:
        if path == prefix or path.startswith(prefix):
            return cat
    return "other"


def _leaf_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def build_param_groups(schema: dict, category: str) -> list[dict[str, Any]]:
    """对一个分类的 schema 子树构建分组参数表。

    分组 = 子树的一级模块节点（如 environment.sim.mujoco、rewards.<项>）。
    渐进披露：深度 > 5 或末段为结构字段的叶子进 advanced。
    """
    prefixes = [prefix for prefix, cat in CATEGORY_BY_PREFIX if cat == category]
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def walk(node: Any, path: str, depth: int) -> None:
        if isinstance(node, dict):
            # 决定分组节点名：奖励/终止/事件按项分组，其余按模块分组
            parts = path.split(".")
            if path.startswith("environment.rewards.") and len(parts) >= 3:
                group_node = f"environment.rewards.{parts[2]}"
            elif path.startswith("environment.events.") and len(parts) >= 3:
                group_node = f"environment.events.{parts[2]}"
            elif path.startswith("environment.terminations.") and len(parts) >= 3:
                group_node = f"environment.terminations.{parts[2]}"
            elif path.startswith("environment.commands.") and len(parts) >= 3:
                group_node = f"environment.commands.{parts[2]}"
            elif path.startswith("environment.actions.") and len(parts) >= 3:
                group_node = f"environment.actions.{parts[2]}"
            else:
                group_node = path
            for key, value in node.items():
                if key == "__type__":
                    continue
                walk(value, f"{path}.{key}" if path else key, depth + 1)
            return

        # 叶子
        if is_structural(path):
            return
        # 找到该叶子所属的分组节点
        parts = path.split(".")
        if path.startswith("environment.rewards.") and len(parts) >= 3:
            group_node = f"environment.rewards.{parts[2]}"
        elif path.startswith("environment.events.") and len(parts) >= 3:
            group_node = f"environment.events.{parts[2]}"
        elif path.startswith("environment.terminations.") and len(parts) >= 3:
            group_node = f"environment.terminations.{parts[2]}"
        elif path.startswith("environment.commands.") and len(parts) >= 3:
            group_node = f"environment.commands.{parts[2]}"
        elif path.startswith("environment.actions.") and len(parts) >= 3:
            group_node = f"environment.actions.{parts[2]}"
        else:
            # 模块级分组：内省树第一/二层（sim.mujoco / scene / runner.algorithm ...）
            if path.startswith("environment."):
                rest = parts[1:]
                group_node = "environment." + ".".join(rest[:2]) if len(rest) >= 2 else path
            elif path.startswith("runner.algorithm"):
                group_node = "runner.algorithm"
            elif path.startswith("runner.model"):
                group_node = "runner.model"
            elif path.startswith("runner."):
                group_node = "runner"
            else:
                group_node = path

        from adapters.mjlab.param_catalog import label_for

        if group_node not in groups:
            groups[group_node] = {"title": label_for(group_node), "node": group_node, "params": []}
            order.append(group_node)
        groups[group_node]["params"].append({
            "id": path,
            "path": path,
            "label": label_for(path),
            "type": _leaf_type(node),
            "value": node,
            "advanced": depth > 6,
            "unit": None,
            "readonly": False,
        })

    # 只遍历该分类的子树
    for prefix in prefixes:
        node: Any = schema
        for part in [seg for seg in prefix.split(".") if seg]:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is None:
            continue
        walk(node, prefix.rstrip("."), 0)

    ordered = [{"title": groups[g]["title"], "node": g, "params": groups[g]["params"]}
               for g in order if g in groups]
    return ordered
