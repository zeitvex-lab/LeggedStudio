"""RL-Games vectorized environment wrapper for GenesisLab.

This module mirrors :mod:`isaaclab_rl.rl_games.rl_games` but targets
GenesisLab's :class:`ManagerBasedRlEnv`.

Typical usage from an RL-Games configuration script::

    from rl_games.common import env_configurations, vecenv
    from genesis_rl.rl_games import RlGamesGpuEnv, RlGamesVecEnvWrapper

    def create_env(**kwargs):
        # construct your ManagerBasedRlEnv here
        env = ...
        return RlGamesVecEnvWrapper(
            env,
            rl_device="cuda:0",
            clip_obs=10.0,
            clip_actions=1.0,
        )

    vecenv.register("GenesisRlgWrapper", lambda config_name, num_actors, **kwargs: RlGamesGpuEnv(config_name, num_actors, **kwargs))
    env_configurations.register("rlgpu", {"vecenv_type": "GenesisRlgWrapper", "env_creator": create_env})
"""

from __future__ import annotations

from collections.abc import Callable

import gym.spaces  # required due to rl-games' usage of gym, not gymnasium
import gymnasium
import torch
from rl_games.common import env_configurations
from rl_games.common.vecenv import IVecEnv

from genesislab.envs.common import VecEnvObs
from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv


class RlGamesVecEnvWrapper(IVecEnv):
    """Wrap a :class:`ManagerBasedRlEnv` for :mod:`rl_games`.

    The behavior closely follows IsaacLab's RL-Games wrapper, but is aligned
    with GenesisLab's observation manager and config naming.
    """

    def __init__(
        self,
        env: ManagerBasedRlEnv,
        rl_device: str,
        clip_obs: float,
        clip_actions: float,
        obs_groups: dict[str, list[str]] = None,
        concate_obs_group: bool = True,
    ):
        if not isinstance(env.unwrapped, ManagerBasedRlEnv) and not isinstance(env, ManagerBasedRlEnv):
            raise ValueError(
                "The environment must be an instance of ManagerBasedRlEnv. "
                f"Got type: {type(env)}"
            )

        self.env = env
        self._rl_device = rl_device
        self._clip_obs = clip_obs
        self._clip_actions = clip_actions
        self._sim_device = env.unwrapped.device

        # Observation grouping follows the same pattern as IsaacLab:
        # default to {"obs": ["policy"], "states": ["critic"]?}
        self._concate_obs_groups = concate_obs_group
        self._obs_groups = obs_groups
        if obs_groups is None:
            self._obs_groups = {"obs": ["policy"], "states": []}
            if not self.unwrapped.single_observation_space.get("policy"):
                raise KeyError("Policy observation group is expected if no explicit groups are defined.")
            if self.unwrapped.single_observation_space.get("critic"):
                self._obs_groups["states"] = ["critic"]

        if (
            self._concate_obs_groups
            and isinstance(self.state_space, gym.spaces.Box)
            and isinstance(self.observation_space, gym.spaces.Box)
        ):
            self.rlg_num_states = self.state_space.shape[0]
        elif (
            not self._concate_obs_groups
            and isinstance(self.state_space, gym.spaces.Dict)
            and isinstance(self.observation_space, gym.spaces.Dict)
        ):
            space = [space.shape[0] for space in self.state_space.values()]
            self.rlg_num_states = sum(space)
        else:
            raise TypeError(
                "Invalid combination for state/observation spaces. "
                "Expected gym.spaces.Box when concate_obs_group=True, and gym.spaces.Dict otherwise."
            )

    # --------------------------------------------------------------------- #
    # Debug / representation helpers
    # --------------------------------------------------------------------- #

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<{type(self).__name__}{self.env}>"
            f"\n\tObservations clipping: {self._clip_obs}"
            f"\n\tActions clipping     : {self._clip_actions}"
            f"\n\tAgent device         : {self._rl_device}"
            f"\n\tAsymmetric-learning  : {self.rlg_num_states != 0}"
        )

    __repr__ = __str__

    # --------------------------------------------------------------------- #
    # Gym-like properties expected by RL-Games
    # --------------------------------------------------------------------- #

    @property
    def render_mode(self) -> str | None:
        return getattr(self.env, "render_mode", None)

    @property
    def observation_space(self) -> gym.spaces.Box | gym.spaces.Dict:
        space = self.unwrapped.single_observation_space
        clip = self._clip_obs
        if not self._concate_obs_groups:
            policy_space = {grp: gym.spaces.Box(-clip, clip, space.get(grp).shape) for grp in self._obs_groups["obs"]}
            return gym.spaces.Dict(policy_space)

        shapes = [space.get(group).shape for group in self._obs_groups["obs"]]
        cat_shape, self._obs_concat_fn = make_concat_plan(shapes)
        return gym.spaces.Box(-clip, clip, cat_shape)

    @property
    def action_space(self) -> gym.spaces.Box:
        action_space = self.unwrapped.single_action_space
        if not isinstance(action_space, gymnasium.spaces.Box):
            raise NotImplementedError(
                f"The RL-Games wrapper only supports Box action space, got: {type(action_space)}"
            )
        return gym.spaces.Box(-self._clip_actions, self._clip_actions, action_space.shape)

    @classmethod
    def class_name(cls) -> str:
        return cls.__name__

    @property
    def unwrapped(self) -> ManagerBasedRlEnv:
        return self.env.unwrapped if hasattr(self.env, "unwrapped") else self.env

    @property
    def num_envs(self) -> int:
        return self.unwrapped.num_envs

    @property
    def device(self) -> str:
        return self.unwrapped.device

    @property
    def state_space(self) -> gym.spaces.Box | gym.spaces.Dict:
        space = self.unwrapped.single_observation_space
        clip = self._clip_obs
        if not self._concate_obs_groups:
            state_space = {
                grp: gym.spaces.Box(-clip, clip, space.get(grp).shape) for grp in self._obs_groups["states"]
            }
            return gym.spaces.Dict(state_space)

        shapes = [space.get(group).shape for group in self._obs_groups["states"]]
        cat_shape, self._states_concat_fn = make_concat_plan(shapes)
        return gym.spaces.Box(-self._clip_obs, self._clip_obs, cat_shape)

    def get_number_of_agents(self) -> int:
        return getattr(self, "num_agents", 1)

    def get_env_info(self) -> dict:
        return {
            "observation_space": self.observation_space,
            "action_space": self.action_space,
            "state_space": self.state_space,
        }

    # --------------------------------------------------------------------- #
    # MDP operations
    # --------------------------------------------------------------------- #

    def seed(self, seed: int = -1) -> int:
        return self.unwrapped.seed(seed)

    def reset(self):
        obs_dict, _ = self.env.reset()
        return self._process_obs(obs_dict)

    def step(self, actions: torch.Tensor):
        actions = actions.detach().clone().to(device=self._sim_device)
        actions = torch.clamp(actions, -self._clip_actions, self._clip_actions)

        obs, rewards, terminated, truncated, extras = self.env.step(actions)

        if not self.unwrapped.cfg.is_finite_horizon:
            extras["time_outs"] = truncated.to(device=self._rl_device)

        obs_and_states = self._process_obs(obs)

        rewards = rewards.to(device=self._rl_device)
        dones = (terminated | truncated).to(device=self._rl_device)
        extras = {
            k: v.to(device=self._rl_device, non_blocking=True) if hasattr(v, "to") else v for k, v in extras.items()
        }

        if "log" in extras:
            extras["episode"] = extras.pop("log")

        return obs_and_states, rewards, dones, extras

    def close(self):
        return self.env.close()

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #

    def _process_obs(self, obs_dict: VecEnvObs) -> dict[str, torch.Tensor] | dict[str, dict[str, torch.Tensor]]:
        if self._rl_device != self._sim_device:
            obs_dict = {key: obs.to(device=self._rl_device) for key, obs in obs_dict.items()}

        for key, obs in obs_dict.items():
            obs_dict[key] = torch.clamp(obs, -self._clip_obs, self._clip_obs)

        rl_games_obs: dict[str, dict[str, torch.Tensor] | torch.Tensor] = {
            "obs": {group: obs_dict[group] for group in self._obs_groups["obs"]}
        }
        if len(self._obs_groups["states"]) > 0:
            rl_games_obs["states"] = {group: obs_dict[group] for group in self._obs_groups["states"]}

        if self._concate_obs_groups:
            rl_games_obs["obs"] = self._obs_concat_fn(list(rl_games_obs["obs"].values()))
            if "states" in rl_games_obs:
                rl_games_obs["states"] = self._states_concat_fn(list(rl_games_obs["states"].values()))

        return rl_games_obs


def make_concat_plan(shapes: list[tuple[int, ...]]) -> tuple[tuple[int, ...], Callable]:
    """Plan concatenation of a list of per-sample shapes.

    Returns:
        (out_shape, concat_fn)
    """
    if len(shapes) == 0:
        return (0,), lambda x: x

    if all(len(s) == 1 for s in shapes):
        return (sum(s[0] for s in shapes),), lambda x: torch.cat(x, dim=1)

    rank = len(shapes[0])
    if all(len(s) == rank for s in shapes) and rank > 1:
        if all(s[:-1] == shapes[0][:-1] for s in shapes):
            out_shape = shapes[0][:-1] + (sum(s[-1] for s in shapes),)
            return out_shape, lambda x: torch.cat(x, dim=-1)
        if all(s[1:] == shapes[0][1:] for s in shapes):
            out_shape = (sum(s[0] for s in shapes),) + shapes[0][1:]
            return out_shape, lambda x: torch.cat(x, dim=1)
        raise ValueError(f"Could not find a valid concatenation plan for shapes: {shapes}")

    raise ValueError("Could not find a valid concatenation plan, please make sure all shapes have the same rank.")


class RlGamesGpuEnv(IVecEnv):
    """Thin wrapper that lets RL-Games create a Genesis wrapper from its registry."""

    def __init__(self, config_name: str, num_actors: int, **kwargs):
        del num_actors  # num_actors is unused but kept for API compatibility
        self.env: RlGamesVecEnvWrapper = env_configurations.configurations[config_name]["env_creator"](**kwargs)

    def step(self, action):
        return self.env.step(action)

    def reset(self):
        return self.env.reset()

    def get_number_of_agents(self) -> int:
        return self.env.get_number_of_agents()

    def get_env_info(self) -> dict:
        return self.env.get_env_info()

