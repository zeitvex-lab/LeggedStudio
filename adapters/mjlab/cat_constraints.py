"""Constraints-as-Terminations (CaT) constraint manager.

Ported from LeggedGym-Ex ``utils/constraint_manager.py`` (BSD-3-Clause,
paper: "Constraints-as-Terminations" / Sferrazza et al. 2024).  Tracks the
Polyak-averaged running maximum of each constraint's violation and maps the
violation degree into a termination probability in [min_p, max_p].

mjlab-native usage (from a task env cfg):

    from cat_constraints import ConstraintManagerCfg  # if vendored on sys.path

    cfg.constraints = {
        "action_rate_soft": ConstraintCfg(func=..., soft=True, ...),
    }

or as termination-probability terms wired through the reward/termination
managers using :class:`ConstraintTermCfg`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

import torch

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


@dataclass
class ConstraintCfg:
    """A single constraint: violation_fn returns per-env violation magnitude."""

    violation_fn: Callable[..., torch.Tensor]
    params: dict[str, Any] = field(default_factory=dict)
    soft: bool = True  # soft constraints can be violated occasionally; hard ones terminate fast
    min_prob: float = 0.0
    max_prob: float = 1.0
    polyak: float = 0.95  # running-average decay for the running max tracker


class ConstraintManager:
    """Tracks constraint violations and converts them into termination probabilities.

    - For each constraint the violation magnitude (clipped at 0) is Polyak-
      averaged into a running maximum so transient spikes do not immediately
      terminate but persistent violations do.
    - Termination probability per env = min_p + violation_degree * (max_p - min_p).
    - Sampling: a Bernoulli draw per env per step decides termination.
    """

    def __init__(
        self,
        cfg: dict[str, ConstraintCfg],
        num_envs: int,
        device: str,
        tau: float = 0.95,
        min_prob: float = 0.0,
        max_prob: float = 1.0,
    ) -> None:
        self.cfg = cfg
        self.num_envs = num_envs
        self.device = device
        self.tau = tau
        self.min_prob = min_prob
        self.max_prob = max_prob
        # Running max/min trackers per constraint (Polyak-averaged extremes).
        self._running_max: dict[str, torch.Tensor] = {}
        self._running_min: dict[str, torch.Tensor] = {}
        self._term_prob = torch.zeros(num_envs, device=device)

    def compute(self, env) -> torch.Tensor:
        """Compute the per-env termination probability for this step."""
        prob = torch.full((self.num_envs,), self.min_prob, device=self.device)
        for name, cfg_item in self.cfg.items():
            violation = cfg_item.violation_fn(env, **cfg_item.params)
            violation = torch.clamp(violation, min=0.0).float()
            if name not in self._running_max:
                self._running_max[name] = violation.clone()
                self._running_min[name] = violation.clone()
                continue
            # Polyak-averaged running extremes.
            self._running_max[name] = torch.maximum(
                cfg_item.polyak * self._running_max[name] + (1 - cfg_item.polyak) * violation,
                violation,
            )
            self._running_min[name] = torch.minimum(
                cfg_item.polyak * self._running_min[name] + (1 - cfg_item.polyak) * violation,
                violation,
            )
            span = self._running_max[name] - self._running_min[name]
            degree = torch.where(
                span > 0,
                (self._running_max[name] - violation) / span.clamp(min=1e-8),
                torch.zeros_like(span),
            )
            # Violation above its running min maps to termination probability.
            prob = torch.maximum(
                prob,
                self.min_prob + (violation / (self._running_max[name].clamp(min=1e-8))) * (self.max_prob - self.min_prob),
            )
        self._term_prob = prob
        return prob

    def sample_termination(self, env) -> torch.Tensor:
        """Bernoulli sample of termination per env from the step probability."""
        prob = self.compute(env)
        return torch.rand_like(prob) < prob

    @property
    def term_prob(self) -> torch.Tensor:
        return self._term_prob
