"""Small, dependency-free runtime compatibility checks for package profiles.

Robot packages carry their own MJLab task source, so compatibility belongs to
the package manifest rather than to robot-name conditionals in the control
plane.  The checker intentionally accepts a compact PEP 440-like subset
(``>=1.6,<2`` and ``==1.6.0``) and never claims compatibility when the runtime
version cannot be detected.
"""

from __future__ import annotations

import re
from typing import Any


_VERSION_RE = re.compile(r"\d+(?:\.\d+){0,3}")


def _version_tuple(value: str) -> tuple[int, ...] | None:
    match = _VERSION_RE.search(str(value or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    lhs = left + (0,) * (width - len(left))
    rhs = right + (0,) * (width - len(right))
    return (lhs > rhs) - (lhs < rhs)


def satisfies_version(actual: str | None, requirement: str | None) -> bool | None:
    """Return True/False, or None when either value is not parseable."""
    if not requirement:
        return True
    actual_tuple = _version_tuple(actual or "")
    if actual_tuple is None:
        return None
    clauses = [item.strip() for item in str(requirement).split(",") if item.strip()]
    for clause in clauses:
        match = re.match(r"^(>=|<=|==|!=|>|<|~=)?\s*(.+)$", clause)
        if not match:
            return None
        operator = match.group(1) or "=="
        expected = _version_tuple(match.group(2))
        if expected is None:
            return None
        comparison = _compare(actual_tuple, expected)
        if operator == ">=" and comparison < 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator == "==" and comparison != 0:
            return False
        if operator == "!=" and comparison == 0:
            return False
        if operator == "~=" and (comparison < 0 or actual_tuple[: max(1, len(expected) - 1)] != expected[: max(1, len(expected) - 1)]):
            return False
    return True


def runtime_requirements(package: dict[str, Any]) -> dict[str, str]:
    requirements = package.get("runtime_requirements")
    if not isinstance(requirements, dict):
        requirements = package.get("compatibility")
    if not isinstance(requirements, dict):
        return {}
    return {str(key): str(value) for key, value in requirements.items() if value is not None}


def evaluate_package_runtime(package: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    """Evaluate package requirements against a native preflight runtime."""
    requirements = runtime_requirements(package)
    actual = {
        "mjlab": runtime.get("mjlab_version"),
        "python": runtime.get("python_version"),
        "torch": runtime.get("torch_version"),
    }
    checks: list[dict[str, Any]] = []
    unknown = False
    compatible = True
    for name, requirement in requirements.items():
        value = actual.get(name)
        result = satisfies_version(value, requirement)
        if result is None:
            unknown = True
        elif result is False:
            compatible = False
        checks.append({"runtime": name, "required": requirement, "actual": value, "ok": result is True})
    status = "incompatible" if not compatible else "unknown" if unknown else "compatible"
    return {"status": status, "compatible": compatible and not unknown, "requirements": requirements, "checks": checks}
