"""Create the checked-in Go2 and Go2W Robot Contract/training presets."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def joint_names(xml_path: Path) -> list[str]:
    root = ET.parse(xml_path).getroot()
    return [node.attrib["name"] for node in root.findall(".//joint") if node.attrib.get("name") and node.attrib.get("name") != "root"]


def write_preset(robot_id: str, family: str, locomotion: str, size: str, mass: float, obs_dim: int) -> None:
    robot_dir = ROOT / "assets" / "robots" / robot_id
    model_file = "go2w.xml" if robot_id.endswith("go2w") else "go2.xml"
    xml_path = robot_dir / model_file
    joints = joint_names(xml_path)
    contract = {
        "schema_version": "robot-contract-2.0",
        "contract_id": f"{robot_id}_mvp_v1",
        "robot_id": robot_id,
        "family": family,
        "size_class": size,
        "locomotion_type": locomotion,
        "urdf": {"path": str(xml_path.relative_to(ROOT)).replace("\\", "/"), "hash": "", "total_mass_kg": mass, "mass_source": "manual"},
        "joints": {"actuated_joints": joints, "passive_joints": [], "default_pose": [0.0] * len(joints)},
        "observation": {"dimension": obs_dim, "components": ["base_lin_vel", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "last_action"]},
        "action": {"dimension": len(joints), "joint_order": joints, "action_scale": 0.25},
        "control": {"control_hz": 50, "physics_hz": 1000, "decimation": 20},
        "description": f"Canonical {family} MJCF preset sourced from the local UniLab asset snapshot.",
        "tags": ["mvp", "mjcf", locomotion, "python-3.12"],
        "source": "unilab_new/UniLab",
        "python_version": "3.12",
    }
    (ROOT / "contracts" / "fixtures" / f"{robot_id}.v2.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = {
        "robot_id": robot_id,
        "contract_path": str((ROOT / "contracts" / "fixtures" / f"{robot_id}.v2.json").relative_to(ROOT)).replace("\\", "/"),
        "task_name": "forward_walk",
        "algorithm": "PPO",
        "num_envs": 4096,
        "max_iterations": 1000,
        "episode_length_s": 20.0,
        "learning_rate": 0.0003,
        "save_interval": 100,
        "terrain": {"terrain_type": "plane", "measure_heights": True},
        "command_ranges": {"lin_vel_x": [-1.0, 1.0], "lin_vel_y": [-0.5, 0.5], "ang_vel_yaw": [-1.0, 1.0]},
    }
    (ROOT / "presets" / "training" / f"{robot_id}_forward_walk.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_preset("unitree_go2", "Unitree Go2", "P", "M", 15.206408, 48)
    write_preset("unitree_go2w", "Unitree Go2W", "W", "M", 19.126408, 56)
