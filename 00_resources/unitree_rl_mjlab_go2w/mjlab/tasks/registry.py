"""Task registry system for managing environment registration and creation."""

from copy import deepcopy
from dataclasses import dataclass

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg


@dataclass
class _TaskCfg:
  env_cfg: ManagerBasedRlEnvCfg
  play_env_cfg: ManagerBasedRlEnvCfg
  rl_cfg: RslRlOnPolicyRunnerCfg
  runner_cls: type | None
  experimental: bool = False
  aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskResolution:
  requested_task_id: str
  task_id: str
  used_alias: bool
  experimental: bool


# Private module-level registry: task_id -> task config.
_REGISTRY: dict[str, _TaskCfg] = {}
_ALIASES: dict[str, str] = {}


def register_mjlab_task(
  task_id: str,
  env_cfg: ManagerBasedRlEnvCfg,
  play_env_cfg: ManagerBasedRlEnvCfg,
  rl_cfg: RslRlOnPolicyRunnerCfg,
  runner_cls: type | None = None,
  experimental: bool = False,
  aliases: tuple[str, ...] | list[str] | None = None,
) -> None:
  """Register an environment task.

  Args:
    task_id: Canonical unique task identifier (e.g., "go2w-rough").
    env_cfg: Environment configuration used for training.
    play_env_cfg: Environment configuration in "play" mode.
    rl_cfg: RL runner configuration.
    runner_cls: Optional custom runner class. If None, uses OnPolicyRunner.
    experimental: Whether this task should be hidden from the default CLI/task
      surface unless explicitly enabled.
    aliases: Optional backwards-compatible task identifiers accepted during
      task lookup but hidden from the default CLI/task surface.
  """
  if task_id in _REGISTRY or task_id in _ALIASES:
    raise ValueError(f"Task '{task_id}' is already registered")
  task_aliases = tuple(aliases or ())
  for alias in task_aliases:
    if alias == task_id:
      raise ValueError(f"Task alias '{alias}' duplicates canonical task ID")
    if alias in _REGISTRY or alias in _ALIASES:
      raise ValueError(f"Task alias '{alias}' is already registered")
  _REGISTRY[task_id] = _TaskCfg(
    env_cfg,
    play_env_cfg,
    rl_cfg,
    runner_cls,
    experimental=experimental,
    aliases=task_aliases,
  )
  for alias in task_aliases:
    _ALIASES[alias] = task_id


def resolve_task_name(
  task_name: str,
  include_experimental: bool = False,
) -> TaskResolution:
  canonical_task_id = _ALIASES.get(task_name, task_name)

  try:
    task_cfg = _REGISTRY[canonical_task_id]
  except KeyError as exc:
    raise KeyError(f"Task '{task_name}' is not registered") from exc

  if task_cfg.experimental and not include_experimental:
    raise KeyError(
      f"Task '{task_name}' is experimental. Re-run with explicit experimental "
      "task opt-in to access it."
    )
  return TaskResolution(
    requested_task_id=task_name,
    task_id=canonical_task_id,
    used_alias=canonical_task_id != task_name,
    experimental=task_cfg.experimental,
  )


def _get_task_cfg(task_name: str, include_experimental: bool = False) -> _TaskCfg:
  resolution = resolve_task_name(
    task_name,
    include_experimental=include_experimental,
  )
  return _REGISTRY[resolution.task_id]


def is_task_experimental(task_name: str) -> bool:
  """Return whether a task is registered as experimental."""
  return resolve_task_name(task_name, include_experimental=True).experimental


def list_tasks(
  include_experimental: bool = False,
  include_aliases: bool = False,
) -> list[str]:
  """List registered task IDs."""
  task_ids: list[str] = []
  for task_id, task_cfg in _REGISTRY.items():
    if not include_experimental and task_cfg.experimental:
      continue
    task_ids.append(task_id)
    if include_aliases:
      task_ids.extend(task_cfg.aliases)
  return sorted(task_ids)


def load_env_cfg(
  task_name: str,
  play: bool = False,
  include_experimental: bool = False,
) -> ManagerBasedRlEnvCfg:
  """Load environment configuration for a task.

  Returns a deep copy to prevent mutation of the registered config.
  """
  task_cfg = _get_task_cfg(task_name, include_experimental=include_experimental)
  return deepcopy(
    task_cfg.env_cfg if not play else task_cfg.play_env_cfg
  )


def load_rl_cfg(
  task_name: str,
  include_experimental: bool = False,
) -> RslRlOnPolicyRunnerCfg:
  """Load RL configuration for a task.

  Returns a deep copy to prevent mutation of the registered config.
  """
  return deepcopy(
    _get_task_cfg(task_name, include_experimental=include_experimental).rl_cfg
  )


def load_runner_cls(
  task_name: str,
  include_experimental: bool = False,
) -> type | None:
  """Load the runner class for a task.

  If None, the default OnPolicyRunner will be used.
  """
  return _get_task_cfg(task_name, include_experimental=include_experimental).runner_cls
