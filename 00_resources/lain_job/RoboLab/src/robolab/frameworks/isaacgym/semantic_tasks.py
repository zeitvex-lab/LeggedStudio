"""Register RoboLab semantic locomotion tasks in the bundled legged_gym."""

from __future__ import annotations

from robolab.robots import PROFILES, isaacgym_asset


_FOOT_PATTERNS = {
    "anymal_b": "FOOT",
    "anymal_c": "FOOT",
    "bipedal_walker": "foot",
    "booster_k1": "foot_link",
    "cassie": "toe",
    "limx_tron1pf": "foot_",
    "limx_tron1sf": "ankle_",
    "unitree_a1": "foot",
    "unitree_g1": "ankle_roll_link",
    "unitree_go2": "foot",
}

def _make_cfg(robot_id, LeggedRobotCfg):
    profile = PROFILES[robot_id]
    cfg = LeggedRobotCfg()
    cfg.env.num_actions = profile.action_dim
    cfg.env.num_observations = 9 + 3 * profile.action_dim
    cfg.init_state.pos = [0.0, 0.0, profile.base_height]
    cfg.init_state.default_joint_angles = dict(profile.default_joint_pos)
    cfg.control.control_type = "P"
    cfg.control.stiffness = {"joint": min(80.0, max(20.0, profile.effort_limit))}
    cfg.control.damping = {"joint": 1.0}
    cfg.control.action_scale = profile.action_scale
    # Legacy legged_gym has an A1-specific hip scaling path.  Keep it opt-in so
    # lower-DOF bipeds/humanoids do not index past the action tensor.
    cfg.control.scale_hip_actions = profile.action_dim >= 12 and robot_id not in {"booster_k1", "unitree_g1"}
    cfg.control.decimation = max(1, round(profile.control_dt / cfg.sim.dt))
    cfg.asset.file = str(isaacgym_asset(robot_id))
    cfg.asset.name = robot_id
    cfg.asset.foot_name = _FOOT_PATTERNS[robot_id]
    cfg.asset.penalize_contacts_on = []
    cfg.asset.terminate_after_contacts_on = [profile.base_body]
    cfg.asset.self_collisions = 1
    cfg.rewards.base_height_target = profile.base_height * 0.85
    cfg.rewards.soft_dof_pos_limit = 0.9
    return cfg


def _make_train_cfg(robot_id, LeggedRobotCfgPPO):
    cfg = LeggedRobotCfgPPO()
    cfg.runner.experiment_name = f"robolab_{robot_id}_velocity"
    cfg.runner.run_name = "semantic_flat"
    return cfg


def register_semantic_tasks(task_registry) -> tuple[str, ...]:
    """Register one flat velocity task per tracked robot, idempotently."""

    from legged_gym.envs.base.legged_robot import LeggedRobot
    from legged_gym.envs.base.legged_robot_config import (
        LeggedRobotCfg,
        LeggedRobotCfgPPO,
    )

    names = []
    for robot_id in PROFILES:
        name = f"robolab_{robot_id}"
        names.append(name)
        if name not in task_registry.task_classes:
            task_registry.register(
                name,
                LeggedRobot,
                _make_cfg(robot_id, LeggedRobotCfg),
                _make_train_cfg(robot_id, LeggedRobotCfgPPO),
            )
    return tuple(names)


__all__ = ["register_semantic_tasks"]
