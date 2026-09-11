"""Built-in workflows; backend work remains in framework runtimes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from robolab.core.contracts import PolicyArtifact, TensorContract
from robolab.frameworks.isaacgym.runtime import run_isaacgym_evaluate, run_isaacgym_train
from robolab.frameworks.mjlab.runtime import run_mjlab_evaluate, run_mjlab_train
from robolab.robots.unitree_a1.spec import UNITREE_A1_JOINT_ORDER
from robolab.tasks import resolve_training_recipe

from .interface import WorkflowResult
from .registry import register_workflow


def _framework(value: str) -> str:
    if value not in ("isaacgym", "mjlab"):
        raise ValueError("framework must be isaacgym or mjlab")
    return value


def _train(**kwargs: Any) -> dict[str, Any]:
    recipe_path = kwargs.pop("recipe_path", None)
    if recipe_path:
        resolved = resolve_training_recipe(kwargs)
        kwargs = {
            "framework": resolved["framework"],
            "task": resolved["backend_task"],
            "method": resolved["method"],
            "num_envs": resolved["num_envs"],
            "device": resolved["device"],
            "seed": resolved["seed"],
            "max_iterations": resolved["max_iterations"],
            "checkpoint_interval": resolved["checkpoint_interval"],
            "run_dir": resolved["run_dir"],
            "resume_from": resolved.get("resume_from"),
            "recipe_path": recipe_path,
        }
    framework = _framework(kwargs.pop("framework"))
    if "task" in kwargs:
        kwargs["task_id"] = kwargs.pop("task")
    if framework == "isaacgym":
        return run_isaacgym_train(method_id=kwargs.pop("method", "ppo"), **kwargs)
    if kwargs.pop("method", "ppo") != "ppo":
        raise ValueError("MJLab train workflow currently supports method=ppo only")
    return run_mjlab_train(**kwargs)


class TrainWorkflow:
    name = "train"
    description = "Run one backend training job and return its run/checkpoint outputs."

    def run(self, **kwargs: Any) -> WorkflowResult:
        # Robot is recipe metadata; backend runtimes receive the resolved task.
        kwargs.pop("robot", None)
        return WorkflowResult(self.name, "completed", _train(**dict(kwargs)))


class ReproduceWorkflow:
    name = "reproduce"
    description = "Launch a reproducible method recipe through the train runtime."

    def run(self, **kwargs: Any) -> WorkflowResult:
        kwargs.pop("robot", None)
        result = _train(**dict(kwargs))
        return WorkflowResult(self.name, "completed", {"recipe": kwargs, **result})


class EvaluateWorkflow:
    name = "evaluate"
    description = "Evaluate a checkpoint in an independent backend worker."

    def run(self, **kwargs: Any) -> WorkflowResult:
        framework = _framework(kwargs.pop("framework"))
        checkpoint = kwargs.pop("checkpoint")
        if "task" in kwargs:
            kwargs["task_id"] = kwargs.pop("task")
        if framework == "isaacgym":
            result = run_isaacgym_evaluate(checkpoint, method_id=kwargs.pop("method", "ppo"), **kwargs)
        else:
            if kwargs.pop("method", "ppo") != "ppo":
                raise ValueError("MJLab evaluate workflow currently supports method=ppo only")
            result = run_mjlab_evaluate(checkpoint, **kwargs)
        return WorkflowResult(self.name, "completed", result)


class ExportWorkflow:
    name = "export"
    description = "Create a validated PolicyArtifact manifest beside a checkpoint."

    def run(self, **kwargs: Any) -> WorkflowResult:
        checkpoint = Path(kwargs["checkpoint"]).expanduser().resolve()
        if not checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint does not exist: {checkpoint}")
        config_path = checkpoint.parent / "resolved_config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"resolved config does not exist: {config_path}")
        config = json.loads(config_path.read_text())
        task = str(config.get("task", kwargs.get("task", "unknown")))
        method = str(config.get("method", kwargs.get("method", "ppo")))
        framework = str(config.get("framework", kwargs.get("framework", "unknown")))
        robot = str(kwargs.get("robot", "unitree_a1"))
        action_dim = 12 if robot == "unitree_a1" else int(kwargs.get("action_dim", 0))
        if action_dim <= 0:
            raise ValueError("export requires a known positive action_dim")
        artifact = PolicyArtifact(
            policy_path=str(checkpoint), robot=robot, task=task, method=method, framework=framework,
            observation=TensorContract("actor_observation", (45,), semantics="policy input"),
            action=TensorContract("action", (action_dim,), semantics="joint target action"),
            control_dt=float(kwargs.get("control_dt", 0.02)),
            joint_order=tuple(UNITREE_A1_JOINT_ORDER) if robot == "unitree_a1" else tuple(),
            metadata={"source_config": str(config_path), "manifest_version": 1},
        )
        output = Path(kwargs.get("output") or checkpoint.parent / "policy_artifact.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n")
        return WorkflowResult(self.name, "completed", {"artifact": str(output.resolve()), "policy_artifact": artifact.to_dict()})


for _workflow in (TrainWorkflow(), ReproduceWorkflow(), EvaluateWorkflow(), ExportWorkflow()):
    register_workflow(_workflow)
