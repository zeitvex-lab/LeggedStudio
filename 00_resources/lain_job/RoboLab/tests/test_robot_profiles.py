import xml.etree.ElementTree as ET
from pathlib import Path

from robolab.frameworks.semantic_tasks import isaacgym_task_config, mjlab_task_config
from robolab.robots.profiles import PROFILES


def _urdf_joint_names(robot_id):
    paths = sorted((Path("resources/robots") / robot_id).rglob("*.urdf"))
    if robot_id == "unitree_g1":
        paths = [p for p in paths if "12dof" in p.name]
    path = paths[0]
    root = ET.parse(path).getroot()
    return tuple(j.attrib["name"] for j in root.findall("joint") if j.attrib.get("type") != "fixed")


def test_profiles_cover_all_urdf_joints_and_are_shared_by_backends():
    for robot_id, profile in PROFILES.items():
        assert set(profile.joint_order) == set(_urdf_joint_names(robot_id))
        assert len(profile.default_joint_pos) == profile.action_dim
        isaac = isaacgym_task_config(robot_id)["control"]
        mjlab = mjlab_task_config(robot_id)["control"]
        assert isaac["joint_order"] == mjlab["joint_order"] == profile.joint_order
        assert isaac["dt"] == mjlab["dt"] == profile.control_dt


def test_profiles_have_explicit_control_semantics():
    for profile in PROFILES.values():
        assert profile.control_dt > 0
        assert profile.action_scale > 0
        assert profile.sensors and profile.observation_terms and profile.reward_terms
        assert profile.base_body and profile.contact_bodies and profile.terminate_bodies
