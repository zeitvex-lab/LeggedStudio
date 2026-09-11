from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

import mjlab.tasks  # noqa: F401
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg


class TaskRegistryTest(unittest.TestCase):
  def test_supported_go2w_tasks_visible_by_default(self) -> None:
    tasks = set(list_tasks())
    expected = {
      "go2w-flat",
      "go2w-flat-legs",
      "go2w-flat-legs-omni",
      "go2w-flat-legs-omni-finetune",
      "go2w-rough",
      "go2w-rough-finetune",
    }
    self.assertTrue(expected.issubset(tasks))
    self.assertNotIn("Mjlab-Velocity-Flat-Unitree-Go2W", tasks)

  def test_removed_go2w_experimental_tasks_absent_even_with_opt_in(self) -> None:
    tasks = set(list_tasks(include_experimental=True))
    removed = {
      "go2w-rough-legs-isaac",
      "go2w-rough-legs-isaac-finetune",
      "go2w-rough-hybrid-isaac",
      "go2w-rough-hybrid-isaac-finetune",
      "go2w-stepfield-hybrid",
      "go2w-stepfield-hybrid-finetune",
      "go2w-stepfield-legs",
      "go2w-stepfield-legs-finetune",
    }
    self.assertTrue(removed.isdisjoint(tasks))

  def test_loading_removed_go2w_experimental_task_raises(self) -> None:
    with self.assertRaises(KeyError):
      load_env_cfg("go2w-stepfield-hybrid")

    with self.assertRaises(KeyError):
      load_env_cfg(
        "go2w-stepfield-hybrid",
        include_experimental=True,
      )

  def test_legacy_go2w_aliases_resolve_but_stay_hidden_from_default_listing(self) -> None:
    tasks = set(list_tasks())
    all_names = set(list_tasks(include_aliases=True))
    cases = (
      ("Mjlab-Velocity-Flat-Unitree-Go2W", "go2w-flat"),
      ("Mjlab-Velocity-Rough-Unitree-Go2W", "go2w-rough"),
    )

    for legacy_name, canonical_name in cases:
      with self.subTest(legacy_name=legacy_name):
        self.assertNotIn(legacy_name, tasks)
        self.assertIn(legacy_name, all_names)

        canonical_cfg = load_env_cfg(canonical_name)
        legacy_cfg = load_env_cfg(legacy_name)
        self.assertEqual(
          len(canonical_cfg.actions),
          len(legacy_cfg.actions),
        )

  def test_supported_go2w_tasks_default_to_1000_iteration_checkpoints(self) -> None:
    for task_name in (
      "go2w-flat",
      "go2w-flat-legs",
      "go2w-flat-legs-omni",
      "go2w-flat-legs-omni-finetune",
      "go2w-rough",
      "go2w-rough-finetune",
    ):
      rl_cfg = load_rl_cfg(task_name)
      self.assertEqual(rl_cfg.save_interval, 1000)


if __name__ == "__main__":
  unittest.main()
