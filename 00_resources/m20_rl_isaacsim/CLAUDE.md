# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reinforcement learning training library for Deep Robotics robots (Lite3 quadruped, M20 wheeled-legged robot), built on IsaacLab 2.3.2 / Isaac Sim 5.1.0.

## Key Commands

```bash
# Install the library (after IsaacLab is installed)
python -m pip install -e source/rl_training

# List registered environments
python scripts/tools/list_envs.py

# Train Lite3
python scripts/reinforcement_learning/rsl_rl/train.py --task=Rough-Deeprobotics-Lite3-v0 --headless

# Train M20
python scripts/reinforcement_learning/rsl_rl/train.py --task=Rough-Deeprobotics-M20-v0 --headless

# Play (with single robot keyboard control: --keyboard)
python scripts/reinforcement_learning/rsl_rl/play.py --task=Rough-Deeprobotics-Lite3-v0 --num_envs=10

# Common play args: --load_run <folder> --checkpoint model.pt --video --video_length 200 --num_envs 32

# Resume training
python scripts/reinforcement_learning/rsl_rl/train.py --task=Rough-Deeprobotics-Lite3-v0 --headless --resume --load_run <folder> --checkpoint model.pt

# Multi-GPU
python -m torch.distributed.run --nnodes=1 --nproc_per_node=2 scripts/reinforcement_learning/rsl_rl/train.py --task=Rough-Deeprobotics-Lite3-v0 --headless --distributed --num_envs=2048

# ONNX export (no Isaac Sim required)
python scripts/tools/export_onnx_fast.py --checkpoint_path <path.pt> --robot lite3 --output_path exported/policy.onnx

# Compare training run configs
python scripts/tools/compare_runs.py <run1_dir> <run2_dir>

# TensorBoard
tensorboard --logdir=logs
```

## Project Structure

```
source/rl_training/rl_training/
├── assets/
│   ├── __init__.py          # Data dir pointing to deep_robotics_model submodule
│   └── deeprobotics.py      # ArticulationCfg for Lite3 & M20 (actuators, init state, USD paths)
│
├── tasks/
│   ├── __init__.py          # Auto-imports all sub-packages to register Gym envs
│   └── manager_based/locomotion/velocity/
│       ├── velocity_env_cfg.py     # Base env config: scene, obs, actions, rewards, events, terminations, curriculum
│       ├── mdp/                    # Custom MDP terms (extend isaaclab.envs.mdp)
│       │   ├── commands.py         # UniformThresholdVelocityCommand, DiscreteCommandController
│       │   ├── observations.py     # joint_pos_rel_without_wheel, phase
│       │   ├── rewards.py          # Velocity tracking, gait, foot contact/height/slide, mirror, penalty terms
│       │   ├── events.py           # Inertia/COM randomization, bad_orientation_2 termination
│       │   └── curriculums.py      # command_levels_vel curriculum
│       └── config/
│           ├── quadruped/deeprobotics_lite3/   # Lite3 env + PPO configs (Rough, Flat)
│           ├── wheeled/deeprobotics_m20/        # M20 env + PPO configs (Rough, Flat, FixedObstacle, Perception)
│
scripts/
├── reinforcement_learning/rsl_rl/
│   ├── train.py              # Training entry point (Isaac Sim + RSL-RL)
│   ├── play.py               # Inference/playback entry point (supports --keyboard)
│   └── cli_args.py            # RSL-RL CLI argument parsing
└── tools/
    ├── export_onnx_fast.py   # ONNX export from .pt without Isaac Sim
    ├── compare_runs.py       # Diff agent.yaml/env.yaml between runs
    └── list_envs.py          # Print registered Deep Robotics environments
```

## Architecture Patterns

### Environment Registration
Gym environments are registered in robot-specific `__init__.py` files (e.g. `config/quadruped/deeprobotics_lite3/__init__.py`). The parent `tasks/__init__.py` auto-imports all sub-packages using `isaaclab_tasks.utils.import_packages`. Each env registration exposes an `env_cfg_entry_point` and an `rsl_rl_cfg_entry_point`.

### Config Hierarchy
All configs use IsaacLab's `@configclass` decorator (dataclass-like with deep-copy merging). The base config is `LocomotionVelocityRoughEnvCfg` in `velocity_env_cfg.py`. Robot-specific configs (e.g. `DeeproboticsLite3RoughEnvCfg`) inherit and override in `__post_init__`.

### Reward System
Rewards are defined as `@configclass` attributes of type `RewTerm(func=..., weight=...)`. When `weight=0`, the term is set to `None` via `disable_zero_weight_rewards()` to skip computation. Common reward patterns:
- `*_l2`: L2 penalty (e.g. `joint_torques_l2`, `flat_orientation_l2`)
- `*_exp`: Exponential reward (e.g. `track_lin_vel_xy_exp`)
- `*_penalty`: Position deviation penalties
- `GaitReward`: Class-based term for enforcing trotting gait via foot contact/air time syncing

### Robot Types
- **Lite3**: 12-DOF quadruped (HipX, HipY, Knee x 4 legs). `DelayedPDActuatorCfg` with delay [0,5] ticks. Action scale: HipX=0.125, others=0.25. No base linear velocity observation.
- **M20**: 16-DOF wheeled-legged robot (12 leg + 4 wheel joints). Leg joints use `DelayedPDActuatorCfg`, wheels use separate `DelayedPDActuatorCfg` with stiffness=0/damping=0.6. Action: position for legs, velocity for wheels. `joint_pos_rel_without_wheel` observation.

### PPO Configuration
Both robots use RSL-RL PPO with: [512, 256, 128] actor/critic hidden layers, ELU activation, adaptive learning rate (1e-3), 24 steps per env, 5 epochs, 4 mini-batches, entropy_coef=0.01, clip_param=0.2.

### Fast ONNX Export
`export_onnx_fast.py` reconstructs the actor MLP from checkpoint state dict keys (`actor.0.weight`, etc.) and exports to ONNX opset 11. Robot metadata (joint names, stiffness/damping, default positions, action scales) is embedded as ONNX model properties. Tensor names `actor_state_dict` (cusrl) and `model_state_dict` (rsl_rl) are both handled.

## Registered Environments

| ID | Robot | Terrain |
|----|-------|---------|
| Flat-Deeprobotics-Lite3-v0 | Lite3 | Flat plane |
| Rough-Deeprobotics-Lite3-v0 | Lite3 | Rough terrain |
| Flat-Deeprobotics-M20-v0 | M20 | Flat plane |
| Rough-Deeprobotics-M20-v0 | M20 | Rough terrain |
| RoughFixedObstacle-Deeprobotics-M20-v0 | M20 | Rough with obstacles |
| PerceptionFixedObstacle-Deeprobotics-M20-v0 | M20 | Perception-based obstacle |
