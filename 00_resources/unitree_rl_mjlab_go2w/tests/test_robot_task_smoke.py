from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

import mjlab.tasks  # noqa: F401
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg


def _configure_warp_cache() -> Path:
  cache_dir = _REPO_ROOT / ".warp_cache"
  cache_dir.mkdir(parents=True, exist_ok=True)
  os.environ["WARP_CACHE_DIR"] = str(cache_dir)

  import warp

  warp.config.kernel_cache_dir = str(cache_dir)
  return cache_dir


class RobotTaskSmokeTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    _configure_warp_cache()

  def _smoke_step(self, task_id: str, *, motion_file: Path | None = None) -> None:
    cfg = load_env_cfg(task_id)
    cfg.scene.num_envs = 1
    if motion_file is not None:
      cfg.commands["motion"].motion_file = str(motion_file)

    env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
    try:
      obs_dict, _ = env.reset()
      self.assertTrue(torch.isfinite(obs_dict["policy"]).all().item())

      action_dim = env.action_space.shape[-1]
      actions = torch.zeros((cfg.scene.num_envs, action_dim), device="cpu")
      obs_dict, rewards, terminated, truncated, _extras = env.step(actions)
      self.assertTrue(torch.isfinite(obs_dict["policy"]).all().item())
      self.assertTrue(torch.isfinite(rewards).all().item())
      self.assertTrue(torch.isfinite(terminated.float()).all().item())
      self.assertTrue(torch.isfinite(truncated.float()).all().item())
    finally:
      env.close()

  def test_go2_velocity_env_steps(self) -> None:
    self._smoke_step("Mjlab-Velocity-Flat-Unitree-Go2")

  def test_humanoid_velocity_env_steps(self) -> None:
    self._smoke_step("Mjlab-Velocity-Flat-Unitree-H1_2")

  def test_tracking_env_steps_with_demo_motion(self) -> None:
    motion_file = (
      _REPO_ROOT
      / "deploy/robots/g1/config/policy/mimic/dance1_subject2/params/dance1_subject2.npz"
    )
    self.assertTrue(motion_file.exists(), f"Missing motion file fixture: {motion_file}")
    self._smoke_step("Mjlab-Tracking-Flat-Unitree-G1", motion_file=motion_file)


if __name__ == "__main__":
  unittest.main()
