"""Package-local (Go2) robot and experiment discovery.

包自包含约束（B8）：本包只登记 Go2 的机器人域与实验绑定；其他机型的任务源码
属于各自的机器人包，不得在 Go2 包内出现。
"""

from __future__ import annotations

from functools import cache

from local_tasks.core import Catalog, RobotSpec, TaskSpec, TrainingSpec
from local_tasks.integrations.mjlab import MjlabExperimentBinding


@cache
def robot_catalog() -> Catalog[RobotSpec]:
  from local_tasks.robots.unitree.go2 import GO2

  return Catalog((GO2,), id_of=lambda robot: robot.robot_id)


@cache
def experiment_catalog() -> Catalog[MjlabExperimentBinding]:
  from local_tasks.robots.unitree.go2.experiments import GO2_EXPERIMENTS

  return Catalog(
    (*GO2_EXPERIMENTS.values(),),
    id_of=lambda binding: binding.binding_id,
  )


def resolve_robot(robot_id: str) -> RobotSpec:
  # 包自包含：本包只承载 Go2，不得解析其他机型的机器人域。
  aliases = {
    "go2": "unitree/go2",
    "unitree/go2": "unitree/go2",
  }
  try:
    canonical_id = aliases[robot_id.lower()]
  except KeyError as exc:
    choices = ", ".join(robot_catalog().ids())
    raise KeyError(f"Unknown robot {robot_id!r}; choose one of: {choices}") from exc
  return robot_catalog().get(canonical_id)


def task_catalog(robot_id: str) -> Catalog[TaskSpec]:
  resolve_robot(robot_id)
  from local_tasks.robots.unitree.go2.tasks import GO2_TASKS

  return GO2_TASKS


def training_profile_catalog(robot_id: str) -> Catalog[TrainingSpec]:
  resolve_robot(robot_id)
  from local_tasks.robots.unitree.go2.training import GO2_TRAINING_PROFILES

  return GO2_TRAINING_PROFILES


def resolve_experiment(task_id: str, profile_id: str) -> MjlabExperimentBinding:
  return experiment_catalog().get(f"{task_id}::{profile_id}")
