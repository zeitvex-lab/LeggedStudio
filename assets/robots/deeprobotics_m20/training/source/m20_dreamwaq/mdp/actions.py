"""Episode-delayed leg-position action term (DreamWaQ command-latency DR).

The source applies a per-environment command latency of 0-3 simulation
substeps to the leg targets.  mjlab action terms update once per control step
(50 Hz), so the latency set is approximated on the control-step grid with a
0-1 step DelayBuffer (0-20 ms versus the source's 0-15 ms).
"""

from dataclasses import dataclass

import torch

from mjlab.envs.mdp.actions import JointPositionAction, JointPositionActionCfg
from mjlab.utils.buffers import DelayBuffer


class EpisodeDelayedJointPositionAction(JointPositionAction):
  """Per-environment action delay with reset-safe history backfill."""

  def __init__(self, cfg: "EpisodeDelayedJointPositionActionCfg", env) -> None:
    super().__init__(cfg, env)
    self._delay = DelayBuffer(
      min_lag=cfg.delay_min_lag,
      max_lag=cfg.delay_max_lag,
      batch_size=env.num_envs,
      device=env.device,
      per_env=True,
      update_period=cfg.delay_update_period,
      per_env_phase=False,
    )

  def apply_actions(self) -> None:
    self._delay.append(self._processed_actions)
    target = self._delay.compute()
    # Match the stock JointPositionAction encoder-bias compensation so the
    # biased encoder reading converges to the delayed commanded target.
    encoder_bias = self._entity.data.encoder_bias[:, self._target_ids]
    self._entity.set_joint_position_target(
      target - encoder_bias, joint_ids=self._target_ids
    )

  def reset(self, env_ids=None) -> None:
    super().reset(env_ids)
    self._delay.reset(batch_ids=env_ids)
    zeros = torch.zeros_like(self._processed_actions)
    if not self._delay.is_initialized:
      self._delay.append(zeros)
      return
    if env_ids is None:
      ids = torch.arange(self.num_envs, device=self.device)
    elif isinstance(env_ids, slice):
      ids = torch.arange(self.num_envs, device=self.device)[env_ids]
    else:
      ids = env_ids
    self._delay.backfill(zeros, ids)


@dataclass(kw_only=True)
class EpisodeDelayedJointPositionActionCfg(JointPositionActionCfg):
  delay_min_lag: int = 0
  delay_max_lag: int = 1
  delay_update_period: int = 2**30

  def build(self, env) -> EpisodeDelayedJointPositionAction:
    return EpisodeDelayedJointPositionAction(self, env)
