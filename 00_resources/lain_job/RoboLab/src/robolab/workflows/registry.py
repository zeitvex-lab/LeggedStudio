"""Registry for executable RoboLab workflows."""

from __future__ import annotations

from typing import Any

from .interface import Workflow

_WORKFLOWS: dict[str, Workflow] = {}


def register_workflow(workflow: Workflow) -> Workflow:
    if not getattr(workflow, "name", "").strip():
        raise ValueError("workflow name must be non-empty")
    if workflow.name in _WORKFLOWS:
        raise ValueError(f"workflow already registered: {workflow.name}")
    _WORKFLOWS[workflow.name] = workflow
    return workflow


def get_workflow(name: str) -> Workflow:
    try:
        return _WORKFLOWS[name]
    except KeyError as exc:
        available = ", ".join(list_workflows()) or "<none>"
        raise KeyError(f"unknown workflow {name!r}; available: {available}") from exc


def list_workflows() -> tuple[str, ...]:
    return tuple(sorted(_WORKFLOWS))


def run_workflow(name: str, **kwargs: Any) -> WorkflowResult:
    return get_workflow(name).run(**kwargs)
