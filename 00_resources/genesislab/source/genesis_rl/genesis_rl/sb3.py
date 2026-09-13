"""Stable-Baselines3 vectorized environment wrapper for GenesisLab.

This module mirrors :mod:`isaaclab_rl.sb3` but is implemented against
GenesisLab's :class:`ManagerBasedRlEnv`.

Usage example
-------------

.. code-block:: python

    from genesis_rl.sb3 import Sb3VecEnvWrapper
    from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv, ManagerBasedRlEnvCfg

    cfg = ManagerBasedRlEnvCfg(...)
    env = ManagerBasedRlEnv(cfg, device="cuda:0")
    vec_env = Sb3VecEnvWrapper(env)
"""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn  # noqa: F401
from stable_baselines3.common.preprocessing import is_image_space, is_image_space_channels_first
from stable_baselines3.common.utils import constant_fn
from stable_baselines3.common.vec_env.base_vec_env import VecEnv, VecEnvObs, VecEnvStepReturn

from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv


def process_sb3_cfg(cfg: dict, num_envs: int) -> dict:
    """Convert simple YAML / dict config into SB3-ready configuration.

    This helper is a lightly adapted copy of IsaacLab's ``process_sb3_cfg``
    so that Genesis tasks can reuse the same style of configuration files.
    """

    def update_dict(hyperparams: dict[str, Any], depth: int) -> dict[str, Any]:
        for key, value in hyperparams.items():
            if isinstance(value, dict):
                update_dict(value, depth + 1)
            if isinstance(value, str):
                if value.startswith("nn."):
                    hyperparams[key] = getattr(nn, value[3:])
            if depth == 0:
                if key in ["learning_rate", "clip_range", "clip_range_vf"]:
                    if isinstance(value, str):
                        _, initial_value = value.split("_")
                        initial_value = float(initial_value)
                        hyperparams[key] = lambda progress_remaining: progress_remaining * initial_value
                    elif isinstance(value, (float, int)):
                        if value < 0:
                            # negative value: ignore (ex: for clipping)
                            continue
                        hyperparams[key] = constant_fn(float(value))
                    else:
                        raise ValueError(f"Invalid value for {key}: {hyperparams[key]}")

        # Convert to a desired batch_size (n_steps=2048 by default for SB3 PPO)
        if "n_minibatches" in hyperparams:
            hyperparams["batch_size"] = (hyperparams.get("n_steps", 2048) * num_envs) // hyperparams["n_minibatches"]
            del hyperparams["n_minibatches"]

        return hyperparams

    return update_dict(cfg, depth=0)


class Sb3VecEnvWrapper(VecEnv):
    """Wrap GenesisLab :class:`ManagerBasedRlEnv` as an SB3 ``VecEnv``.

    Conceptually this is identical to IsaacLab's ``Sb3VecEnvWrapper``:

    - Internally GenesisLab already runs many parallel sub-envs in one
      :class:`ManagerBasedRlEnv` instance.
    - SB3, however, expects something that implements its own ``VecEnv``
      interface.
    - This class holds a reference to the Genesis env, forwards calls, and
      converts observations, rewards and info dicts into SB3's conventions.
    """

    def __init__(self, env: ManagerBasedRlEnv, fast_variant: bool = True):
        # Basic type check – Genesis uses only ManagerBasedRlEnv for now.
        if not isinstance(env.unwrapped, ManagerBasedRlEnv) and not isinstance(env, ManagerBasedRlEnv):
            raise ValueError(
                "The environment must be an instance of ManagerBasedRlEnv. "
                f"Got type: {type(env)}"
            )

        self.env = env
        self.fast_variant = fast_variant

        # Common attributes used by SB3
        self.num_envs = self.unwrapped.num_envs
        self.sim_device = self.unwrapped.device
        self.render_mode = getattr(self.unwrapped, "render_mode", None)

        self.observation_processors: dict[str, callable] = {}
        self._process_spaces()

        # Episode statistics buffers
        self._ep_rew_buf = np.zeros(self.num_envs, dtype=np.float32)
        self._ep_len_buf = np.zeros(self.num_envs, dtype=np.int32)

    # --------------------------------------------------------------------- #
    # Introspection helpers
    # --------------------------------------------------------------------- #

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"<{type(self).__name__}{self.env}>"

    __repr__ = __str__

    @classmethod
    def class_name(cls) -> str:
        return cls.__name__

    @property
    def unwrapped(self) -> ManagerBasedRlEnv:
        """Return the base Genesis environment (underneath any wrappers)."""
        return self.env.unwrapped if hasattr(self.env, "unwrapped") else self.env

    # --------------------------------------------------------------------- #
    # Episode statistics
    # --------------------------------------------------------------------- #

    def get_episode_rewards(self) -> list[float]:
        return self._ep_rew_buf.tolist()

    def get_episode_lengths(self) -> list[int]:
        return self._ep_len_buf.tolist()

    # --------------------------------------------------------------------- #
    # VecEnv API
    # --------------------------------------------------------------------- #

    def seed(self, seed: int = None) -> list[int | None]:
        return [self.unwrapped.seed(seed)] * self.unwrapped.num_envs

    def reset(self) -> VecEnvObs:
        obs_dict, _ = self.env.reset()
        self._ep_rew_buf[:] = 0.0
        self._ep_len_buf[:] = 0
        return self._process_obs(obs_dict)

    def step_async(self, actions) -> None:
        if not isinstance(actions, torch.Tensor):
            actions = np.asarray(actions)
            actions = torch.from_numpy(actions).to(device=self.sim_device, dtype=torch.float32)
        else:
            actions = actions.to(device=self.sim_device, dtype=torch.float32)
        self._async_actions = actions

    def step_wait(self) -> VecEnvStepReturn:
        obs_dict, rew, terminated, truncated, extras = self.env.step(self._async_actions)

        dones = terminated | truncated

        obs = self._process_obs(obs_dict)
        rewards = rew.detach().cpu().numpy()
        terminated_np = terminated.detach().cpu().numpy()
        truncated_np = truncated.detach().cpu().numpy()
        dones_np = dones.detach().cpu().numpy()

        reset_ids = dones_np.nonzero()[0]

        self._ep_rew_buf += rewards
        self._ep_len_buf += 1

        infos = self._process_extras(obs, terminated_np, truncated_np, extras, reset_ids)

        self._ep_rew_buf[reset_ids] = 0.0
        self._ep_len_buf[reset_ids] = 0

        return obs, rewards, dones_np, infos

    def close(self) -> None:
        self.env.close()

    def get_attr(self, attr_name, indices=None):
        if indices is None:
            indices = slice(None)
            num_indices = self.num_envs
        else:
            num_indices = len(indices)

        attr_val = getattr(self.env, attr_name)
        if not isinstance(attr_val, torch.Tensor):
            return [attr_val] * num_indices
        return attr_val[indices].detach().cpu().numpy()

    def set_attr(self, attr_name, value, indices=None):
        raise NotImplementedError("Setting attributes on the Genesis env via SB3 wrapper is not supported.")

    def env_method(self, method_name: str, *method_args, indices=None, **method_kwargs):
        if method_name == "render":
            return self.env.render()
        env_method = getattr(self.env, method_name)
        return env_method(*method_args, indices=indices, **method_kwargs)

    def env_is_wrapped(self, wrapper_class, indices=None):
        # Minimal implementation so that SB3 helpers like evaluate_policy() work.
        del wrapper_class, indices
        return [False]

    def get_images(self):
        raise NotImplementedError("Image fetching is not implemented for Genesis SB3 wrapper.")

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #

    def _process_spaces(self) -> None:
        # Genesis observation_manager exposes a dict of groups; we mirror IsaacLab:
        # use the single_observation_space["policy"] entry for the SB3 env.
        observation_space = self.unwrapped.single_observation_space["policy"]
        if isinstance(observation_space, gym.spaces.Dict):
            for obs_key, obs_space in observation_space.spaces.items():
                processors: list[callable[[torch.Tensor], Any]] = []

                if is_image_space(obs_space, check_channels=True, normalized_image=True):
                    actually_normalized = np.all(obs_space.low == -1.0) and np.all(obs_space.high == 1.0)
                    if not actually_normalized:
                        if np.any(obs_space.low != 0) or np.any(obs_space.high != 255):
                            raise ValueError(
                                "Image observation is not normalized in environment and cannot be normalized by SB3 "
                                "unless min=0 and max=255."
                            )
                        if obs_space.dtype != np.uint8:
                            processors.append(lambda obs: obs.to(torch.uint8))
                        observation_space.spaces[obs_key] = gym.spaces.Box(0, 255, obs_space.shape, np.uint8)
                    else:

                        def tranp(img: torch.Tensor) -> torch.Tensor:
                            return img.permute(2, 0, 1) if len(img.shape) == 3 else img.permute(0, 3, 1, 2)

                        if not is_image_space_channels_first(obs_space):
                            processors.append(tranp)
                            h, w, c = obs_space.shape
                            observation_space.spaces[obs_key] = gym.spaces.Box(-1.0, 1.0, (c, h, w), obs_space.dtype)

                    def chained_processor(obs: torch.Tensor, procs=processors) -> Any:
                        for proc in procs:
                            obs = proc(obs)
                        return obs

                    if len(processors) > 0:
                        self.observation_processors[obs_key] = chained_processor

        action_space = self.unwrapped.single_action_space
        if isinstance(action_space, gym.spaces.Box) and not action_space.is_bounded("both"):
            action_space = gym.spaces.Box(low=-100, high=100, shape=action_space.shape)

        VecEnv.__init__(self, self.num_envs, observation_space, action_space)

    def _process_obs(self, obs_dict: torch.Tensor | dict[str, torch.Tensor]) -> np.ndarray | dict[str, np.ndarray]:
        # Genesis follows the same convention: obs_dict is a VecEnvObs mapping.
        obs = obs_dict["policy"]
        if isinstance(obs, dict):
            for key, value in obs.items():
                if key in self.observation_processors:
                    obs[key] = self.observation_processors[key](value)
                obs[key] = obs[key].detach().cpu().numpy()
        elif isinstance(obs, torch.Tensor):
            obs = obs.detach().cpu().numpy()
        else:
            raise NotImplementedError(f"Unsupported observation type: {type(obs)}")
        return obs

    def _process_extras(
        self,
        obs: np.ndarray | dict[str, np.ndarray],
        terminated: np.ndarray,
        truncated: np.ndarray,
        extras: dict,
        reset_ids: np.ndarray,
    ) -> list[dict[str, Any]]:
        """Convert Genesis manager extras into SB3-style info dicts."""
        if self.fast_variant:
            infos: list[dict[str, Any]] = [{} for _ in range(self.num_envs)]

            for idx in reset_ids:
                infos[idx]["episode"] = {
                    "r": float(self._ep_rew_buf[idx]),
                    "l": int(self._ep_len_buf[idx]),
                }
                infos[idx]["TimeLimit.truncated"] = bool(truncated[idx] and not terminated[idx])

                if isinstance(obs, dict):
                    terminal_obs = {key: value[idx] for key, value in obs.items()}
                else:
                    terminal_obs = obs[idx]
                infos[idx]["terminal_observation"] = terminal_obs

            return infos

        # Slow, but more complete path (kept for parity with IsaacLab).
        infos = [dict.fromkeys(extras.keys()) for _ in range(self.num_envs)]
        for idx in range(self.num_envs):
            if idx in reset_ids:
                infos[idx]["episode"] = {
                    "r": float(self._ep_rew_buf[idx]),
                    "l": float(self._ep_len_buf[idx]),
                }
            else:
                infos[idx]["episode"] = None

            infos[idx]["TimeLimit.truncated"] = bool(truncated[idx] and not terminated[idx])

            for key, value in extras.items():
                if key == "log":
                    if infos[idx]["episode"] is not None:
                        for sub_key, sub_value in value.items():
                            infos[idx]["episode"][sub_key] = sub_value
                else:
                    infos[idx][key] = value[idx]

            if idx in reset_ids:
                if isinstance(obs, dict):
                    terminal_obs = {key: value[idx] for key, value in obs.items()}
                else:
                    terminal_obs = obs[idx]
                infos[idx]["terminal_observation"] = terminal_obs
            else:
                infos[idx]["terminal_observation"] = None

        return infos

