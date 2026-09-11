from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))


class RobotTaskCanonicalImportTest(unittest.TestCase):
  def test_canonical_velocity_imports_succeed(self) -> None:
    from mjlab.tasks.robots.unitree_g1.velocity.env_cfgs import (
      unitree_g1_flat_env_cfg,
      unitree_g1_rough_env_cfg,
    )
    from mjlab.tasks.robots.unitree_g1.velocity.rl_cfg import (
      unitree_g1_ppo_runner_cfg,
    )
    from mjlab.tasks.robots.unitree_g1_23dof.velocity.env_cfgs import (
      unitree_g1_23dof_flat_env_cfg,
      unitree_g1_23dof_rough_env_cfg,
    )
    from mjlab.tasks.robots.unitree_g1_23dof.velocity.rl_cfg import (
      unitree_g1_23dof_ppo_runner_cfg,
    )
    from mjlab.tasks.robots.unitree_go2.velocity.env_cfgs import (
      unitree_go2_flat_env_cfg,
      unitree_go2_rough_env_cfg,
    )
    from mjlab.tasks.robots.unitree_go2.velocity.rl_cfg import (
      unitree_go2_ppo_runner_cfg,
    )
    from mjlab.tasks.robots.unitree_h1_2.velocity.env_cfgs import (
      unitree_h1_2_flat_env_cfg,
      unitree_h1_2_rough_env_cfg,
    )
    from mjlab.tasks.robots.unitree_h1_2.velocity.rl_cfg import (
      unitree_h1_2_ppo_runner_cfg,
    )
    self.assertTrue(callable(unitree_go2_flat_env_cfg))
    self.assertTrue(callable(unitree_go2_rough_env_cfg))
    self.assertTrue(callable(unitree_go2_ppo_runner_cfg))
    self.assertTrue(callable(unitree_g1_flat_env_cfg))
    self.assertTrue(callable(unitree_g1_rough_env_cfg))
    self.assertTrue(callable(unitree_g1_ppo_runner_cfg))
    self.assertTrue(callable(unitree_g1_23dof_flat_env_cfg))
    self.assertTrue(callable(unitree_g1_23dof_rough_env_cfg))
    self.assertTrue(callable(unitree_g1_23dof_ppo_runner_cfg))
    self.assertTrue(callable(unitree_h1_2_flat_env_cfg))
    self.assertTrue(callable(unitree_h1_2_rough_env_cfg))
    self.assertTrue(callable(unitree_h1_2_ppo_runner_cfg))

  def test_canonical_go2w_imports_succeed(self) -> None:
    from mjlab.tasks.robots.unitree_go2w.velocity.env_cfgs import (
      unitree_go2w_flat_env_cfg,
      unitree_go2w_flat_legs_only_env_cfg,
      unitree_go2w_flat_legs_only_omni_env_cfg,
      unitree_go2w_rough_env_cfg,
    )
    from mjlab.tasks.robots.unitree_go2w.velocity.rl_cfg import (
      make_go2w_runner_cfg,
      unitree_go2w_flat_legs_only_omni_finetune_ppo_runner_cfg,
      unitree_go2w_flat_legs_only_omni_ppo_runner_cfg,
      unitree_go2w_flat_legs_only_ppo_runner_cfg,
      unitree_go2w_ppo_runner_cfg,
      unitree_go2w_rough_finetune_ppo_runner_cfg,
      unitree_go2w_rough_ppo_runner_cfg,
    )
    self.assertTrue(callable(unitree_go2w_flat_env_cfg))
    self.assertTrue(callable(unitree_go2w_rough_env_cfg))
    self.assertTrue(callable(unitree_go2w_flat_legs_only_env_cfg))
    self.assertTrue(callable(unitree_go2w_flat_legs_only_omni_env_cfg))
    self.assertTrue(callable(make_go2w_runner_cfg))
    self.assertTrue(callable(unitree_go2w_ppo_runner_cfg))
    self.assertTrue(callable(unitree_go2w_rough_ppo_runner_cfg))
    self.assertTrue(callable(unitree_go2w_rough_finetune_ppo_runner_cfg))
    self.assertTrue(callable(unitree_go2w_flat_legs_only_ppo_runner_cfg))
    self.assertTrue(callable(unitree_go2w_flat_legs_only_omni_ppo_runner_cfg))
    self.assertTrue(
      callable(unitree_go2w_flat_legs_only_omni_finetune_ppo_runner_cfg)
    )

  def test_canonical_tracking_imports_succeed(self) -> None:
    from mjlab.tasks.robots.unitree_g1.tracking.env_cfgs import (
      unitree_g1_flat_tracking_env_cfg,
    )
    from mjlab.tasks.robots.unitree_g1.tracking.rl_cfg import (
      unitree_g1_tracking_ppo_runner_cfg,
    )

    self.assertTrue(callable(unitree_g1_flat_tracking_env_cfg))
    self.assertTrue(callable(unitree_g1_tracking_ppo_runner_cfg))

  def test_canonical_go2w_mdp_imports_succeed(self) -> None:
    from mjlab.tasks.robots.unitree_go2w.velocity.mdp import (
      adaptive_leg_motion_penalty,
      base_height_tracking,
      contact_fraction_reward,
      leg_motion_penalty,
      wheel_joint_pos_rel,
      wheel_joint_vel_rel,
      wheel_roll_tracking,
      wheel_speed_limit_penalty,
    )

    self.assertTrue(callable(wheel_joint_pos_rel))
    self.assertTrue(callable(wheel_joint_vel_rel))
    self.assertTrue(callable(wheel_roll_tracking))
    self.assertTrue(callable(wheel_speed_limit_penalty))
    self.assertTrue(callable(leg_motion_penalty))
    self.assertTrue(callable(adaptive_leg_motion_penalty))
    self.assertTrue(callable(contact_fraction_reward))
    self.assertTrue(callable(base_height_tracking))

  def test_removed_legacy_task_modules_are_absent(self) -> None:
    removed_modules = (
      "mjlab.tasks.velocity.config",
      "mjlab.tasks.velocity.config.g1",
      "mjlab.tasks.velocity.config.g1.env_cfgs",
      "mjlab.tasks.velocity.config.g1_23dof",
      "mjlab.tasks.velocity.config.g1_23dof.env_cfgs",
      "mjlab.tasks.velocity.config.go2",
      "mjlab.tasks.velocity.config.go2.env_cfgs",
      "mjlab.tasks.velocity.config.go2w",
      "mjlab.tasks.velocity.config.go2w.env_cfgs",
      "mjlab.tasks.velocity.config.h1_2",
      "mjlab.tasks.velocity.config.h1_2.env_cfgs",
      "mjlab.tasks.tracking.config",
      "mjlab.tasks.tracking.config.g1",
      "mjlab.tasks.tracking.config.g1.env_cfgs",
      "mjlab.tasks.velocity.go2w_mdp",
      "mjlab.tasks.velocity.velocity_env_cfg",
      "mjlab.tasks.tracking.tracking_env_cfg",
      "mjlab.tasks.velocity.config.go2w.experimental_env_cfgs",
      "mjlab.tasks.velocity.config.go2w.experimental_rl_cfg",
      "mjlab.tasks.velocity.config.go2w.experimental_tasks",
      "mjlab.tasks.velocity.config.go2w.supported_env_cfgs",
      "mjlab.tasks.velocity.config.go2w.supported_rl_cfg",
      "mjlab.tasks.velocity.config.go2w.supported_tasks",
    )
    for module_name in removed_modules:
      with self.subTest(module_name=module_name):
        with self.assertRaises(ModuleNotFoundError):
          importlib.import_module(module_name)


if __name__ == "__main__":
  unittest.main()
