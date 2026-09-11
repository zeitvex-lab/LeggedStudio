"""MJLab-to-RoboLab visualization state conversion."""

from __future__ import annotations

from robolab.robots.unitree_a1.spec import UNITREE_A1_JOINT_ORDER
from robolab.visualization import SceneFrame


def scene_frame_from_mjlab(env, *, env_idx: int = 0, reward: float = 0.0) -> SceneFrame:
    """Convert one MJLab environment state to the public SceneFrame protocol."""

    robot = env.unwrapped.scene["robot"]
    command = env.unwrapped.command_manager.get_term("twist").command[env_idx]
    root_position = robot.data.root_link_pos_w[env_idx]
    root_orientation = robot.data.root_link_quat_w[env_idx]
    native_order = tuple(robot.joint_names)
    is_a1 = set(native_order) == set(UNITREE_A1_JOINT_ORDER)
    joint_order = UNITREE_A1_JOINT_ORDER if is_a1 else native_order
    native_index = {name: index for index, name in enumerate(native_order)}
    joint_ids = [native_index[name] for name in joint_order]
    joint_position = robot.data.joint_pos[env_idx, joint_ids]
    joint_velocity = robot.data.joint_vel[env_idx, joint_ids]
    def values(value) -> tuple[float, ...]:
        return tuple(float(item) for item in value.detach().cpu().tolist())

    return SceneFrame(
        robot="unitree_a1" if is_a1 else "unknown",
        joint_order=joint_order,
        root_position=values(root_position),
        root_orientation=values(root_orientation),
        joint_position=values(joint_position),
        joint_velocity=values(joint_velocity),
        command=values(command),
        reward=float(reward),
    )
