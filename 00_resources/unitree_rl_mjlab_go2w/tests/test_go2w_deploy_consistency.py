from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

import mjlab.tasks  # noqa: F401
from mjlab.tasks.registry import load_env_cfg

_HYBRID_DEPLOY = (
  _REPO_ROOT
  / "deploy/robots/go2w/config/policy/velocity/v0/params/deploy.yaml"
)
_LEGS_ONLY_DEPLOY = (
  _REPO_ROOT
  / "deploy/robots/go2w/config/policy/velocity_legs_only/v0/params/deploy.yaml"
)

_TASK_TO_DEPLOY = {
  "go2w-flat": _HYBRID_DEPLOY,
  "go2w-rough": _HYBRID_DEPLOY,
  "go2w-rough-finetune": _HYBRID_DEPLOY,
  "go2w-flat-legs": _LEGS_ONLY_DEPLOY,
  "go2w-flat-legs-omni": _LEGS_ONLY_DEPLOY,
  "go2w-flat-legs-omni-finetune": _LEGS_ONLY_DEPLOY,
}


def _num_selected_joints(asset_cfg) -> int:
  if isinstance(asset_cfg.joint_ids, list):
    return len(asset_cfg.joint_ids)
  if asset_cfg.joint_names is not None:
    return len(asset_cfg.joint_names)
  raise AssertionError("Expected explicit joint selection for Go2-W policy observations.")


def _env_action_dim(cfg) -> int:
  total = 0
  for action_cfg in cfg.actions.values():
    total += len(action_cfg.actuator_names)
  return total


def _env_policy_layout(cfg) -> list[tuple[str, int]]:
  action_dim = _env_action_dim(cfg)
  layout: list[tuple[str, int]] = []
  for name, term_cfg in cfg.observations["policy"].terms.items():
    if name == "base_ang_vel":
      layout.append(("base_ang_vel", 3))
    elif name == "projected_gravity":
      layout.append(("projected_gravity", 3))
    elif name == "command":
      layout.append(("velocity_commands", 3))
    elif name == "joint_pos":
      layout.append(("joint_pos_rel", _num_selected_joints(term_cfg.params["asset_cfg"])))
    elif name == "joint_vel":
      layout.append(("joint_vel_rel", _num_selected_joints(term_cfg.params["asset_cfg"])))
    elif name == "wheel_joint_pos_rel":
      layout.append(("wheel_joint_pos_rel", _num_selected_joints(term_cfg.params["asset_cfg"])))
    elif name == "wheel_joint_vel_rel":
      layout.append(("wheel_joint_vel_rel", _num_selected_joints(term_cfg.params["asset_cfg"])))
    elif name == "actions":
      layout.append(("last_action", action_dim))
    else:
      raise AssertionError(f"Unexpected Go2-W policy observation term: {name}")
  return layout


def _deploy_action_dim(cfg: dict) -> int:
  return sum(len(action_cfg["joint_ids"]) for action_cfg in cfg["actions"].values())


def _deploy_policy_layout(cfg: dict) -> list[tuple[str, int]]:
  return [
    (name, len(term_cfg["scale"]))
    for name, term_cfg in cfg["observations"].items()
  ]


class Go2WDeployConsistencyTest(unittest.TestCase):
  def test_kept_go2w_tasks_match_supported_deploy_profiles(self) -> None:
    for task_id, deploy_path in _TASK_TO_DEPLOY.items():
      with self.subTest(task_id=task_id):
        env_cfg = load_env_cfg(task_id)
        with deploy_path.open("r", encoding="utf-8") as handle:
          deploy_cfg = yaml.safe_load(handle)

        self.assertEqual(_env_action_dim(env_cfg), _deploy_action_dim(deploy_cfg))
        self.assertEqual(_env_policy_layout(env_cfg), _deploy_policy_layout(deploy_cfg))


if __name__ == "__main__":
  unittest.main()
