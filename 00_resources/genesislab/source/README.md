GenesisLab Source Layout
========================

This directory contains the Python source code for GenesisLab and related task libraries.
At a high level, it is organized into four main packages:

- `genesislab/`: **core "lab" library** and engine integration
- `genesis_assets/`: robot and environment asset descriptions and configuration parameters
- `genesis_tasks/`: RL task definitions built on top of the lab and assets
- `genesis_rl/`: RL integration layer (interfaces and configs for external RL repos)


genesislab/
-----------

The `genesislab` package is the **core lab**: it provides the main abstractions and engine bindings:

- `engine/`: thin wrappers around the Genesis physics engine, scene management, and simulation utilities
- `envs/`: RL-friendly environment wrappers (MDP-style APIs, vectorized envs, reset/step logic)
- `tasks/`: high-level task registration and configuration hooks
- `cli/`: small command-line utilities and entry points

Most user-facing APIs (e.g., environment creation and stepping) are routed through this package.


genesis_assets/
---------------

The `genesis_assets` package manages robot and environment assets and their configuration parameters:

- `robots/unitree/go2.py`: Genesis asset description and helpers for the Unitree Go2 robot
- additional modules for importing or composing MJCF/URDF assets under `data/assets/`

These assets are used by the core lab to build scenes and by tasks to reference specific robots/layouts.


genesis_tasks/
--------------

The `genesis_tasks` package contains concrete RL **task definitions** built on top of `genesislab`:

- `locomotion/velocity/`: velocity-tracking locomotion tasks
  - `robots/go2/`: Unitree Go2-specific task configurations (flat, rough, etc.)
  - shared components for observations, rewards, and curriculum

These modules define task-specific configs, reward shaping, observation construction, and wrappers that
are then exposed to downstream RL algorithms via the `genesis_rl` integration.


genesis_rl/
-----------

The `genesis_rl` package provides the **RL-facing glue code**:

- environment wrappers and utilities for specific RL libraries (e.g., RSL-RL)
- runner and training configuration templates that point to tasks defined in `genesis_tasks`

This keeps the core lab and tasks RL-agnostic, while offering clean, ready-to-use entry points for
external RL repositories and training scripts (such as those under `scripts/reinforcement_learning/`).


How things fit together
-----------------------

1. **Assets** in `genesis_assets` describe robots and environments.
2. The **core lab** in `genesislab` turns these assets into vectorized RL environments.
3. **Tasks** in `genesis_tasks` define specific RL problems (observations, rewards, configs).
4. **RL integrations** in `genesis_rl` expose these tasks to external RL codebases and training scripts.

This separation keeps the lab core, assets, task logic, and RL integration loosely coupled and easy to extend.


