"""Observatuib field-level convergence adapter (PolicyContract -> v3 observation).

Goal (architecture debt #6 / report 1 §3):
    `local_tasks/core/policy_contract.py` 携带高质量的字段级观测表述
    (name + width + history_length + normalization)，但此前仅 Go2/G1 两个
    包内使用，未并入 `robot-contract-3.0.schema.json` 的 `observation`。

本模块提供一个**无 torch 依赖**的收敛适配层：
    - 把 PolicyContract 的 `observation_fields` / `history_*` 转成 v3 的
      `observation.components` + `history_*` 元数据；
    - 校验 `Σ(components.width) == observation.dimension`（与 role_resolver
      的自洽校验同口径）；
    - 提供 `normalize_observation` 作为 schema 字段级表述收敛后的统一入口。

刻意保持只依赖标准库 + contracts 的轻量模型，供控制面/CI 在无训练栈
环境单测，且不复用会拉入 torch 的 `local_tasks` 训练栈导入链。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 允许的观测来源（与 v3 schema `$defs/observation` 的 enum 对齐）
_SOURCE_ENUM = ("imu", "cmd", "actuated", "action", "world", "external")
_HISTORY_ORDER_ENUM = ("oldest_to_newest", "newest_to_oldest")
_HISTORY_RESET_ENUM = ("zero", "repeat")


class ObservationConvergenceError(ValueError):
    """观测收敛过程中的不变量违背。"""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """一个字段级观测表述（对齐 PolicyContract.ObservationField）。"""

    name: str
    width: int
    source: str = "actuated"
    scale: float = 1.0
    wrap: bool | None = None


@dataclass(frozen=True, slots=True)
class ObservationConvergence:
    """收敛后的字段级观测表述（可序列化为 v3 observation 的 components+history）。"""

    components: tuple[FieldSpec, ...] = ()
    dimension: int = 0
    history_length: int = 1
    history_order: str = "oldest_to_newest"
    history_reset: str = "zero"
    normalizer: dict[str, Any] | None = None

    @property
    def summary_width(self) -> int:
        return sum(field.width for field in self.components)


def normalize_source(source: str | None) -> str:
    """把来源归一化到 v3 enum；未知来源落回 'external'。"""
    if source in _SOURCE_ENUM:
        return source
    return "external"


def align_observation_fields(
    fields: list[FieldSpec] | list[dict[str, Any]],
    *,
    dimension: int | None = None,
    history_length: int = 1,
    history_order: str = "oldest_to_newest",
    history_reset: str = "zero",
    normalizer: dict[str, Any] | None = None,
) -> ObservationConvergence:
    """把字段级观测表述收敛为 ObservationConvergence，并校验维度自洽。

    Args:
        fields: 有序观测字段（每项至少含 name/width，可含 source/scale/wrap）。
        dimension: 期望的策略输入维度；None = 由 Σwidth 推断。
        history_length: 观测历史帧数（1 = 无历史）。
        history_order / history_reset: 历史帧元数据（对齐 PolicyContract）。

    Raises:
        ObservationConvergenceError: 名称重复 / 维度不匹配 / 历史元数据非法。
    """
    if history_length < 0:
        raise ObservationConvergenceError("history_length cannot be negative")
    if history_order not in _HISTORY_ORDER_ENUM:
        raise ObservationConvergenceError(f"invalid history_order: {history_order!r}")
    if history_reset not in _HISTORY_RESET_ENUM:
        raise ObservationConvergenceError(f"invalid history_reset: {history_reset!r}")

    comps: list[FieldSpec] = []
    names: set[str] = set()
    for item in fields:
        if isinstance(item, dict):
            name = str(item.get("name", ""))
            width = int(item.get("width", 0))
            source = normalize_source(item.get("source"))
            scale = float(item.get("scale", 1.0))
            wrap = item.get("wrap")
        else:
            name, width = item.name, item.width
            source = normalize_source(getattr(item, "source", None))
            scale = float(getattr(item, "scale", 1.0))
            wrap = getattr(item, "wrap", None)
        if not name:
            raise ObservationConvergenceError("observation field name cannot be empty")
        if width <= 0:
            raise ObservationConvergenceError(
                f"observation field width must be positive: {name!r}"
            )
        if name in names:
            raise ObservationConvergenceError(f"duplicate observation field: {name!r}")
        names.add(name)
        comps.append(FieldSpec(name=name, width=width, source=source, scale=scale, wrap=wrap))

    total = sum(comp.width for comp in comps)
    resolved_dim = dimension if dimension is not None else total
    if dimension is not None and dimension != total:
        raise ObservationConvergenceError(
            f"observation.dimension={dimension} != Σcomponents.width={total}"
        )

    return ObservationConvergence(
        components=tuple(comps),
        dimension=resolved_dim,
        history_length=history_length,
        history_order=history_order,
        history_reset=history_reset,
        normalizer=normalizer,
    )


def validate_v3_observation(observation: dict[str, Any]) -> list[str]:
    """校验一份 v3 observation 字典的字段级表述自洽性，返回错误列表。

    这是 role_resolver `expand_observation` 之外对 components/history 的
    独立轻量校验，供契约收敛流程在无训练栈环境下调用。
    """
    errors: list[str] = []
    components = observation.get("components") or []
    names = [comp.get("name") for comp in components]
    if len(set(names)) != len(names):
        errors.append("observation.components 名称重复")

    total = 0
    for comp in components:
        width = comp.get("width")
        if not isinstance(width, int) or width <= 0:
            errors.append(f"observation.components[{comp.get('name')!r}] width 非法")
        else:
            total += width

    declared = observation.get("dimension")
    if declared is not None and declared != total and components:
        errors.append(
            f"observation.dimension={declared} != Σcomponents.width={total}"
        )

    history_length = observation.get("history_length")
    if history_length is not None and (not isinstance(history_length, int) or history_length < 0):
        errors.append("observation.history_length 非法")

    for key, enum_vals in (
        ("history_order", _HISTORY_ORDER_ENUM),
        ("history_reset", _HISTORY_RESET_ENUM),
    ):
        value = observation.get(key)
        if value is not None and value not in enum_vals:
            errors.append(f"observation.{key}={value!r} 非法（允许 {enum_vals}）")

    return errors
