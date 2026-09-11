# PPO-EE Isaac Gym method extension

This directory is the RoboLab-controlled extension boundary for the Explicit
Estimator method. It is intentionally separate from the legacy
`legged_gym` task registry and from the default `rsl_rl` PPO implementation.

The implementation follows the validated structure in
`/home/lxy/LeggedGym-Ex` (`PPO_EE`, `ActorCriticEE`, `EERunner`, and
`RolloutStorageEE`) while keeping method-specific imports and task registration
inside the RoboLab Isaac Gym adapter. The base `a1` task must remain unchanged.

Integration is only enabled when a Recipe explicitly selects `method =
"ppo_ee"`; importing `robolab.core` or running the ordinary `isaacgym` PPO
command must not import this extension.
