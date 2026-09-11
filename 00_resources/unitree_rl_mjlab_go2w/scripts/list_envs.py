"""Script to list mjlab environments."""

import sys
from pathlib import Path

import tyro
from prettytable import PrettyTable

# Ensure script uses local workspace package when invoked as `python scripts/list_envs.py`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

import mjlab.tasks  # noqa: F401
from mjlab.tasks.registry import list_tasks


def list_environments(keyword: str | None = None, experimental: bool = False):
  """List all registered environments.

  Args:
    keyword: Optional filter to only show environments containing this keyword.
    experimental: Include archived experimental tasks in the listing.
  """
  table = PrettyTable(["Index", "Task ID"])
  table.title = "Available Environments in mjlab"
  table.align["Task ID"] = "l"

  all_tasks = list_tasks(include_experimental=experimental)
  match_count = 0
  for idx, task_id in enumerate(all_tasks, start=1):
    try:
      # Optionally filter by keyword.
      if keyword and keyword.lower() not in task_id.lower():
        continue

      table.add_row([idx, task_id])
      match_count += 1
    except Exception:
      continue

  print(table)
  if match_count == 0:
    msg = "[INFO] No tasks matched"
    if keyword:
      msg += f" keyword '{keyword}'"
    print(msg)
  else:
    print(
      "[INFO] Use the Index column with scripts/train.py or scripts/play.py. "
      "Indexes follow the full task order for the current --experimental setting "
      "and are not stable registry IDs."
    )
  return match_count


list_environments.__doc__ = (list_environments.__doc__ or "") + (
  "\n\n  The printed Index column can be passed to scripts/train.py and "
  "scripts/play.py. Indexes are derived from the current task listing, not "
  "stored as permanent registry IDs."
)


def main():
  return tyro.cli(list_environments)


if __name__ == "__main__":
  main()
