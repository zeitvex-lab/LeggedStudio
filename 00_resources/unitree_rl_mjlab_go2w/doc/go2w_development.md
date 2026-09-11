# Go2-W Developer Guide

This repo treats `Go2-W` as a peer robot family with its own asset, task, and
deploy paths. `README.md` is the user-facing workflow entrypoint; this file is
only for Go2-W-specific maintenance guidance.

## Current Task Surface

Supported canonical task IDs:

- `go2w-flat`
- `go2w-rough`
- `go2w-rough-finetune`
- `go2w-flat-legs`
- `go2w-flat-legs-omni`
- `go2w-flat-legs-omni-finetune`

These are the only Go2-W task IDs shown by default in `list_envs.py`,
`train.py`, and `play.py`.

Legacy long-form `Mjlab-*` Go2-W names still resolve as deprecated
compatibility aliases, but they stay hidden from default task listings.

The older Go2-W experimental families were removed during the task-package
refactor. `--experimental` does not restore the old Isaac or step-field Go2-W
variants.

## Ownership

- Robot assets and constants live under:
  - `mjlab/asset_zoo/robots/unitree_go2w/`
- Active Go2-W task registration, env builders, and runner configs live under:
  - `mjlab/tasks/robots/unitree_go2w/velocity/`
- Go2-W-specific observations, rewards, commands, and terminations live under:
  - `mjlab/tasks/robots/unitree_go2w/velocity/mdp/`
- Go2-W deploy code and policy configs live under:
  - `deploy/robots/go2w/`

Do not add new Go2-W-only logic back under the removed legacy layout such as
`mjlab/tasks/velocity/config/go2w/` or `mjlab/tasks/velocity/go2w_mdp.py`.

Generic `mjlab/tasks/velocity/mdp/` modules are for reusable cross-robot logic
only. Keep Go2-W-specific behavior in the robot-owned package unless it is
clearly shared.

## Where To Put New Work

- New robot meshes, MJCF changes, joint naming changes, or packaging updates:
  - `mjlab/asset_zoo/robots/unitree_go2w/`
- Supported task IDs and compatibility aliases:
  - `mjlab/tasks/robots/unitree_go2w/velocity/__init__.py`
- Task composition, action layout, terrain wiring, and policy observation shape:
  - `mjlab/tasks/robots/unitree_go2w/velocity/base.py`
  - `mjlab/tasks/robots/unitree_go2w/velocity/env_cfgs.py`
  - `mjlab/tasks/robots/unitree_go2w/velocity/velocity_env_cfg.py`
- Go2-W-only rewards, observations, commands, curricula, and terminations:
  - `mjlab/tasks/robots/unitree_go2w/velocity/mdp/`
- PPO defaults and finetune behavior:
  - `mjlab/tasks/robots/unitree_go2w/velocity/rl_cfg.py`
- Deploy runtime, action split, and policy/deploy parity:
  - `deploy/robots/go2w/src/State_RLBase.cpp`
  - `deploy/robots/go2w/config/policy/`

Do not add Go2-W policy configs, runtime logic, or comments under
`deploy/robots/go2/`.

## Asset Provenance

The vendored Go2-W MJCF and meshes come from `unitree_mujoco`. Keep that
provenance explicit when updating the model or adapting actuator packaging.

## Verification

Run these after changing Go2-W task IDs, registry behavior, or deploy configs:

```bash
python scripts/list_envs.py
python scripts/train.py go2w-flat --help
python scripts/play.py go2w-flat --help
python -m unittest tests.test_task_registry tests.test_go2w_deploy_consistency -v
```

Run this as well after changing Go2-W assets or policy observation or action
surfaces:

```bash
python -m unittest tests.test_go2w_smoke -v
```

If you move or delete task modules, also run:

```bash
python -m unittest tests.test_robot_task_imports -v
```

The smoke tests use a repo-local `.warp_cache/` so they can run in restricted
environments.
