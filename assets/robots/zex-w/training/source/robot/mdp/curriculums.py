"""Adaptive command curriculum based on tracking reward performance."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
import torch

from mjlab.managers.curriculum_manager import CurriculumTermCfg
# 注：``Entity`` / ``SceneEntityCfg`` 原先只为地形级课程函数而 import，随函数上移一并移除
# （地形课程的四函数现在从 Kit 再导出，见文末）。

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


class adaptive_command_vel:
    """Expand velocity command ranges dynamically when tracking performance exceeds threshold.

    Uses the reward manager's per-step reward buffer directly to compute the mean raw
    tracking reward (in [0, 1] for exponential-based rewards).
    """

    def __init__(self, cfg: CurriculumTermCfg, env: ManagerBasedRlEnv):
        from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

        p = cfg.params
        self._command_name: str = p["command_name"]
        self._reward_name: str = p["reward_name"]
        self._upper_threshold: float = p.get("upper_threshold", 0.8)
        self._lower_threshold: float = p.get("lower_threshold", 0.4)
        self._delta: float = p.get("delta", 0.2)
        self._max_lin_vel_x: tuple = tuple(p.get("max_lin_vel_x", (-1.0, 1.0)))
        self._max_lin_vel_y: tuple = tuple(p.get("max_lin_vel_y", (-0.5, 0.5)))
        self._max_ang_vel_z: tuple = tuple(p.get("max_ang_vel_z", (-1.0, 1.0)))
        self._min_range: float = 0.3

        command_term = env.command_manager.get_term(self._command_name)
        self._cfg = cast(UniformVelocityCommandCfg, command_term.cfg)

        # Locate the index of the target reward term
        self._reward_idx = list(env.reward_manager._term_names).index(self._reward_name)
        self._reward_weight = env.reward_manager.get_term_cfg(self._reward_name).weight

        # Exponential moving average (EMA) smoothing to prevent oscillations
        self._ema = 0.5
        self._running_mean = 0.0

    def __call__(
        self,
        env: ManagerBasedRlEnv,
        env_ids: torch.Tensor,
        **kwargs,
    ) -> dict[str, torch.Tensor]:
        # Retrieve raw step rewards from step_reward buffer
        # step_reward[:, idx] = raw * weight (already scaled by dt)
        step_rewards = env.reward_manager._step_reward[:, self._reward_idx]
        # raw = step_reward / weight -> [0, 1] for exponential rewards
        mean_raw = (torch.mean(step_rewards) / self._reward_weight).item()

        # Apply EMA smoothing to prevent jitter
        self._running_mean = self._ema * mean_raw + (1 - self._ema) * self._running_mean

        if self._running_mean > self._upper_threshold:
            self._expand()
        elif self._running_mean < self._lower_threshold:
            self._shrink()

        return self._log()

    def _expand(self):
        lo, hi = self._cfg.ranges.lin_vel_x
        self._cfg.ranges.lin_vel_x = (
            max(lo - self._delta, self._max_lin_vel_x[0]),
            min(hi + self._delta, self._max_lin_vel_x[1]),
        )
        lo, hi = self._cfg.ranges.lin_vel_y
        self._cfg.ranges.lin_vel_y = (
            max(lo - self._delta * 0.5, self._max_lin_vel_y[0]),
            min(hi + self._delta * 0.5, self._max_lin_vel_y[1]),
        )
        lo, hi = self._cfg.ranges.ang_vel_z
        self._cfg.ranges.ang_vel_z = (
            max(lo - self._delta, self._max_ang_vel_z[0]),
            min(hi + self._delta, self._max_ang_vel_z[1]),
        )

    def _shrink(self):
        lo, hi = self._cfg.ranges.lin_vel_x
        new_lo = min(lo + self._delta, -self._min_range)
        new_hi = max(hi - self._delta, self._min_range)
        if new_hi - new_lo >= 2 * self._min_range:
            self._cfg.ranges.lin_vel_x = (new_lo, new_hi)

    def _log(self) -> dict[str, torch.Tensor]:
        return {
            "lin_vel_x_min": torch.tensor(self._cfg.ranges.lin_vel_x[0]),
            "lin_vel_x_max": torch.tensor(self._cfg.ranges.lin_vel_x[1]),
            "ang_vel_z_max": torch.tensor(self._cfg.ranges.ang_vel_z[1]),
        }


class command_axis_levels_vel:
    """Linearly expand one command axis over training steps."""

    def __init__(self, cfg: CurriculumTermCfg, env: ManagerBasedRlEnv):
        from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

        p = cfg.params
        self._command_name: str = p.get("command_name", "twist")
        self._reward_name: str = p["reward_term_name"]
        self._axis: str = p["axis"]
        self._range_multiplier: tuple[float, float] = tuple(p.get("range_multiplier", (0.4, 1.0)))
        self._initial_range_param: tuple[float, float] | None = (
            tuple(p["initial_range"]) if "initial_range" in p else None
        )
        self._ema_alpha: float = p.get("ema_alpha", 0.5)
        self._warmup_steps: int = p.get("warmup_steps", 0)
        self._ramp_steps: int = p.get("ramp_steps", 800 * 24)

        command_term = env.command_manager.get_term(self._command_name)
        self._cfg = cast(UniformVelocityCommandCfg, command_term.cfg)
        self._reward_idx = list(env.reward_manager._term_names).index(self._reward_name)
        self._reward_weight = env.reward_manager.get_term_cfg(self._reward_name).weight
        self._running_mean = 0.0

        self._full_range = self._get_range()
        self._min_range = self._initial_range_param or self._scaled_range(self._range_multiplier[0])
        self._set_range(self._min_range)

    def __call__(self, env: ManagerBasedRlEnv, env_ids: torch.Tensor, **kwargs) -> dict[str, torch.Tensor]:
        if len(env_ids) > 0:
            episode_sums = env.reward_manager._episode_sums[self._reward_name][env_ids]
            mean_raw = torch.mean(episode_sums / env.cfg.episode_length_s / self._reward_weight).item()
            self._running_mean = self._ema_alpha * mean_raw + (1.0 - self._ema_alpha) * self._running_mean
        self._set_range(self._current_max_range(env.common_step_counter))

        lo, hi = self._get_range()
        return {
            f"{self._axis}_range_min": torch.tensor(lo),
            f"{self._axis}_range_max": torch.tensor(hi),
            f"{self._axis}_tracking_ema": torch.tensor(self._running_mean),
            f"{self._axis}_warmup_active": torch.tensor(float(env.common_step_counter < self._warmup_steps)),
            f"{self._axis}_range_cap": torch.tensor(self._current_multiplier(env.common_step_counter)),
        }

    def _get_range(self) -> tuple[float, float]:
        if self._axis == "x":
            return tuple(self._cfg.ranges.lin_vel_x)
        if self._axis == "y":
            return tuple(self._cfg.ranges.lin_vel_y)
        if self._axis == "yaw":
            return tuple(self._cfg.ranges.ang_vel_z)
        raise ValueError(f"Unknown command curriculum axis: {self._axis}")

    def _set_range(self, value: tuple[float, float]) -> None:
        if self._axis == "x":
            self._cfg.ranges.lin_vel_x = value
        elif self._axis == "y":
            self._cfg.ranges.lin_vel_y = value
        elif self._axis == "yaw":
            self._cfg.ranges.ang_vel_z = value
        else:
            raise ValueError(f"Unknown command curriculum axis: {self._axis}")

    def _scaled_range(self, multiplier: float) -> tuple[float, float]:
        lo, hi = self._full_range
        return (lo * multiplier, hi * multiplier)

    def _current_multiplier(self, step: int) -> float:
        start, end = self._range_multiplier
        if self._ramp_steps <= 0:
            return end
        progress = max(0.0, min(1.0, (step - self._warmup_steps) / self._ramp_steps))
        return start + (end - start) * progress

    def _current_max_range(self, step: int) -> tuple[float, float]:
        if self._initial_range_param is None:
            return self._scaled_range(self._current_multiplier(step))
        progress = self._current_progress(step)
        lo = self._min_range[0] + (self._full_range[0] - self._min_range[0]) * progress
        hi = self._min_range[1] + (self._full_range[1] - self._min_range[1]) * progress
        return (lo, hi)

    def _current_progress(self, step: int) -> float:
        if self._ramp_steps <= 0:
            return 1.0
        return max(0.0, min(1.0, (step - self._warmup_steps) / self._ramp_steps))


class command_levels_adaptive:
    """Adaptive command range curriculum based on average tracking performance."""

    def __init__(self, cfg: CurriculumTermCfg, env: ManagerBasedRlEnv):
        p = cfg.params
        self._command_name: str = p.get("command_name", "twist")
        self._reward_name: str = p["reward_term_name"]
        self._axis: str = p["axis"]
        self._delta_command: float = p.get("delta_command", 0.05)
        self._target_ratio: float = p.get("target_ratio", 0.8)
        self._ema_alpha: float = p.get("ema_alpha", 0.5)

        command_term = env.command_manager.get_term(self._command_name)
        self._cfg = command_term.cfg
        self._reward_weight = env.reward_manager.get_term_cfg(self._reward_name).weight
        self._running_mean = 0.0

        # Read the full range configured in the environment configuration
        self._full_range = self._get_range()

        # Set the command range to initial range at the start
        self._initial_range = list(p["initial_range"])  # e.g. [-0.5, 0.5]
        self._current_range = list(self._initial_range)
        self._set_range(self._current_range)

    def __call__(self, env: ManagerBasedRlEnv, env_ids: torch.Tensor, **kwargs) -> dict[str, torch.Tensor]:
        if len(env_ids) > 0:
            episode_sums = env.reward_manager._episode_sums[self._reward_name][env_ids]
            mean_raw = torch.mean(episode_sums / env.cfg.episode_length_s / self._reward_weight).item()
            self._running_mean = self._ema_alpha * mean_raw + (1.0 - self._ema_alpha) * self._running_mean

        # Check performance at the end of every episode (or every max_episode_length_s)
        episode_length_steps = int(env.cfg.episode_length_s / env.step_dt)
        if env.common_step_counter > 0 and env.common_step_counter % episode_length_steps == 0:
            # If performance exceeds target ratio (e.g., 0.8), widen the range
            if self._running_mean > self._target_ratio:
                # Widen the range
                lo, hi = self._current_range
                new_lo = max(self._full_range[0], lo - self._delta_command)
                new_hi = min(self._full_range[1], hi + self._delta_command)
                self._current_range = [new_lo, new_hi]
                self._set_range(self._current_range)

        lo, hi = self._current_range
        return {
            f"{self._axis}_range_min": torch.tensor(lo),
            f"{self._axis}_range_max": torch.tensor(hi),
            f"{self._axis}_tracking_ema": torch.tensor(self._running_mean),
            f"{self._axis}_target_ratio": torch.tensor(self._target_ratio),
        }

    def _get_range(self) -> tuple[float, float]:
        if self._axis == "x":
            return tuple(self._cfg.ranges.lin_vel_x)
        if self._axis == "y":
            return tuple(self._cfg.ranges.lin_vel_y)
        if self._axis == "yaw":
            return tuple(self._cfg.ranges.ang_vel_z)
        raise ValueError(f"Unknown command curriculum axis: {self._axis}")

    def _set_range(self, value: list[float]) -> None:
        if self._axis == "x":
            self._cfg.ranges.lin_vel_x = tuple(value)
        elif self._axis == "y":
            self._cfg.ranges.lin_vel_y = tuple(value)
        elif self._axis == "yaw":
            self._cfg.ranges.ang_vel_z = tuple(value)
        else:
            raise ValueError(f"Unknown command curriculum axis: {self._axis}")


# ------------------------------------------------------------------------------
# 越障技能族级化（2026-09-25）：以下四个**地形级课程**函数原先在本文件自带正文，
# 已**逐字上移**为 ``adapters/mjlab/kits/wheel_leg_kit/mdp/terrain_curriculums.py``
# （唯一真值，轮足族级；含障碍释放课程 ``terrain_levels_obstacle_release``）。
# 这里保名再导出 —— ``from ..mdp.curriculums import terrain_levels_obstacle_release``
# 等入口与函数对象不变，env_cfgs 与档案行为等价。
#
# 命令课程（adaptive_command_vel / command_axis_levels_vel / command_levels_adaptive）
# 属任务特有调参，仍留包。
# ------------------------------------------------------------------------------

import sys as _sys
from pathlib import Path as _Path

for _parent in _Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in _sys.path:
            _sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.wheel_leg_kit.mdp.terrain_curriculums import (  # noqa: E402, F401
    terrain_levels_flat_warmup,
    terrain_levels_obstacle_release,
    terrain_levels_ramp_strict,
    terrain_levels_vel_strict,
)
