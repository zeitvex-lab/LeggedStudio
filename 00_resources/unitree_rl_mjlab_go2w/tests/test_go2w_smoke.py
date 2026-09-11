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


class Go2WSmokeTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    _configure_warp_cache()

  def _smoke_step(self, task_id: str, expected_action_dim: int) -> None:
    cfg = load_env_cfg(task_id)
    cfg.scene.num_envs = 1

    env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
    try:
      action_dim = env.action_space.shape[-1]
      self.assertEqual(action_dim, expected_action_dim)

      obs_dict, _ = env.reset()
      self.assertTrue(torch.isfinite(obs_dict["policy"]).all().item())

      actions = torch.zeros((cfg.scene.num_envs, action_dim), device="cpu")
      obs_dict, rewards, terminated, truncated, _extras = env.step(actions)
      self.assertTrue(torch.isfinite(obs_dict["policy"]).all().item())
      self.assertTrue(torch.isfinite(rewards).all().item())
      self.assertTrue(torch.isfinite(terminated.float()).all().item())
      self.assertTrue(torch.isfinite(truncated.float()).all().item())
    finally:
      env.close()

  def test_supported_go2w_envs_step(self) -> None:
    cases = (
      ("go2w-flat", 16),
      ("go2w-rough", 16),
      ("go2w-flat-legs", 12),
      ("go2w-flat-legs-omni", 12),
    )
    for task_id, action_dim in cases:
      with self.subTest(task_id=task_id):
        self._smoke_step(task_id, action_dim)


if __name__ == "__main__":
  unittest.main()
