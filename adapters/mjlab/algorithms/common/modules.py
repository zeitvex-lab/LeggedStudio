"""Shared nn building blocks and RSL-RL conditional-model infrastructure.

Split out of the former ``local_tasks/learning/models.py`` so every algorithm
family (cts / dreamwaq / amp / distill) builds on the same primitives without
depending on each other or on a robot task package.  The family-specific actor
critics live in their own ``<family>/models.py``.
"""

from __future__ import annotations

import copy
from typing import NamedTuple

import torch
from rsl_rl.models.mlp_model import MLPModel
from rsl_rl.modules import GaussianDistribution
from rsl_rl.modules.mlp import MLP
from torch import nn
from torch.distributions import Normal
from torch.nn import functional as F


def _activation(name: str) -> nn.Module:
  if name == "elu":
    return nn.ELU()
  if name == "relu":
    return nn.ReLU()
  if name == "tanh":
    return nn.Tanh()
  raise ValueError(f"Unsupported activation: {name}")


def _mlp(
  input_dim: int,
  output_dim: int,
  hidden_dims: tuple[int, ...],
  activation: str = "elu",
) -> nn.Sequential:
  layers: list[nn.Module] = []
  current = input_dim
  for hidden in hidden_dims:
    layers.extend((nn.Linear(current, hidden), _activation(activation)))
    current = hidden
  layers.append(nn.Linear(current, output_dim))
  return nn.Sequential(*layers)


class PolicyOutput(NamedTuple):
  action: torch.Tensor
  log_prob: torch.Tensor
  mean: torch.Tensor
  std: torch.Tensor


class Go2ClampedGaussianDistribution(GaussianDistribution):
  """Gaussian policy noise with the source per-joint minimum standard deviation."""

  def __init__(
    self,
    output_dim: int,
    min_std: tuple[float, ...],
    **kwargs,
  ) -> None:
    super().__init__(output_dim, **kwargs)
    if len(min_std) != output_dim:
      raise ValueError(f"Expected {output_dim} minimum std values, got {len(min_std)}")
    self.min_std: torch.Tensor
    self.register_buffer("min_std", torch.tensor(min_std, dtype=torch.float32))

  def update(self, mlp_output: torch.Tensor) -> None:
    super().update(mlp_output)
    assert self._distribution is not None
    self._distribution = Normal(
      self._distribution.mean,
      torch.maximum(self._distribution.stddev, self.min_std),
    )


class _GaussianPolicy(nn.Module):
  def __init__(self, input_dim: int, action_dim: int, hidden_dims: tuple[int, ...]):
    super().__init__()
    self.policy = _mlp(input_dim, action_dim, hidden_dims)
    self.log_std = nn.Parameter(torch.zeros(action_dim))

  def distribution(self, features: torch.Tensor) -> Normal:
    mean = self.policy(features)
    return Normal(mean, self.log_std.exp().expand_as(mean))

  def sample(self, features: torch.Tensor, deterministic: bool = False) -> PolicyOutput:
    distribution = self.distribution(features)
    action = distribution.mean if deterministic else distribution.rsample()
    return PolicyOutput(
      action,
      distribution.log_prob(action).sum(dim=-1),
      distribution.mean,
      distribution.stddev,
    )


class _ConditionalActor(MLPModel):
  """RSL-RL actor whose latent input is assembled from extra mjlab groups."""

  latent_kind: str = "none"
  use_student: bool = False
  teacher_encoder: nn.Sequential
  student_encoder: nn.Sequential
  vae: "object"  # DreamWaQVAE; typed loosely to avoid a cross-family import
  student_lstm: nn.LSTM
  student_head: nn.Sequential
  terrain_encoder: nn.Sequential
  privileged_encoder: nn.Sequential

  def __init__(self, obs, obs_groups, obs_set, output_dim, **kwargs) -> None:
    super().__init__(obs, obs_groups, obs_set, output_dim, **kwargs)
    actor_dim = int(obs["actor"].shape[-1])
    self._go2_actor_dim = actor_dim
    self._go2_conditional_dim = 0
    self._go2_conditional_splits: tuple[int, ...] = ()
    hidden_dims = tuple(kwargs.get("hidden_dims", (512, 256, 128)))
    activation = kwargs.get("activation", "elu")
    self.latent_kind = type(self).latent_kind
    self.use_student = type(self).use_student
    latent_dim = 0
    if self.latent_kind == "cts":
      latent_dim = 32
      if self.use_student:
        source_dim = int(obs["history"].shape[-1])
        self._go2_cts_student_dim = source_dim - actor_dim
        self._go2_conditional_dim = self._go2_cts_student_dim
        self._go2_conditional_splits = (self._go2_conditional_dim,)
        self.student_encoder = _mlp(source_dim - actor_dim, latent_dim, (512, 256))
      else:
        privileged_dim = int(obs["privileged"].shape[-1])
        history_dim = int(obs["history"].shape[-1])
        self._go2_cts_student_dim = history_dim - actor_dim
        self._go2_conditional_dim = privileged_dim
        self._go2_conditional_splits = (privileged_dim, history_dim)
        self.teacher_encoder = _mlp(privileged_dim, latent_dim, (512, 256))
        self.student_encoder = _mlp(history_dim - actor_dim, latent_dim, (512, 256))
    elif self.latent_kind == "dreamwaq":
      history_dim = int(obs["history"].shape[-1])
      self._go2_conditional_dim = history_dim - actor_dim
      self._go2_conditional_splits = (self._go2_conditional_dim,)
      # Imported lazily: the DreamWaQ VAE belongs to the dreamwaq family while
      # this shared base serves every family (avoids an import cycle).
      from adapters.mjlab.algorithms.dreamwaq.models import DreamWaQVAE

      # The source VAE consumes history excluding the newest actor frame;
      # that 45-D frame is concatenated directly to the latent downstream.
      self.vae = DreamWaQVAE(history_dim - actor_dim, 16, 3, actor_dim)
      latent_dim = 19
    elif self.latent_kind == "ts":
      latent_dim = 32
      if self.use_student:
        history_dim = int(obs["history"].shape[-1])
        self._go2_conditional_dim = history_dim
        self._go2_conditional_splits = (history_dim,)
        # Match the source TS student encoder capacity so the same weights
        # can be used by the external-state deployment exporter.
        self.student_lstm = nn.LSTM(actor_dim, 256, num_layers=3, batch_first=True)
        self.student_head = _mlp(256, latent_dim, (256, 128))
      else:
        terrain_dim = int(obs["terrain"].shape[-1])
        privileged_dim = int(obs["privileged"].shape[-1])
        self._go2_conditional_dim = terrain_dim + privileged_dim
        self._go2_conditional_splits = (terrain_dim, privileged_dim)
        self.terrain_encoder = _mlp(terrain_dim, 16, (256, 128))
        self.privileged_encoder = _mlp(privileged_dim, 16, (128, 64))
    self.mlp = MLP(
      actor_dim + latent_dim,
      self.distribution.input_dim if self.distribution else output_dim,
      hidden_dims,
      activation,
    )
    if self.distribution is not None:
      self.distribution.init_mlp_weights(self.mlp)

  def _student_history_features(self, history: torch.Tensor) -> torch.Tensor:
    if history.ndim == 2:
      if history.shape[-1] % self.obs_dim == 0:
        history = history.view(history.shape[0], -1, self.obs_dim)
      else:
        history = history.unsqueeze(1)
    sequence, _ = self.student_lstm(history)
    return self.student_head(sequence[:, -1])

  def _conditional_features(self, obs: dict[str, torch.Tensor]) -> torch.Tensor:
    if self.latent_kind == "cts":
      # Source ``obs_hist_buf`` excludes the current observation.  The mjlab
      # compatibility group retains one extra frame so dropping its newest
      # 45-D block reproduces the source five-frame input exactly.
      student = F.normalize(
        self.student_encoder(obs["history"][..., : -self._go2_actor_dim]),
        p=2.0,
        dim=-1,
      )
      if self.use_student:
        return student
      teacher = F.normalize(self.teacher_encoder(obs["privileged"]), p=2.0, dim=-1)
      mask = obs.get("teacher_mask")
      if mask is None:
        return teacher
      # Match the source CTS update: PPO trains the teacher path, while the
      # student path is updated only by the latent distillation loss.
      return torch.where(mask > 0.5, teacher, student.detach())
    if self.latent_kind == "dreamwaq":
      encoded = self.vae(obs["history"][..., : -self._go2_actor_dim])
      # Source ``ActorCriticDreamWaQ`` concatenates the sampled velocity code
      # before the sampled latent code, then appends the current actor frame.
      return torch.cat((encoded["explicit"], encoded["latent"]), dim=-1)
    if self.latent_kind == "ts":
      if self.use_student:
        return self._student_history_features(obs["history"])
      return torch.cat(
        (
          self.terrain_encoder(obs["terrain"]),
          self.privileged_encoder(obs["privileged"]),
        ),
        dim=-1,
      )
    return obs["actor"].new_zeros((obs["actor"].shape[0], 0))

  def get_latent(self, obs, masks=None, hidden_state=None):
    del masks, hidden_state
    actor_obs = self.obs_normalizer(obs["actor"])
    conditional = self._conditional_features(obs)
    # All four source conditional policies build their actor input as
    # ``latent || current_observation`` (CTS, DreamWaQ and AMP-TS included).
    # Keep the ordinary PPO actor-only path unchanged.
    return (
      torch.cat((conditional, actor_obs), dim=-1)
      if conditional.shape[-1]
      else actor_obs
    )

  def as_onnx(self, verbose: bool):
    """Return a multi-input deterministic wrapper for deployment export.

    RSL-RL's default MLP wrapper assumes a single observation group.  Go2
    teacher/student actors additionally consume history or privileged inputs,
    so the deployment contract is ``(actor, conditional)`` where
    ``conditional`` is either the single selected group or the concatenation
    ``terrain || privileged`` for a teacher TS policy.
    """
    return _ConditionalOnnxModel(self, verbose)


class _ConditionalOnnxModel(nn.Module):
  """ONNX-safe deterministic wrapper around a conditional Go2 actor."""

  is_recurrent = False
  teacher_encoder: nn.Sequential
  student_encoder: nn.Sequential
  vae: "object"
  student_lstm: nn.LSTM
  student_head: nn.Sequential
  terrain_encoder: nn.Sequential
  privileged_encoder: nn.Sequential

  def __init__(self, model: _ConditionalActor, verbose: bool) -> None:
    super().__init__()
    self.verbose = verbose
    self.obs_normalizer = copy.deepcopy(model.obs_normalizer)
    self.mlp = copy.deepcopy(model.mlp)
    self.latent_kind = model.latent_kind
    # CTS is concurrent only during rollout collection.  The source
    # ``act_inference`` and deployment exporter always use the distilled
    # history encoder, never the privileged teacher.  Force that path for the
    # exported artifact even though the training actor itself is a mixed
    # teacher/student model.
    self.use_student = model.use_student or model.latent_kind == "cts"
    self.actor_dim = model._go2_actor_dim
    self.conditional_dim = (
      model._go2_cts_student_dim
      if model.latent_kind == "cts"
      else model._go2_conditional_dim
    )
    self.conditional_splits = model._go2_conditional_splits
    # Keep only the conditional modules needed by this policy.  Assigning the
    # modules (rather than deep-copying) preserves the trained weights when the
    # runner moves this wrapper to CPU for export.
    for name in (
      "encoder",
      "teacher_encoder",
      "student_encoder",
      "vae",
      "student_lstm",
      "student_head",
      "terrain_encoder",
      "privileged_encoder",
    ):
      if hasattr(model, name):
        setattr(self, name, copy.deepcopy(getattr(model, name)))
    if model.distribution is not None:
      self.deterministic_output = model.distribution.as_deterministic_output_module()
    else:
      self.deterministic_output = nn.Identity()

  def _features(self, conditional: torch.Tensor) -> torch.Tensor:
    if self.latent_kind == "cts":
      encoder = self.student_encoder if self.use_student else self.teacher_encoder
      return F.normalize(encoder(conditional), p=2.0, dim=-1)
    if self.latent_kind == "dreamwaq":
      # Deployment callers already provide the source five-frame history;
      # only the in-environment observation group carries an extra current
      # frame that must be removed before reaching this wrapper.
      encoded = self.vae.encoder(conditional)
      mean_latent = self.vae.mean_latent(encoded)
      mean_explicit = self.vae.mean_explicit(encoded)
      return torch.cat((mean_explicit, mean_latent), dim=-1)
    if self.latent_kind == "ts":
      if self.use_student:
        history = conditional.view(conditional.shape[0], -1, self.actor_dim)
        sequence, _ = self.student_lstm(history)
        return self.student_head(sequence[:, -1])
      terrain_dim, privileged_dim = self.conditional_splits
      terrain, privileged = torch.split(
        conditional, [terrain_dim, privileged_dim], dim=-1
      )
      return torch.cat(
        (self.terrain_encoder(terrain), self.privileged_encoder(privileged)), dim=-1
      )
    return conditional.new_zeros((conditional.shape[0], 0))

  def forward(self, actor: torch.Tensor, conditional: torch.Tensor) -> torch.Tensor:
    features = self._features(conditional)
    actor_obs = self.obs_normalizer(actor)
    # This wrapper is created only for conditional Go2 actors, so its feature
    # width is statically non-zero.  Avoid a tensor-shape Python branch here;
    # otherwise ONNX tracing bakes in the dummy batch and emits a misleading
    # generalization warning.
    latent = torch.cat((features, actor_obs), dim=-1)
    return self.deterministic_output(self.mlp(latent))

  def get_dummy_inputs(self) -> tuple[torch.Tensor, torch.Tensor]:
    return (
      torch.zeros(1, self.actor_dim),
      torch.zeros(1, self.conditional_dim),
    )

  @property
  def input_names(self) -> list[str]:
    return ["actor", "conditional"]

  @property
  def output_names(self) -> list[str]:
    return ["actions"]

  @property
  def dynamic_axes(self) -> dict[str, dict[int, str]]:
    return {
      "actor": {0: "batch"},
      "conditional": {0: "batch"},
      "actions": {0: "batch"},
    }


class _TsStudentRecurrentOnnxModel(nn.Module):
  """ONNX-safe recurrent wrapper for TS student actors."""

  is_recurrent = True

  def __init__(self, model, verbose: bool = False) -> None:
    super().__init__()
    self.verbose = verbose
    self.obs_normalizer = copy.deepcopy(model.obs_normalizer)
    self.student_lstm = copy.deepcopy(model.student_lstm)
    self.student_head = copy.deepcopy(model.student_head)
    self.mlp = copy.deepcopy(model.mlp)
    if model.distribution is not None:
      self.deterministic_output = model.distribution.as_deterministic_output_module()
    else:
      self.deterministic_output = nn.Identity()
    self.actor_dim = model._go2_actor_dim
    self.hidden_size = model.student_lstm.hidden_size
    self.num_layers = model.student_lstm.num_layers

  def forward(
    self,
    obs: torch.Tensor,
    h: torch.Tensor,
    c: torch.Tensor,
  ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    obs = self.obs_normalizer(obs)
    encoded, (h_next, c_next) = self.student_lstm(obs[:, None, :], (h, c))
    latent = self.student_head(encoded[:, -1])
    actions = self.deterministic_output(self.mlp(torch.cat((latent, obs), dim=-1)))
    return actions, h_next, c_next

  def get_dummy_inputs(self) -> tuple[torch.Tensor, ...]:
    return (
      torch.zeros(1, self.actor_dim),
      torch.zeros(self.num_layers, 1, self.hidden_size),
      torch.zeros(self.num_layers, 1, self.hidden_size),
    )

  @property
  def input_names(self) -> list[str]:
    return ["obs", "h", "c"]

  @property
  def output_names(self) -> list[str]:
    return ["actions", "he", "ce"]

  @property
  def dynamic_axes(self) -> dict[str, dict[int, str]]:
    return {
      "obs": {0: "batch"},
      "h": {1: "batch"},
      "c": {1: "batch"},
      "actions": {0: "batch"},
      "he": {1: "batch"},
      "ce": {1: "batch"},
    }
