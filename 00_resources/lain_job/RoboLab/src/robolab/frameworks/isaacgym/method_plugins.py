"""Isaac Gym method plugin loading without importing backend SDKs eagerly."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StandardPPOPlugin:
    method_id: str = "ppo"

    def register_task(self, task_registry: Any, requested_task: str) -> str:
        return requested_task

    def make_runner(
        self, task_registry: Any, env: Any, task: str, runtime_args: Any,
        *, log_dir: str | None, checkpoint: str | None,
    ) -> tuple[Any, Any]:
        return task_registry.make_alg_runner(
            env=env,
            name=task,
            args=runtime_args,
            log_root=log_dir,
            train_path=checkpoint,
        )


def load_method_plugin(method_id: str) -> Any:
    """Load one explicitly selected backend plugin by its stable method ID."""

    if method_id == "ppo":
        return StandardPPOPlugin()
    if method_id not in ("ppo_ee", "dreamwaq", "teacher_student", "cts"):
        raise ValueError("unknown Isaac Gym method %r; choose ppo, ppo_ee, dreamwaq, teacher_student, or cts" % method_id)
    module = importlib.import_module(f"methods.{method_id}")
    plugin = getattr(module, "PLUGIN", None)
    if plugin is None:
        raise RuntimeError(f"Isaac Gym method plugin {method_id!r} does not expose PLUGIN")
    if getattr(plugin, "method_id", None) != method_id:
        raise RuntimeError(f"Isaac Gym method plugin ID mismatch for {method_id!r}")
    return plugin
