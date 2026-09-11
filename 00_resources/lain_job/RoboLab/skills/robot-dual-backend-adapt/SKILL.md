---
name: robot-dual-backend-adapt
description: Adapt or add a RoboLab robot asset so Isaac Gym and MJLab can resolve it through the shared asset registry, with validated URDF/MJCF paths and backend-specific task bindings.
---

# Robot Dual-Backend Adaptation

Use this skill when a user asks to add, convert, or make a robot in
`resources/robots` work with both Isaac Gym and MJLab.

## Required outcome

Every robot must be discoverable through `robolab.robots`:

- Isaac Gym resolves a URDF with `isaacgym_asset(robot_id)`.
- MJLab resolves native MJCF/XML when present, otherwise the URDF fallback with
  `mjlab_asset(robot_id)`; do not claim physics parity until a native MJCF is
  validated.
- Backend task adapters must keep joint order, action meaning, control period,
  initial pose, actuator limits, contact bodies, and sensor names explicit.

## Workflow

1. Read the repository `AGENTS.md`, inspect the robot directory, and run:
   `python skills/robot-dual-backend-adapt/scripts/audit_assets.py`.
2. Choose canonical files deterministically. Do not copy meshes or silently
   edit vendor assets. Preserve licenses and add/update `NOTICE.md`.
3. Add or update metadata in `src/robolab/robots/` using the shared registry and
   bindings. Robot-specific semantics belong in `src/robolab/robots/<id>/` and
   backend task code, not in the generic registry.
4. Add/update `src/robolab/robots/profiles.py`. The profile is the single source
   of truth for joint order, default pose/base height, control dt/action scale,
   actuator limits, base/contact/termination bodies, sensors, observations, and
   rewards. Verify every joint against the canonical URDF variant.
5. For Isaac Gym, use `register_semantic_tasks()` to project the profile into a
   flat velocity task, then refine robot-specific gains/contact patterns after a
   one-env reset/step smoke test.
6. For MJLab, prefer a native MJCF and use `make_semantic_env_cfg()`. URDF-only
   assets must remain explicitly unavailable for MJLab training until converted
   and loaded by MuJoCo; do not silently register a false parity task.
7. Add a registry test and backend smoke test. Run the focused tests, then the
   full test suite. Backend integration tests must be marked `integration`.

## Acceptance checklist

- `discover_robot_assets()` lists the robot and both binding functions return
  existing files under `resources/robots`.
- XML/MJCF mesh references are local and loadable; URDF mesh references resolve.
- Joint names and order are recorded once and mapped explicitly in each backend.
- A one-environment reset/step smoke test passes for each configured backend.
- No generated conversion overwrites the source asset; provenance is recorded.

For the detailed validation matrix and conversion decision, read
[`references/validation.md`](references/validation.md). The repeatable inventory
command is [`scripts/audit_assets.py`](scripts/audit_assets.py).
