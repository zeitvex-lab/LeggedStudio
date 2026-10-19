#!/usr/bin/env python3
"""Observation parity gate: family skeleton ↔ contract ↔ generic builder ↔ policy width.

The family skeleton (``registry/families/*.json``) is the single actor layout.
This gate fails when a contract, the generic builder fallback, or a policy
declares a different actor width without an explicit legacy entry in
``registry/observation_legacy_policies.json``.

Usage::

    python tools/audit_observation_parity.py
    python tools/audit_observation_parity.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.observation_contract import (  # noqa: E402
    DEFAULT_ACTOR_TERMS,
    expected_actor_width,
)

ACTOR_WIDTH = {"base_ang_vel": 3, "projected_gravity": 3, "commands": 3}


def _norm(name: str) -> str:
    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    return "commands" if key in {"command", "commands"} else key


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _families() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((ROOT / "registry" / "families").glob("*.json")):
        data = _load(path)
        if isinstance(data, dict):
            out[str(path.stem)] = data
    return out


def _family_for(contract: dict, families: dict[str, dict]) -> tuple[str, dict] | tuple[None, None]:
    morphology = str((contract.get("morphology") or {}).get("id") or "")
    for family_id, family in families.items():
        if morphology in (family.get("morphology_ids") or []):
            return family_id, family
    return None, None


def _contract_components(contract: dict) -> list[dict]:
    raw = (contract.get("observation") or {}).get("components") or []
    out = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        else:
            out.append({"name": str(item), "role": "actor"})
    return out


def _check_contract(robot: str, contract: dict, families: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    family_id, family = _family_for(contract, families)
    if not family:
        return [f"{robot}: no family declaration for morphology {(contract.get('morphology') or {}).get('id')!r}"]
    skeleton = (family.get("observation_skeleton") or {})
    expected_terms = [_norm(term) for term in skeleton.get("actor") or []]
    if not expected_terms:
        return [f"{robot}: family {family_id} has no observation_skeleton.actor"]
    components = _contract_components(contract)
    actor = [item for item in components if str(item.get("role") or "actor") == "actor"]
    names = [_norm(str(item.get("name") or "")) for item in actor]
    if names != expected_terms:
        errors.append(
            f"{robot}: contract actor {names} != family {family_id} skeleton {expected_terms}"
        )
    if "base_lin_vel" in names:
        errors.append(f"{robot}: base_lin_vel must be critic-only, not actor")
    joints = list((contract.get("action") or {}).get("joint_order") or [])
    if not joints:
        errors.append(f"{robot}: action.joint_order is empty")
        return errors
    expected_width = expected_actor_width(len(joints))
    declared_width = (contract.get("observation") or {}).get("dimension")
    if declared_width != expected_width:
        errors.append(
            f"{robot}: contract dimension {declared_width} != expected {expected_width} "
            f"({len(joints)} joints)"
        )
    for item in actor:
        name = _norm(str(item.get("name") or ""))
        width = ACTOR_WIDTH.get(name, len(joints) if name in {"joint_pos", "joint_vel", "last_action"} else None)
        if width is not None and item.get("width") not in (None, width):
            errors.append(f"{robot}: {name} width {item.get('width')} != {width}")
    if skeleton.get("deviations"):
        errors.append(f"{robot}: family {family_id} has non-empty observation deviations: {skeleton['deviations']}")
    return errors


def _check_builder(families: dict[str, dict]) -> list[str]:
    expected = tuple(_norm(term) for term in DEFAULT_ACTOR_TERMS)
    errors = []
    for family_id, family in families.items():
        skeleton = tuple(_norm(term) for term in (family.get("observation_skeleton") or {}).get("actor") or [])
        if skeleton and skeleton != expected:
            errors.append(f"generic builder default {expected} != family {family_id} skeleton {skeleton}")
    return errors


def _check_policies(families: dict[str, dict]) -> tuple[list[str], int, int]:
    index = _load(ROOT / "pretrained_models" / "index.json")
    if not isinstance(index, list):
        return ["pretrained_models/index.json is not a list"], 0, 0
    manifest_path = ROOT / "registry" / "observation_legacy_policies.json"
    legacy = {}
    if manifest_path.is_file():
        manifest = _load(manifest_path)
        legacy = (manifest.get("policies") or {}) if isinstance(manifest, dict) else {}
    errors: list[str] = []
    checked = 0
    allowed_legacy = 0
    for entry in index:
        if not isinstance(entry, dict):
            continue
        robot = str(entry.get("robot") or "")
        policy_id = str(entry.get("id") or "")
        width = entry.get("obs_dim")
        if not robot or not policy_id or not isinstance(width, int):
            continue
        contract_path = ROOT / "assets" / "robots" / robot / "contract.json"
        if not contract_path.is_file():
            errors.append(f"{policy_id}: missing contract for robot {robot}")
            continue
        contract = _load(contract_path)
        family_id, family = _family_for(contract, families)
        if not family:
            errors.append(f"{policy_id}: robot {robot} has no family")
            continue
        joints = list((contract.get("action") or {}).get("joint_order") or [])
        expected = expected_actor_width(len(joints))
        checked += 1
        if width == expected:
            continue
        if width > expected and width % expected == 0:
            continue
        if policy_id in legacy:
            allowed_legacy += 1
            continue
        errors.append(
            f"{policy_id}: obs_dim {width} != standard {expected}"
            f" (family {family_id}, {len(joints)} joints); add a reason to "
            "registry/observation_legacy_policies.json only if it is a documented legacy layout"
        )
    return errors, checked, allowed_legacy


def audit() -> dict:
    families = _families()
    errors = _check_builder(families)
    robots = 0
    for path in sorted((ROOT / "assets" / "robots").glob("*/contract.json")):
        robots += 1
        errors.extend(_check_contract(path.parent.name, _load(path), families))
    policy_errors, policies, legacy = _check_policies(families)
    errors.extend(policy_errors)
    return {
        "families": sorted(families),
        "robots": robots,
        "policies": policies,
        "legacy_policies": legacy,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"families {len(report['families'])} | robots {report['robots']} | policies {report['policies']}"
              f" | legacy policies {report['legacy_policies']} | errors {len(report['errors'])}")
        for error in report["errors"]:
            print(f"  [FAIL] {error}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
