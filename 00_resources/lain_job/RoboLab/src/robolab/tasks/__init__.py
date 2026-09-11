"""Public task contracts and recipe resolution."""

from .registry import TaskSpec, get_task_spec, list_task_specs, resolve_training_recipe

__all__ = ["TaskSpec", "get_task_spec", "list_task_specs", "resolve_training_recipe"]
