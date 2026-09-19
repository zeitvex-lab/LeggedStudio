"""Model surface for the HIM plugin family.

Two layers live here:

- Re-exports of the extracted UniLab core (``actor_critic.py`` / ``estimator.py``,
  provenance headers untouched upstream).
- The mjlab/RSL-RL adapter models (``HIMActorModel``): an ``rsl_rl`` ``MLPModel``
  whose "actor" observation group is the HIMLoco stacked history (45-D frames ×
  history length, newest frame first) and whose latent input is assembled by the
  ``HIMEstimator`` as ``[current_frame(45), est_vel(3), est_latent(16)]``.
"""

from __future__ import annotations

import copy

import torch
from rsl_rl.models.mlp_model import MLPModel
from rsl_rl.modules import MLP
from torch import nn

from .actor_critic import HIMActorCritic
from .config import DEFAULT_HIM_CONFIG
from .estimator import HIMEstimator, get_activation, sinkhorn

__all__ = [
    "HIMActorCritic",
    "HIMActorModel",
    "HIMEstimator",
    "get_activation",
    "sinkhorn",
]


class HIMActorModel(MLPModel):
    """RSL-RL actor over the HIM history observation.

    ``obs["actor"]`` is the flattened HIMLoco ``obs_hist_buf``: ``history_size``
    consecutive 45-D frames stacked **newest first** (frame 0 = current step),
    exactly matching upstream ``obs_buf = cat(current, obs_buf[:, :-45])``. The
    estimator consumes the full history and yields the deployment latent
    ``[est_vel(3), est_latent(num_latent)]``; the actor MLP consumes
    ``[frame45, vel, latent]``. The estimator is updated exclusively by its own
    optimizer inside :class:`~adapters.mjlab.algorithms.him.algorithms.HimPPO`
    (upstream: HIMPPO.update -> estimator.update), so its forward here always
    runs under ``torch.no_grad()`` — PPO gradients never flow into it.
    """

    latent_kind = "him"

    def __init__(
        self,
        obs,
        obs_groups,
        obs_set,
        output_dim,
        one_step_obs_dim: int | None = None,
        estimator: dict | None = None,
        **kwargs,
    ) -> None:
        # ``one_step_obs_dim`` / ``estimator`` are adapter keys absorbed here so
        # the RSL-RL runner cfg only needs declared dataclass fields.
        self._adapter_one_step = (
            int(one_step_obs_dim)
            if one_step_obs_dim is not None
            else int(DEFAULT_HIM_CONFIG.one_step_obs_dim)
        )
        self._adapter_estimator_cfg = dict(estimator or {})
        super().__init__(obs, obs_groups, obs_set, output_dim, **kwargs)
        actor_dim = self.obs_dim
        if actor_dim % self._adapter_one_step != 0:
            raise ValueError(
                "HIM history obs must be an integer multiple of the 45-D frame, "
                f"got {actor_dim} and {self._adapter_one_step}"
            )
        self._one_step_obs = self._adapter_one_step
        self._history_size = actor_dim // self._adapter_one_step
        self.estimator = HIMEstimator(
            temporal_steps=self._history_size,
            num_one_step_obs=self._one_step_obs,
            activation=str(kwargs.get("activation", "elu")),
            **self._adapter_estimator_cfg,
        )
        # Rebuild the MLP head for the estimator-assembled input
        # ``[frame(45), vel(3), latent(num_latent)]``; MLPModel built it for the
        # raw 270-D group. Same rebuild pattern as _ConditionalActor.
        hidden_dims = tuple(kwargs.get("hidden_dims", (512, 256, 128)))
        activation = str(kwargs.get("activation", "elu"))
        self.mlp = MLP(
            self._one_step_obs + 3 + self.estimator.num_latent,
            self.distribution.input_dim if self.distribution else output_dim,
            hidden_dims,
            activation,
        )
        if self.distribution is not None:
            self.distribution.init_mlp_weights(self.mlp)

    def get_latent(self, obs, masks=None, hidden_state=None):
        del masks, hidden_state
        history = self.obs_normalizer(obs["actor"])
        with torch.no_grad():
            vel, latent = self.estimator(history)
        frame = history[:, : self._one_step_obs]
        return torch.cat((frame, vel, latent), dim=-1)

    def as_onnx(self, verbose: bool = False) -> nn.Module:
        """Single-input deterministic wrapper: ``obs_history -> actions``.

        Matches the upstream HIMLoco deployment contract (UniLab runner's
        ``_HimOnnxPolicy``): the estimator and the actor mean head trace as one
        graph over the stacked history, so deployment callers only stack frames
        client-side (``himloco_45_hist6`` contract).
        """
        return _HimOnnxModel(self, verbose)


class _HimOnnxModel(nn.Module):
    """ONNX-safe deterministic HIM policy: ``obs_history -> actions``.

    Every submodule is deep-copied (weights at export time) — the runner moves
    the wrapper to CPU before tracing, and an assigned (shared) estimator would
    drag the live training actor's estimator to CPU with it, crashing the next
    rollout iteration on CUDA.
    """

    is_recurrent = False

    def __init__(self, model: HIMActorModel, verbose: bool = False) -> None:
        super().__init__()
        self.verbose = verbose
        self.obs_normalizer = copy.deepcopy(model.obs_normalizer)
        self.mlp = copy.deepcopy(model.mlp)
        self.estimator = copy.deepcopy(model.estimator)
        self.one_step_obs = int(model._one_step_obs)
        self.input_size = int(model.obs_dim)
        if model.distribution is not None:
            self.deterministic_output = model.distribution.as_deterministic_output_module()
        else:
            self.deterministic_output = nn.Identity()

    def forward(self, obs_history: torch.Tensor) -> torch.Tensor:
        history = self.obs_normalizer(obs_history)
        vel, latent = self.estimator(history)
        frame = history[:, : self.one_step_obs]
        return self.deterministic_output(
            self.mlp(torch.cat((frame, vel, latent), dim=-1))
        )

    def get_dummy_inputs(self) -> tuple[torch.Tensor]:
        return (torch.zeros(1, self.input_size),)

    @property
    def input_names(self) -> list[str]:
        return ["obs_history"]

    @property
    def output_names(self) -> list[str]:
        return ["actions"]

    @property
    def dynamic_axes(self) -> dict[str, dict[int, str]]:
        return {"obs_history": {0: "batch"}, "actions": {0: "batch"}}
