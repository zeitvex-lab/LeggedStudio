from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

import mjlab.tasks  # noqa: F401
from mjlab.tasks.registry import list_tasks
from scripts._task_cli import TaskSelectionError, consume_task_selection
from scripts.list_envs import list_environments


class TaskCliTest(unittest.TestCase):
  def test_positional_index_resolves_canonical_task(self) -> None:
    indexed_tasks = list_tasks()
    named_tasks = list_tasks(include_aliases=True)
    go2w_flat_index = indexed_tasks.index("go2w-flat") + 1

    selection = consume_task_selection(
      argv=[str(go2w_flat_index), "--help"],
      named_task_choices=named_tasks,
      indexed_task_choices=indexed_tasks,
    )

    self.assertEqual(selection.task_id, "go2w-flat")
    self.assertEqual(selection.remaining_args, ["--help"])
    self.assertTrue(selection.used_index)

  def test_task_index_flag_resolves_canonical_task(self) -> None:
    indexed_tasks = list_tasks()
    named_tasks = list_tasks(include_aliases=True)
    go2w_rough_index = indexed_tasks.index("go2w-rough") + 1

    selection = consume_task_selection(
      argv=["--task-index", str(go2w_rough_index), "--viewer", "viser"],
      named_task_choices=named_tasks,
      indexed_task_choices=indexed_tasks,
    )

    self.assertEqual(selection.task_id, "go2w-rough")
    self.assertEqual(selection.remaining_args, ["--viewer", "viser"])
    self.assertTrue(selection.used_index)

  def test_zero_task_index_is_rejected(self) -> None:
    indexed_tasks = list_tasks()
    named_tasks = list_tasks(include_aliases=True)

    with self.assertRaisesRegex(
      TaskSelectionError,
      "greater than or equal to 1",
    ):
      consume_task_selection(
        argv=["0"],
        named_task_choices=named_tasks,
        indexed_task_choices=indexed_tasks,
      )

  def test_out_of_range_task_index_is_rejected(self) -> None:
    indexed_tasks = list_tasks()
    named_tasks = list_tasks(include_aliases=True)

    with self.assertRaisesRegex(TaskSelectionError, "out of range"):
      consume_task_selection(
        argv=[str(len(indexed_tasks) + 1)],
        named_task_choices=named_tasks,
        indexed_task_choices=indexed_tasks,
      )

  def test_keyword_listing_preserves_global_task_indexes(self) -> None:
    indexed_tasks = list_tasks()
    go2w_tasks = [task_id for task_id in indexed_tasks if "go2w" in task_id]
    expected_rows = {
      task_id: indexed_tasks.index(task_id) + 1
      for task_id in ("go2w-flat", "go2w-rough-finetune")
    }
    output = io.StringIO()

    with mock.patch("sys.stdout", output):
      match_count = list_environments(keyword="go2w")

    rendered = output.getvalue()
    self.assertEqual(match_count, len(go2w_tasks))
    for task_id, task_index in expected_rows.items():
      self.assertRegex(rendered, rf"\|\s*{task_index}\s*\|\s*{task_id}\s*\|")
    self.assertIn("not stable registry IDs", rendered)


if __name__ == "__main__":
  unittest.main()
