"""E6：专家模式 dot-path —— **任意参数可改，但越界/只读必须当场拒**。

## 为什么不能只"透传"

`overrides` 此前只是被放进配置（`CreateTrainingRequest.overrides`）随请求透传，控制面**不校验**：

* 路径拼错 → 没人报（要么静默无效、要么 worker 稍后才炸）；
* 改到只读项（物理/契约类）→ 同样静默，于是"我改了但没生效"会再演一次 ——
  这正是本仓反复踩的形态：**看起来生效、实际不生效**。

所以专家的逃生门要**带护栏**：任意参数可改（判据原文），但**未知路径**与**只读项**必须拒，
并给出最接近的可改路径 —— "不能改"要说清"那能改什么"。

## 目录即真值

参数目录来自 `adapters.mjlab.param_descriptors.resolve_params(schema)`（每项带
`path` / `label` / `type` / `readonly` / `category` / `value`）。**不另造白名单**：
白名单一旦与目录分叉，就会出现"页面能改、后端说未知"这种最难查的不一致。
"""

from __future__ import annotations

import difflib
import json
from typing import Any, Iterable, Mapping

#: 目录里"不可精确寻址"的路径（模式/通配/正则）——它们代表**一类**关节，
#: 只能整体改（或走结构化字段），不能当点路径用。
_PATTERN_CHARS = ("*", "?", "[", "]", "(", ")", "+", "^", "$", "|", "\\")

#: **静态只读键**（末段名 → 原因）。用途：参数目录**缓存冷**时也能拒掉"改物理"的尝试 ——
#: "物理真值属于契约"这条事实**不依赖目录**；目录只是更细（能报到具体路径）。
#: 优先级：目录条目（权威）> 本表（兜底）。
STATIC_READONLY: dict[str, str] = {
    "physics_hz": "由机器人契约决定（训练资产页 02 维护）",
    "control_hz": "由机器人契约决定（训练资产页 02 维护）",
    "decimation": "由机器人契约决定（训练资产页 02 维护）",
    "timestep": "由机器人契约决定（物理真值只在契约 + MJCF 一处）",
    "stiffness": "由机器人契约决定（PD 增益真值在契约 + MJCF；改这里不生效）",
    "damping": "由机器人契约决定（PD 增益真值在契约 + MJCF；改这里不生效）",
    "armature": "由机器人契约决定（物理真值只在契约 + MJCF 一处）",
    "frictionloss": "由机器人契约决定（物理真值只在契约 + MJCF 一处）",
    "joint_order": "由机器人契约决定（动作槽位与关节的对应关系）",
    "default_pose": "由机器人契约决定",
    "terrain_mixes": "由训练配方源码决定",
    "curriculum": "由训练配方源码决定",
    "hidden_dims": "由训练配方源码决定（runner 默认）",
    "activation": "由训练配方源码决定（runner 默认）",
    "obs_normalization": "由训练配方源码决定（runner 默认）",
    "domain_randomization": "由训练配方源码决定",
}


def is_addressable(path: str) -> bool:
    """这条目录路径能否用点路径精确寻址。"""
    return bool(path) and not any(char in path for char in _PATTERN_CHARS)


def catalog_index(catalog: Iterable[Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """把参数目录变成 ``path → entry``。"""
    index: dict[str, dict[str, Any]] = {}
    for entry in catalog or []:
        path = str(entry.get("path") or "").strip()
        if path:
            index[path] = dict(entry)
    return index


def coerce_value(raw: Any, type_name: str) -> tuple[Any, str | None]:
    """按目录声明的类型转换输入值；**转不了就报错，不猜**（返回 ``(值, 错误)``）。"""
    kind = (type_name or "").strip().lower()
    if kind in ("", "any", "auto"):
        return raw, None
    if kind in ("bool", "boolean"):
        if isinstance(raw, bool):
            return raw, None
        text = str(raw).strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True, None
        if text in ("false", "0", "no", "off"):
            return False, None
        return None, f"bool 类型无法解析 {raw!r}（可用 true/false）"
    if kind in ("int", "integer"):
        try:
            return int(float(raw)), None          # 允许 "3.0" 这种数字串
        except (TypeError, ValueError):
            return None, f"int 类型无法解析 {raw!r}"
    if kind in ("float", "number", "double"):
        try:
            return float(raw), None
        except (TypeError, ValueError):
            return None, f"float 类型无法解析 {raw!r}"
    if kind in ("str", "string", "text"):
        if isinstance(raw, str):
            return raw, None
        return None, f"str 类型需要字符串（得到 {type(raw).__name__}）"
    if kind.startswith(("list", "array", "tuple")) or kind.startswith(("dict", "object", "map")):
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return None, f"{kind} 类型需要数组/对象（JSON 也解析失败：{raw!r}）"
            return parsed, None
        return raw, None
    return raw, None                              # 未登记的类型原样放行，不编规则


def validate_edits(
    edits: Mapping[str, Any] | None,
    *,
    catalog: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """校验一批点路径覆盖。**返回结论，不抛异常**。

    ``ok=False`` 时调用方应**整批拒绝**（不是"应用一半"）—— 专家模式里最危险的结果
    正是"一部分生效、一部分被静默丢掉，然后人以为全生效了"。
    """
    index = catalog_index(catalog)
    known = sorted(path for path in index if is_addressable(path))
    applied: dict[str, Any] = {}
    details: list[dict[str, Any]] = []
    problems: list[str] = []

    for raw_path, raw_value in (edits or {}).items():
        path = str(raw_path or "").strip()
        if not path:
            problems.append("存在空路径的覆盖项")
            continue
        entry = index.get(path)
        if entry is None or not is_addressable(path):
            leaf = path.rsplit(".", 1)[-1].strip().lower()
            if entry is None and leaf in STATIC_READONLY:
                problems.append(
                    f"{path}: **只读**（{STATIC_READONLY[leaf]}）—— 改在这里不会生效",
                )
                continue
            near = difflib.get_close_matches(path, known, n=1, cutoff=0.5)
            hint = f"；最接近的可改路径：{near[0]}" if near else "；可改路径见参数目录（/api/training/schema 的 params）"
            problems.append(f"{path}: 目录里没有这一项（未知或被模式化的路径）{hint}")
            continue
        if entry.get("readonly"):
            reason = entry.get("reason") or entry.get("readonly_reason") or "由契约或配方源码决定"
            problems.append(f"{path}: **只读**（{reason}）—— 它属于物理/机器人契约，改在这里不会生效")
            continue
        value, error = coerce_value(raw_value, str(entry.get("type") or ""))
        if error:
            problems.append(f"{path}: {error}")
            continue
        applied[path] = value
        details.append({
            "path": path,
            "label": entry.get("label"),
            "category": entry.get("category"),
            "unit": entry.get("unit"),
            "value": value,
            "before": entry.get("value"),
        })

    return {
        "ok": not problems,
        "applied": applied,
        "details": details,
        "problems": problems,
        "catalog_size": len(index),
        "addressable": len(known),
    }


def apply_to_config(config: Mapping[str, Any], applied: Mapping[str, Any]) -> dict[str, Any]:
    """把已校验的覆盖写进配置副本（**不修改入参**）；中间层不存在就建出来。"""
    merged: dict[str, Any] = json.loads(json.dumps(dict(config)))
    for path, value in (applied or {}).items():
        node = merged
        parts = [part for part in str(path).split(".") if part]
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        if parts:
            node[parts[-1]] = value
    return merged
