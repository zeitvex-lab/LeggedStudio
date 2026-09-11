"""Isaac Gym-to-RoboLab visualization state conversion."""

from __future__ import annotations

from robolab.robots.unitree_a1.spec import UNITREE_A1_JOINT_ORDER
from robolab.visualization import SceneFrame


def scene_frame_from_isaacgym(env, *, reward: float = 0.0, env_idx: int = 0, robot: str | None = None) -> SceneFrame:
    """Convert one legacy legged_gym state into the public SceneFrame protocol."""

    names = tuple(env.dof_names)
    name_to_index = {name: index for index, name in enumerate(names)}
    is_a1 = set(UNITREE_A1_JOINT_ORDER).issubset(name_to_index)
    joint_order = UNITREE_A1_JOINT_ORDER if is_a1 else names
    joint_indices = [name_to_index[name] for name in joint_order]
    root = env.root_states[env_idx]
    quat_xyzw = root[3:7]
    quat_wxyz = quat_xyzw[[3, 0, 1, 2]]
    command = env.commands[env_idx, :3]

    def values(value):
        return tuple(float(item) for item in value.detach().cpu().tolist())

    contacts = ()
    if hasattr(env, "contact_forces") and hasattr(env, "feet_indices"):
        forces = env.contact_forces[env_idx, env.feet_indices]
        active = forces.norm(dim=-1) > 1.0
        contacts = tuple(
            name for name, is_active in zip(("FL", "RL", "FR", "RR"), active.tolist()) if is_active
        )

    return SceneFrame(
        robot=robot or ("unitree_a1" if is_a1 else "unknown"),
        joint_order=joint_order,
        root_position=values(root[:3]),
        root_orientation=values(quat_wxyz),
        joint_position=values(env.dof_pos[env_idx, joint_indices]),
        joint_velocity=values(env.dof_vel[env_idx, joint_indices]),
        command=values(command),
        reward=float(reward),
        contacts=contacts,
    )
