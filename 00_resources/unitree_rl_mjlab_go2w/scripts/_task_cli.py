"""Shared task CLI helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import tyro


class TaskSelectionError(ValueError):
  """Raised when CLI task selection input is invalid."""


@dataclass(frozen=True)
class TaskSelection:
  task_id: str
  remaining_args: list[str]
  requested_selector: str
  used_index: bool = False


def _parse_bool(value: str) -> bool:
  normalized = value.strip().lower()
  if normalized in {"1", "true", "yes", "on"}:
    return True
  if normalized in {"0", "false", "no", "off"}:
    return False
  raise ValueError(f"Invalid boolean value for --experimental: {value!r}")


def consume_experimental_flag(argv: list[str]) -> tuple[bool, list[str]]:
  """Strip `--experimental` from argv before task selection parsing."""
  experimental = False
  remaining_args: list[str] = []

  idx = 0
  while idx < len(argv):
    arg = argv[idx]
    if arg == "--experimental":
      experimental = True
      if idx + 1 < len(argv):
        next_arg = argv[idx + 1].strip().lower()
        if next_arg in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
          experimental = _parse_bool(argv[idx + 1])
          idx += 1
    elif arg.startswith("--experimental="):
      experimental = _parse_bool(arg.split("=", 1)[1])
    else:
      remaining_args.append(arg)
    idx += 1

  return experimental, remaining_args


def _looks_like_int(value: str) -> bool:
  normalized = value.strip()
  if normalized.startswith(("+", "-")):
    normalized = normalized[1:]
  return normalized.isdigit()


def _parse_positive_index(value: str, source: str) -> int:
  if not _looks_like_int(value):
    raise TaskSelectionError(f"{source} expects a positive integer, got {value!r}.")

  task_index = int(value)
  if task_index <= 0:
    raise TaskSelectionError(f"{source} must be greater than or equal to 1.")
  return task_index


def _resolve_task_index(task_index: int, indexed_task_choices: Sequence[str]) -> str:
  if task_index > len(indexed_task_choices):
    raise TaskSelectionError(
      f"Task index {task_index} is out of range for the current task listing "
      f"({len(indexed_task_choices)} task(s))."
    )
  return indexed_task_choices[task_index - 1]


def consume_task_index_flag(argv: list[str]) -> tuple[int | None, list[str]]:
  """Strip `--task-index` from argv before task parsing."""
  task_index: int | None = None
  remaining_args: list[str] = []

  idx = 0
  while idx < len(argv):
    arg = argv[idx]
    parsed_index: int | None = None

    if arg == "--task-index":
      if idx + 1 >= len(argv):
        raise TaskSelectionError("`--task-index` requires a value.")
      parsed_index = _parse_positive_index(argv[idx + 1], "`--task-index`")
      idx += 1
    elif arg.startswith("--task-index="):
      parsed_index = _parse_positive_index(
        arg.split("=", 1)[1],
        "`--task-index`",
      )
    else:
      remaining_args.append(arg)

    if parsed_index is not None:
      if task_index is not None:
        raise TaskSelectionError("`--task-index` may only be provided once.")
      task_index = parsed_index

    idx += 1

  return task_index, remaining_args


def consume_task_selection(
  argv: list[str],
  named_task_choices: Sequence[str],
  indexed_task_choices: Sequence[str],
) -> TaskSelection:
  """Resolve a task from argv using a name, alias, or numeric task index."""
  task_index, remaining_args = consume_task_index_flag(argv)

  if task_index is not None:
    if remaining_args and not remaining_args[0].startswith("-"):
      raise TaskSelectionError(
        "Task selector provided twice. Use either a task name/index or "
        "`--task-index`, not both."
      )
    task_id = _resolve_task_index(task_index, indexed_task_choices)
    return TaskSelection(
      task_id=task_id,
      remaining_args=remaining_args,
      requested_selector=str(task_index),
      used_index=True,
    )

  if remaining_args and _looks_like_int(remaining_args[0]):
    requested_selector = remaining_args[0]
    task_id = _resolve_task_index(
      _parse_positive_index(requested_selector, "Task index"),
      indexed_task_choices,
    )
    return TaskSelection(
      task_id=task_id,
      remaining_args=remaining_args[1:],
      requested_selector=requested_selector,
      used_index=True,
    )

  task_id, remaining_args = tyro.cli(
    tyro.extras.literal_type_from_choices(named_task_choices),
    args=remaining_args,
    add_help=False,
    return_unknown_args=True,
  )
  return TaskSelection(
    task_id=task_id,
    remaining_args=remaining_args,
    requested_selector=task_id,
  )


def normalize_task_name(requested_task_id: str, canonical_task_id: str) -> str:
  """Return canonical task ID and warn when a deprecated alias was used."""
  if requested_task_id != canonical_task_id:
    print(
      f"[WARN] Task '{requested_task_id}' is deprecated; use '{canonical_task_id}' instead."
    )
  return canonical_task_id
