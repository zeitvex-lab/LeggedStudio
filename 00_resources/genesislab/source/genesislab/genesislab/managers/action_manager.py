"""Action manager for processing actions sent to the environment."""

from __future__ import annotations

import abc
from dataclasses import MISSING
from typing import TYPE_CHECKING, Optional, Sequence

import torch
from prettytable import PrettyTable

from genesislab.managers.manager_base import ManagerBase, ManagerTermBase
from genesislab.managers.manager_term_cfg import ActionTermCfg
from genesislab.utils.configclass.string import resolve_matching_names_values

if TYPE_CHECKING:
	from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv


class ActionTerm(ManagerTermBase):
	"""Base class for action terms.

	The action term is responsible for processing the raw actions sent to the environment
	and applying them to the entity managed by the term.
	"""

	def __init__(self, cfg: ActionTermCfg, env: "ManagerBasedRlEnv"):
		self.cfg = cfg
		super().__init__(cfg=cfg, env=env)
		# Get entity from scene - required
		if not hasattr(self._env, "scene"):
			raise AttributeError(
				"Environment does not have 'scene' attribute. "
				"ActionManager requires LabScene to access entities."
			)
		
		if not hasattr(self._env.scene, "entities"):
			raise AttributeError(
				"Scene does not have 'entities' attribute. "
				"Scene may not be properly initialized."
			)
		
		if self.cfg.entity_name not in self._env.scene.entities:
			raise KeyError(
				f"Entity '{self.cfg.entity_name}' not found in scene.entities. "
				f"Available entities: {list(self._env.scene.entities.keys())}"
			)
		
		self._entity = self._env.scene.entities[self.cfg.entity_name]
		
		# Clip bounds cache (will be initialized by _build_clip_bounds)
		self._clip_lower: torch.Tensor | float = None
		self._clip_upper: torch.Tensor | float = None

	@property
	@abc.abstractmethod
	def action_dim(self) -> int:
		raise NotImplementedError

	@abc.abstractmethod
	def process_actions(self, actions: torch.Tensor) -> None:
		raise NotImplementedError

	@abc.abstractmethod
	def apply_actions(self) -> None:
		raise NotImplementedError

	@property
	@abc.abstractmethod
	def raw_action(self) -> torch.Tensor:
		raise NotImplementedError

	def _build_clip_bounds(
		self,
		action_dim: int,
		clip: tuple[float, float] | dict[str, tuple[float, float]] | None,
		joint_names: list[str] = None,
	) -> None:
		"""Build and cache clip bounds for efficient clipping.
		
		This method should be called once during initialization to pre-compute
		clip bounds, avoiding repeated computation in _apply_clip.
		
		Args:
			action_dim: Dimension of the action space.
			clip: Clip configuration. Can be:
				- tuple[float, float]: (min, max) for uniform clipping
				- dict[str, tuple[float, float]]: Per-joint clipping with regex patterns
				- None: No clipping
			joint_names: List of joint names for dict clip matching. Required if clip is dict.
				Must match action_dim.
		
		Raises:
			TypeError: If clip is dict but joint_names is None.
			ValueError: If joint_names length doesn't match action_dim.
		"""
		if clip is None:
			self._clip_lower = None
			self._clip_upper = None
			return
		
		if isinstance(clip, tuple):
			# Uniform clipping (scalar clip): store as float values
			self._clip_lower = float(clip[0])
			self._clip_upper = float(clip[1])
		elif isinstance(clip, dict):
			# Per-joint clipping: build bounds tensors
			if joint_names is None:
				raise TypeError(
					"joint_names must be provided when clip is a dict. "
					"Dict clip requires joint names for pattern matching."
				)
			if len(joint_names) != action_dim:
				raise ValueError(
					f"joint_names length ({len(joint_names)}) must match action_dim "
					f"({action_dim}) for dict clip."
				)
			
			# Resolve clip patterns to joint indices
			matched_indices, matched_names, clip_values = resolve_matching_names_values(
				clip, joint_names, preserve_order=False
			)
			
			# Build bounds tensors
			self._clip_lower = torch.full((action_dim,), -float('inf'), device=self.device)
			self._clip_upper = torch.full((action_dim,), float('inf'), device=self.device)
			
			for idx, (min_val, max_val) in zip(matched_indices, clip_values):
				self._clip_lower[idx] = float(min_val)
				self._clip_upper[idx] = float(max_val)
		else:
			raise TypeError(
				f"clip must be tuple[float, float], dict[str, tuple[float, float]], or None, "
				f"got {type(clip)}"
			)
	
	def _apply_clip(self, targets: torch.Tensor) -> torch.Tensor:
		"""Apply clipping to action targets using pre-computed bounds.
		
		This method uses the cached clip bounds from _build_clip_bounds() for
		efficient clipping without repeated computation.
		
		Args:
			targets: Action targets tensor of shape (num_envs, action_dim) to clip.
		
		Returns:
			Clipped targets tensor of same shape as input.
		"""
		if self._clip_lower is None or self._clip_upper is None:
			return targets
		
		if isinstance(self._clip_lower, float) and isinstance(self._clip_upper, float):
			# Uniform clipping (scalar clip)
			return torch.clamp(targets, min=self._clip_lower, max=self._clip_upper)
		else:
			# Per-joint clipping (tensor bounds)
			lower = self._clip_lower.unsqueeze(0)  # (1, action_dim)
			upper = self._clip_upper.unsqueeze(0)  # (1, action_dim)
			return torch.clamp(targets, min=lower, max=upper)


class ActionManager(ManagerBase):
	"""Manages action processing for the environment.

	The action manager aggregates multiple action terms, each controlling a different
	entity or aspect of the simulation. It splits the policy's action tensor and
	routes each slice to the appropriate action term.
	"""

	def __init__(self, cfg: dict[str, ActionTermCfg], env: "ManagerBasedRlEnv"):
		self.cfg = cfg
		super().__init__(cfg=cfg, env=env)

		# Create buffers to store actions.
		self._action = torch.zeros(
			(self.num_envs, self.total_action_dim), device=self.device
		)
		self._prev_action = torch.zeros_like(self._action)
		self._prev_prev_action = torch.zeros_like(self._action)

	def __str__(self) -> str:
		msg = f"<ActionManager> contains {len(self._term_names)} active terms.\n"
		table = PrettyTable()
		table.title = f"Active Action Terms (shape: {self.total_action_dim})"
		table.field_names = ["Index", "Name", "Dimension"]
		table.align["Name"] = "l"
		table.align["Dimension"] = "r"
		for index, (name, term) in enumerate(self._terms.items()):
			table.add_row([index, name, term.action_dim])
		msg += table.get_string()
		msg += "\n"
		return msg

	# Properties.

	@property
	def total_action_dim(self) -> int:
		return sum(self.action_term_dim)

	@property
	def action_term_dim(self) -> list[int]:
		return [term.action_dim for term in self._terms.values()]

	@property
	def action(self) -> torch.Tensor:
		"""Raw policy output from the current step, before per-term
		scale/offset. Shape: ``(num_envs, total_action_dim)``."""
		return self._action

	@property
	def prev_action(self) -> torch.Tensor:
		"""Raw policy output from the previous step, before per-term
		scale/offset. Shape: ``(num_envs, total_action_dim)``."""
		return self._prev_action

	@property
	def prev_prev_action(self) -> torch.Tensor:
		"""Raw policy output from two steps ago, before per-term
		scale/offset. Shape: ``(num_envs, total_action_dim)``."""
		return self._prev_prev_action

	@property
	def active_terms(self) -> list[str]:
		return self._term_names

	# Methods.

	def get_term(self, name: str) -> ActionTerm:
		return self._terms[name]

	def reset(self, env_ids: torch.Tensor | slice = None) -> dict[str, float]:
		if env_ids is None:
			env_ids = slice(None)
		# Reset action history.
		self._prev_action[env_ids] = 0.0
		self._prev_prev_action[env_ids] = 0.0
		self._action[env_ids] = 0.0
		# Reset action terms.
		for term in self._terms.values():
			term.reset(env_ids=env_ids)
		return {}

	def process_action(self, action: torch.Tensor) -> None:
		"""Store the raw policy output and route slices to each action term.

		Called once per policy step. The raw action tensor is saved into the
		history buffers (``action``, ``prev_action``, ``prev_prev_action``) *before*
		any per-term scale/offset is applied. Each term then receives its slice and
		independently applies its own affine transformation via
		:meth:`ActionTerm.process_actions`.
		"""
		if self.total_action_dim != action.shape[1]:
			raise ValueError(
				f"Invalid action shape, expected: {self.total_action_dim},"
				f" received: {action.shape[1]}."
			)
		# Shift history: prev_prev ← prev ← current ← new.
		self._prev_prev_action[:] = self._prev_action
		self._prev_action[:] = self._action
		self._action[:] = action.to(self.device)
		# Split the flat action vector and route each slice to its term.
		idx = 0
		for term in self._terms.values():
			term_actions = action[:, idx : idx + term.action_dim]
			term.process_actions(term_actions)
			idx += term.action_dim

	def apply_action(self) -> None:
		"""Write processed actions to entity actuator targets.

		Called on every decimation substep (physics step), not just once per policy
		step. Each term writes its most recently processed targets to the simulation.
		"""
		for term in self._terms.values():
			term.apply_actions()

	def get_active_iterable_terms(
		self, env_idx: int
	) -> Sequence[tuple[str, Sequence[float]]]:
		terms = []
		idx = 0
		for name, term in self._terms.items():
			term_actions = self._action[env_idx, idx : idx + term.action_dim].cpu()
			terms.append((name, term_actions.tolist()))
			idx += term.action_dim
		return terms

	def _prepare_terms(self):
		self._term_names: list[str] = list()
		self._terms: dict[str, ActionTerm] = dict()

		# Extract terms from configclass __dict__ or dict items
		if isinstance(self.cfg, dict):
			term_cfg_items = self.cfg.items()
		else:
			term_cfg_items = self.cfg.__dict__.items()

		for term_name, term_cfg in term_cfg_items:
			# Skip private fields
			if term_name.startswith("_"):
				continue
			if term_cfg is None or term_cfg is MISSING:
				print(f"term: {term_name} set to None/MISSING, skipping...")
				continue
			if not isinstance(term_cfg, ActionTermCfg):
				raise TypeError(
					f"Configuration for the term '{term_name}' is not of type 'ActionTermCfg'."
					f" Received: '{type(term_cfg)}'."
				)
			# Create the action term using class_type
			term = term_cfg.class_type(term_cfg, self._env)
			# Sanity check if term is valid type
			if not isinstance(term, ActionTerm):
				raise TypeError(
					f"Returned object for the term '{term_name}' is not of type 'ActionTerm'."
					f" Received: '{type(term)}'."
				)
			self._term_names.append(term_name)
			self._terms[term_name] = term
