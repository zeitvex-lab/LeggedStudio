"""Shared position/velocity actions in policy-interface order, not model order."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby

import math

import torch
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


class _LowPassMixin:
    """IIR 一阶低通混入（上游 rc_mjlab lowpass_actions.py 同款）。

    平滑策略输出的动作跳变——轮足 NaN 实证（go2w-traversal 750 轮尾步物理爆炸）的
    上游防线：zex-w 0.64 产物即由本实现训练。control_frequency = 控制频率（Hz），
    cut_off_frequency = 截止频率（Hz），alpha = 1 − exp(−2π·fc/fs)。
    """

    def _init_lowpass(self, control_frequency: float, cut_off_frequency: float) -> None:
        # 注意：必须在 super().__init__(cfg, env) **之后**调用（_raw_actions 由基类建）；
        # 频率参数由 cfg 显式传入，不读 self（cfg 字段在 super().__init__ 里才可见）。
        self._lp_control_hz = float(control_frequency)
        self._lp_cutoff_hz = float(cut_off_frequency)
        alpha = 1.0 - math.exp(
            -2.0 * math.pi * self._lp_cutoff_hz / self._lp_control_hz
        )
        self._lp_alpha = alpha
        self._lp_prev = torch.zeros_like(self._raw_actions)

    def _filter(self, actions: torch.Tensor) -> torch.Tensor:
        filtered = self._lp_alpha * actions + (1.0 - self._lp_alpha) * self._lp_prev
        self._lp_prev[:] = actions
        return filtered

    def reset(self, env_ids=None):
        self._lp_prev[env_ids] = 0.0
        super().reset(env_ids)


class _OrderedPositionLowPassAction(_LowPassMixin, _OrderedPositionAction):
    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self._init_lowpass(cfg.control_frequency, cfg.cut_off_frequency)

    def process_actions(self, actions):
        super().process_actions(self._filter(actions))


class _OrderedVelocityLowPassAction(_LowPassMixin, _OrderedVelocityAction):
    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self._init_lowpass(cfg.control_frequency, cfg.cut_off_frequency)

    def process_actions(self, actions):
        super().process_actions(self._filter(actions))


@dataclass(kw_only=True)
class OrderedJointPositionLowPassActionCfg(OrderedJointPositionActionCfg):
    control_frequency: float = 50.0
    cut_off_frequency: float = 5.0

    def build(self, env):
        return _OrderedPositionLowPassAction(self, env)


@dataclass(kw_only=True)
class OrderedJointVelocityLowPassActionCfg(OrderedJointVelocityActionCfg):
    control_frequency: float = 50.0
    cut_off_frequency: float = 15.0

    def build(self, env):
        return _OrderedVelocityLowPassAction(self, env)


def build_joint_actions(
    *, joint_order: Sequence[str], control_modes: Mapping[str, str],
    scale: float | Mapping[str, float], term_names: Sequence[str] | None = None,
    low_pass: bool = False, control_frequency: float = 50.0,
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
        if low_pass:
            cfg_type = (OrderedJointPositionLowPassActionCfg if mode == "position"
                        else OrderedJointVelocityLowPassActionCfg)
            actions[name] = cfg_type(
                entity_name="robot", actuator_names=joints, preserve_order=True,
                scale=segment_scale, offset=0.0, use_default_offset=mode == "position",
                control_frequency=control_frequency,
                cut_off_frequency=5.0 if mode == "position" else 15.0)
        else:
            cfg_type = OrderedJointPositionActionCfg if mode == "position" else OrderedJointVelocityActionCfg
            actions[name] = cfg_type(
                entity_name="robot", actuator_names=joints, preserve_order=True,
                scale=segment_scale, offset=0.0, use_default_offset=mode == "position")
    return actions
