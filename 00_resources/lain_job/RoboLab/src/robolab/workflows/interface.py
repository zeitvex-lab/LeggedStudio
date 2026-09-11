"""Framework-neutral contracts for executable RoboLab workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkflowResult:
    workflow: str
    status: str
    outputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"workflow": self.workflow, "status": self.status, **self.outputs}


class Workflow(Protocol):
    name: str
    description: str

    def run(self, **kwargs: Any) -> WorkflowResult:
        ...
