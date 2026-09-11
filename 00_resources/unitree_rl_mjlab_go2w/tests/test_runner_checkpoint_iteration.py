from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

from mjlab.rsl_rl.runners.distillation_runner import DistillationRunner
from mjlab.rsl_rl.runners.on_policy_runner import OnPolicyRunner


class _DummyPolicy:
  def __init__(self, *, loaded_teacher: bool = True) -> None:
    self.loaded_teacher = loaded_teacher

  def train(self) -> None:
    pass


class _DummyAlgorithm:
  def __init__(self, *, loaded_teacher: bool = True) -> None:
    self.policy = _DummyPolicy(loaded_teacher=loaded_teacher)
    self.rnd = False

  def act(self, obs: torch.Tensor) -> torch.Tensor:
    return torch.zeros((1, 1), dtype=torch.float32)

  def process_env_step(
    self,
    obs: torch.Tensor,
    rewards: torch.Tensor,
    dones: torch.Tensor,
    extras: dict,
  ) -> None:
    del obs, rewards, dones, extras

  def compute_returns(self, obs: torch.Tensor) -> None:
    del obs

  def update(self) -> dict:
    return {}


class _DummyEnv:
  def __init__(self) -> None:
    self.num_envs = 1
    self.num_actions = 1
    self.max_episode_length = 1
    self.episode_length_buf = torch.zeros((1, 1), dtype=torch.int64)
    self.device = "cpu"

  def get_observations(self) -> torch.Tensor:
    return torch.zeros((1, 1), dtype=torch.float32)

  def step(self, actions: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, dict]:
    del actions
    obs = torch.zeros((1, 1), dtype=torch.float32)
    rewards = torch.ones(1, dtype=torch.float32)
    dones = torch.ones(1, dtype=torch.int64)
    return obs, rewards, dones, {}


class RunnerCheckpointIterationTest(unittest.TestCase):
  def _make_runner(
    self,
    runner_cls: type[OnPolicyRunner] | type[DistillationRunner],
    *,
    save_interval: int,
    start_iter: int = 0,
  ) -> tuple[OnPolicyRunner | DistillationRunner, list[str]]:
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)

    saved_paths: list[str] = []
    runner = runner_cls.__new__(runner_cls)
    runner.cfg = {"logger": "tensorboard"}
    runner.alg_cfg = {}
    runner.policy_cfg = {}
    runner.device = "cpu"
    runner.env = _DummyEnv()
    runner.num_steps_per_env = 1
    runner.save_interval = save_interval
    runner.alg = _DummyAlgorithm()
    runner.disable_logs = False
    runner.log_dir = tmpdir.name
    runner.writer = None
    runner.logger_type = "tensorboard"
    runner.tot_timesteps = 0
    runner.tot_time = 0
    runner.current_learning_iteration = start_iter
    runner.git_status_repos = []
    runner.is_distributed = False
    runner.gpu_global_rank = 0
    runner.gpu_world_size = 1
    runner._prepare_logging_writer = lambda: None
    runner.train_mode = lambda: None
    runner.log = lambda locs: None
    runner.save = lambda path, infos=None: saved_paths.append(Path(path).name)
    return runner, saved_paths

  def test_runners_save_inclusive_zero_based_checkpoints(self) -> None:
    cases = (
      (OnPolicyRunner, "mjlab.rsl_rl.runners.on_policy_runner.store_code_state"),
      (DistillationRunner, "mjlab.rsl_rl.runners.distillation_runner.store_code_state"),
    )
    expected = ["model_0.pt", "model_2.pt", "model_4.pt", "model_5.pt"]

    for runner_cls, patch_target in cases:
      with self.subTest(runner=runner_cls.__name__):
        runner, saved_paths = self._make_runner(runner_cls, save_interval=2)

        with mock.patch(patch_target, return_value=[]):
          runner.learn(num_learning_iterations=5)

        self.assertEqual(saved_paths, expected)
        self.assertEqual(runner.current_learning_iteration, 5)

  def test_runners_skip_duplicate_final_checkpoint_when_interval_matches_end(self) -> None:
    cases = (
      (OnPolicyRunner, "mjlab.rsl_rl.runners.on_policy_runner.store_code_state"),
      (DistillationRunner, "mjlab.rsl_rl.runners.distillation_runner.store_code_state"),
    )
    expected = ["model_0.pt", "model_5.pt"]

    for runner_cls, patch_target in cases:
      with self.subTest(runner=runner_cls.__name__):
        runner, saved_paths = self._make_runner(runner_cls, save_interval=5)

        with mock.patch(patch_target, return_value=[]):
          runner.learn(num_learning_iterations=5)

        self.assertEqual(saved_paths, expected)
        self.assertEqual(saved_paths.count("model_5.pt"), 1)


if __name__ == "__main__":
  unittest.main()
