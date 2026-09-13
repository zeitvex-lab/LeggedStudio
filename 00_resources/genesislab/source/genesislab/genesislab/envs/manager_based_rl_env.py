"""Manager-based reinforcement learning environment for GenesisLab.

This module provides a thin, IsaacLab-style wrapper around
``ManagerBasedGenesisEnv`` that serves as the canonical RL environment base
class for manager-based workflows.

- ``ManagerBasedRlEnvCfg`` is a small specialization of
  :class:`genesislab.components.entities.env_cfg.ManagerBasedGenesisEnvCfg` with RL-centric
  documentation.
- ``ManagerBasedRlEnv`` subclasses :class:`ManagerBasedGenesisEnv` and keeps
  the same reset/step semantics as used throughout GenesisLab.
"""

from __future__ import annotations

import importlib
from typing import Any

import torch

from genesislab.envs.common import VecEnvObs, VecEnvStepReturn
from genesislab.envs.manager_based_genesis_env import ManagerBasedGenesisEnv, ManagerBasedGenesisEnvCfg
from genesislab.managers import CurriculumManager, NullCurriculumManager
from genesislab.utils.configclass import configclass
from genesislab.utils.timing import timed_block


class ManagerBasedRlEnv(ManagerBasedGenesisEnv):
    """Manager-based RL environment for Genesis.

    This class is a thin alias over :class:`ManagerBasedGenesisEnv` that
    emphasizes RL usage (rewards/terminations) and exposes the same
    vectorized API:

    - ``reset(seed, env_ids, options) -> (VecEnvObs, info)``
    - ``step(action) -> VecEnvStepReturn``
    """

    cfg: ManagerBasedRlEnvCfg
    """Configuration for the environment."""

    def __init__(
        self,
        cfg: ManagerBasedRlEnvCfg = None,
        device: str = "cuda",
        env_cfg_entry_point: str = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the manager-based RL environment.

        Args:
            cfg: RL environment configuration. If None, will be loaded from env_cfg_entry_point.
            device: Device to use for tensors ("cuda" or "cpu").
            env_cfg_entry_point: String entry point to load config from (format: "module:ClassName").
                Used when cfg is None. This allows gym.register to pass config via kwargs.
            **kwargs: Additional keyword arguments (reserved for future use or other configs).
        """
        super().__init__(cfg=cfg, device=device)

        # ------------------------------------------------------------------
        # Curriculum manager (optional) – only used for RL-style tasks.
        # Pattern aligned with mjlab / IsaacLab:
        #   - If curriculum config is empty → NullCurriculumManager
        #   - Otherwise → real CurriculumManager
        # ------------------------------------------------------------------
        curriculum_cfg = getattr(self.cfg, "curriculum", None)
        self.curriculum_manager = CurriculumManager(cfg=curriculum_cfg, env=self)
        print("[ManagerBasedRlEnv] Curriculum manager:", self.curriculum_manager)
        # Set a default render fps in metadata for viewers/wrappers.
        self.metadata["render_fps"] = 1.0 / self.step_dt

    # ----------------------------------------------------------------------
    # Core API overrides to integrate curriculum updates.
    # ----------------------------------------------------------------------

    def step(self, action: torch.Tensor) -> VecEnvStepReturn:
        """Step the environment with full RL semantics (rewards, terminations, curriculum).

        This overrides :meth:`ManagerBasedGenesisEnv.step` by:

        1. Using the shared simulation core (:meth:`_step_simulation`).
        2. Computing terminations and rewards via the respective managers.
        3. Resetting terminated environments with curriculum and events.
        4. Updating commands and interval events.
        5. Computing observations for the next step.
        """
        # Advance simulation (actions + physics + sensors + counters)
        self._step_simulation(action)

        # Compute terminations
        with timed_block("terminations.compute"):
            reset_buf = self.termination_manager.compute()
        reset_terminated = self.termination_manager.terminated
        reset_time_outs = self.termination_manager.time_outs

        # Compute rewards
        with timed_block("rewards.compute"):
            reward_buf = self.reward_manager.compute(dt=self.step_dt)

        # Reset terminated/timed-out environments and collect any episode metrics.
        reset_env_ids = reset_buf.nonzero(as_tuple=False).squeeze(-1)
        manager_extras: dict[str, Any] = {}
        if len(reset_env_ids) > 0:
            maybe_extras = self._reset_idx(reset_env_ids)
            if isinstance(maybe_extras, dict):
                manager_extras.update(maybe_extras)

        # Update commands
        with timed_block("commands.compute"):
            self.command_manager.compute(dt=self.step_dt)

        # Apply interval events if event manager is configured
        if hasattr(self, "event_manager") and self.event_manager is not None:
            if "interval" in self.event_manager.available_modes:
                self.event_manager.apply(mode="interval", dt=self.step_dt)

        # Debug visualization (if enabled)
        if hasattr(self, "command_manager") and self.command_manager is not None:
            self.command_manager.debug_vis(self._scene.gs_scene)

        # Compute observations
        with timed_block("observations.compute"):
            obs_buf = self.observation_manager.compute(update_history=True)

        # Build info dict, including any episode-level metrics produced at reset.
        info: dict[str, dict] = {
            "time_outs": reset_time_outs,
            "terminated": reset_terminated,
            "log": manager_extras,
        }

        return obs_buf, reward_buf, reset_terminated, reset_time_outs, info

    def reset(
        self,
        seed: int = None,
        env_ids: torch.Tensor | list[int] | tuple[int, ...] = None,
        options: dict[str, Any] = None,
    ) -> tuple[VecEnvObs, dict[str, Any]]:
        """Reset the environment with curriculum support.

        This mirrors :meth:`ManagerBasedGenesisEnv.reset` but additionally:

        1. Updates curriculum state before resets via :meth:`curriculum_manager.compute`.
        2. Logs curriculum quantities via :meth:`curriculum_manager.reset`.
        """
        del options  # Currently unused, kept for Gymnasium compatibility.

        # Re-seed if provided
        if seed is not None: self.seed(seed)

        # Determine which environments to reset
        if env_ids is None:
            env_ids = torch.arange(self.num_envs, device=self.device)
        elif isinstance(env_ids, (list, tuple)):
            env_ids = torch.tensor(env_ids, dtype=torch.long, device=self.device)

        # Delegate to the RL-specific indexed reset, which also handles curriculum.
        manager_extras = self._reset_idx(env_ids)

        # Compute initial observations
        obs_buf = self.observation_manager.compute(update_history=True)

        # Expose manager extras at top level (Episode_Reward, Metrics, Curriculum, ...).
        info = dict(manager_extras)
        return obs_buf, info

    def _reset_idx(self, env_ids: torch.Tensor) -> dict[str, Any]:
        """Reset specific environments with curriculum support.

        This extends :meth:`ManagerBasedGenesisEnv._reset_idx` by:

        1. Updating curriculum state for the environments being reset.
        2. Logging curriculum quantities via :meth:`curriculum_manager.reset`.
        """
        # Update curriculum state before resetting environments.
        self.curriculum_manager.compute(env_ids=env_ids)

        # Reset scene, do not use original reset
        # self._scene.controller.reset(env_ids=env_ids)

        # Reset episode counters
        self.episode_length_buf[env_ids] = 0

        # Apply reset events if event manager is configured
        if hasattr(self, "event_manager") and self.event_manager is not None:
            if "reset" in self.event_manager.available_modes:
                self.event_manager.apply(mode="reset", env_ids=env_ids, global_env_step_count=self.common_step_counter)

        # Reset managers and collect extras.
        manager_extras: dict[str, Any] = {}
        manager_extras.update(self.action_manager.reset(env_ids=env_ids))
        manager_extras.update(self.observation_manager.reset(env_ids=env_ids))
        manager_extras.update(self.reward_manager.reset(env_ids=env_ids))
        manager_extras.update(self.termination_manager.reset(env_ids=env_ids))
        manager_extras.update(self.command_manager.reset(env_ids=env_ids))
        manager_extras.update(self.curriculum_manager.reset(env_ids=env_ids))
        
        # Reset event manager and collect extras
        if hasattr(self, "event_manager") and self.event_manager is not None:
            event_extras = self.event_manager.reset(env_ids=env_ids)
            manager_extras.update(event_extras)

        return manager_extras

@configclass
class ManagerBasedRlEnvCfg(ManagerBasedGenesisEnvCfg):
    """Configuration for a manager-based RL environment on Genesis.

    This class extends :class:`ManagerBasedGenesisEnvCfg` with RL-centric
    documentation and semantics similar to IsaacLab's ``ManagerBasedRLEnvCfg``.
    
    Key fields (overriding the generic base documentation):
    
    - ``episode_length_s``: duration of an episode in seconds. Together with
      ``decimation`` and ``scene.dt`` this defines the maximum number of env
      steps per episode.
    - ``is_finite_horizon``: whether the learning problem is treated as finite
      or infinite horizon. The base env uses this flag to distinguish between
      terminated vs. time-out steps; RL libraries may interpret truncated
      signals differently based on this.
    - ``rewards``: configuration object or mapping for :class:`RewardManager`.
    - ``terminations``: configuration object or mapping for
      :class:`TerminationManager`.
    - ``curriculum``: optional configuration for :class:`CurriculumManager`.
      If ``None``, curriculum is disabled and a :class:`NullCurriculumManager`
      is used.
    - ``commands``: optional configuration for :class:`CommandManager`. If
      ``None``, a :class:`NullCommandManager` is used.
    """

    # Re-declare RL-related fields with RL-focused docstrings while keeping
    # defaults aligned with the base config.
    episode_length_s: float = None
    is_finite_horizon: bool = False

    rewards: object = {}
    terminations: object = {}
    curriculum: object = None
    commands: object = None