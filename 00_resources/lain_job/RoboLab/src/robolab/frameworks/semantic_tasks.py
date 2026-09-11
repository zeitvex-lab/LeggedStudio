"""Backend-neutral task projections consumed by Isaac Gym and MJLab adapters."""

from __future__ import annotations

from robolab.robots.profiles import RobotTaskProfile, get_task_profile


def isaacgym_task_config(robot_id: str) -> dict[str, object]:
    p = get_task_profile(robot_id)
    return {
        "asset": {"file": f"resources/robots/{robot_id}", "format": "urdf", "base": p.base_body},
        "control": {"dt": p.control_dt, "action_scale": p.action_scale, "joint_order": p.joint_order, "effort_limit": p.effort_limit, "velocity_limit": p.velocity_limit},
        "init_state": {"joint_pos": dict(p.default_joint_pos)},
        "sensors": p.sensors,
        "contacts": {"feet": p.contact_bodies, "terminate": p.terminate_bodies},
        "observations": p.observation_terms,
        "rewards": p.reward_terms,
    }


def mjlab_task_config(robot_id: str) -> dict[str, object]:
    p = get_task_profile(robot_id)
    return {
        "asset": {"robot": robot_id, "variant": p.asset_variant, "base": p.base_body},
        "control": {"dt": p.control_dt, "action_scale": p.action_scale, "joint_order": p.joint_order, "effort_limit": p.effort_limit, "velocity_limit": p.velocity_limit},
        "init_state": {"joint_pos": dict(p.default_joint_pos)},
        "sensors": p.sensors,
        "contacts": {"feet": p.contact_bodies, "terminate": p.terminate_bodies},
        "observations": p.observation_terms,
        "rewards": p.reward_terms,
    }


__all__ = ["isaacgym_task_config", "mjlab_task_config"]
