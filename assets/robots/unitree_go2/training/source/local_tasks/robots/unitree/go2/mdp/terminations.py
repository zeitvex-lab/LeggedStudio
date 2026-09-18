"""Go2 termination terms layered on mjlab's velocity primitives.

结构层攻关（任务清单 §2.1 序 1）：go2 64×800 长训后期「episode 贴顶低速游走」
策略以高功率低效步态耗满 20s episode（B11 侧 |tau*v| RMS≈700，dof_power 记 0），
拖垮质量分。除了奖励塑形（V1，mdp/rewards.py::go2_dof_power_penalty），本模块
提供功率超限 early-termination（V2）：超限即截断 episode（非 time_out，计为
failure，无 bootstrap），让"低效游走耗时间"不再是无代价策略。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

if TYPE_CHECKING:
  from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def go2_power_runaway(
  env: ManagerBasedRlEnv,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
  peak_power_limit: float = 1500.0,
  mean_power_limit: float = 900.0,
  mean_alpha: float = 0.9,
) -> torch.Tensor:
  """Terminate the episode when per-joint mechanical power runs away.

  口径与评测对齐（adapters/mjlab/quality_metrics.py::dof_power，只读参照）：
  功率 = |actuator_force * joint_vel|（go2 执行器与关节 1:1 同序）。两条触发线：

  * 瞬时峰值：任一关节 |tau*v| > ``peak_power_limit``（默认 1500，约 2× 评测
    RMS 700 的量级，捕捉冲击型尖峰）；
  * 持续均值：逐关节均值的 EMA（``mean_alpha``≈0.9，有效窗口 ~10 个策略步
    ≈0.4s）> ``mean_power_limit``（默认 900，捕捉"持续高功率游走"）。

  EMA 状态按 env 重置逐环境清零（``episode_length_buf <= 1``），跨 reset 不串。
  阈值标定记录见 tools/baselines/reward_shaping_experiments.json v2 段。
  """
  asset: Entity = env.scene[asset_cfg.name]
  force = asset.data.actuator_force[:, asset_cfg.joint_ids]
  velocity = asset.data.joint_vel[:, asset_cfg.joint_ids]
  power = (force * velocity).abs()
  peak = power.max(dim=-1).values
  step_mean = power.mean(dim=-1)
  first_step = env.episode_length_buf <= 1
  previous = getattr(env, "_go2_power_runaway_mean", None)
  if previous is None or previous.shape != step_mean.shape:
    previous = torch.zeros_like(step_mean)
  previous = torch.where(first_step, torch.zeros_like(previous), previous)
  run_mean = previous * mean_alpha + step_mean * (1.0 - mean_alpha)
  env.__dict__["_go2_power_runaway_mean"] = run_mean
  return (peak > peak_power_limit) | (run_mean > mean_power_limit)
