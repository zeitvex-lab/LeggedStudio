"""Shared position/velocity actions in policy-interface order, not model order."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby

from mjlab.envs.mdp.actions import (
    JointPositionAction, JointPositionActionCfg,
    JointVelocityAction, JointVelocityActionCfg,
)
from mjlab.utils.lab_api.string import resolve_matching_names


class OrderedTargets:
    """接口序混入：把 mjlab 动作项的解析目标序恢复成 cfg 声明的序。

    用途不止本模块的两个基类：族级技能里"按源配方换掉动作项实现"的变体
    （`skills/mdp/actions.DelayedJointPositionAction`）也要它 —— 否则"换实现"会
    静默把动作维退回**模型序**，与契约 `action.joint_order` 错位。
    """

    def _find_targets(self, cfg):
        # MJLab's joint branch currently ignores BaseActionCfg.preserve_order.
        # Retain its actuated-target validation, then restore the requested order.
        ids, names = super()._find_targets(cfg)
        order, ordered_names = resolve_matching_names(
            cfg.actuator_names, names, preserve_order=cfg.preserve_order)
        return [ids[i] for i in order], ordered_names


class _OrderedPositionAction(OrderedTargets, JointPositionAction):
    pass


class _OrderedVelocityAction(OrderedTargets, JointVelocityAction):
    pass


@dataclass(kw_only=True)
class OrderedJointPositionActionCfg(JointPositionActionCfg):
    def build(self, env):
        return _OrderedPositionAction(self, env)


@dataclass(kw_only=True)
class OrderedJointVelocityActionCfg(JointVelocityActionCfg):
    def build(self, env):
        return _OrderedVelocityAction(self, env)


def build_joint_actions(
    *, joint_order: Sequence[str], control_modes: Mapping[str, str],
    scale: float | Mapping[str, float], term_names: Sequence[str] | None = None,
) -> dict[str, JointPositionActionCfg | JointVelocityActionCfg]:
    """Split contiguous modes without permuting the action vector.

    Modes are explicit position/velocity targets, not low-level actuator types.
    Scale is a scalar or a complete mapping of literal joint names. Optional
    term_names preserves a profile's public action names, one per segment.
    """
    for joint in joint_order:
        if control_modes.get(joint) not in ("position", "velocity"):
            raise ValueError(f"Unsupported control mode for {joint!r}: {control_modes.get(joint)!r}")
    segments = [(mode, tuple(joints)) for mode, joints in
                groupby(joint_order, key=control_modes.__getitem__)]
    if term_names is not None and (len(term_names) != len(segments) or
                                   len(set(term_names)) != len(term_names)):
        raise ValueError("term_names must have one unique name per action segment")
    actions = {}
    counts: dict[str, int] = {}
    for index, (mode, joints) in enumerate(segments):
        segment_scale = scale
        if isinstance(scale, Mapping):
            segment_scale = {joint: float(scale[joint]) for joint in joints}
            values = list(segment_scale.values())
            if len(set(values)) == 1:
                segment_scale = values[0]
        counts[mode] = counts.get(mode, 0) + 1
        base = "joint_pos" if mode == "position" else "joint_vel"
        name = base if counts[mode] == 1 else f"{base}_{counts[mode]}"
        if term_names is not None:
            name = term_names[index]
        cfg_type = OrderedJointPositionActionCfg if mode == "position" else OrderedJointVelocityActionCfg
        actions[name] = cfg_type(
            entity_name="robot", actuator_names=joints, preserve_order=True,
            scale=segment_scale, offset=0.0, use_default_offset=mode == "position")
    return actions
