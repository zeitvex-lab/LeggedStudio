"""Build the assets/robots/unitree_go2w package from the unitree_rl_mjlab_go2w source project.

Idempotent: recreates model/, simulation/, training/ files from scratch.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

STUDIO = Path(r"C:\Users\31560\Documents\00_open\legged_studio")
SRC = Path(r"C:\Users\31560\Documents\00_open\unitree_rl_mjlab_go2w")
SRC_XML = SRC / "mjlab" / "asset_zoo" / "robots" / "unitree_go2w" / "xmls"
SRC_ASSETS = SRC_XML / "assets"
PKG = STUDIO / "assets" / "robots" / "unitree_go2w"

# ---------------------------------------------------------------------------
# Joint orders
# ---------------------------------------------------------------------------
# XML kinematic-tree order (per leg: hip, thigh, calf, wheel).
TREE_JOINTS = []
for leg in ("FL", "FR", "RL", "RR"):
    TREE_JOINTS += [f"{leg}_hip_joint", f"{leg}_thigh_joint", f"{leg}_calf_joint", f"{leg}_wheel_joint"]
# Unitree SDK action/observation order (preserve_order=True in the training cfg).
SDK_LEGS = []
for leg in ("FR", "FL", "RR", "RL"):
    SDK_LEGS += [f"{leg}_hip_joint", f"{leg}_thigh_joint", f"{leg}_calf_joint"]
SDK_WHEELS = [f"{leg}_wheel_joint" for leg in ("FR", "FL", "RR", "RL")]
SDK_JOINTS = SDK_LEGS + SDK_WHEELS
# InitialStateCfg values keyed by SDK order: hip FR/RR=+0.1 FL/RL=-0.1; thigh 0.9; calf -1.8; wheels 0.
DEFAULT_POSE_SDK = [
    0.1, 0.9, -1.8,   # FR
    -0.1, 0.9, -1.8,  # FL
    0.1, 0.9, -1.8,   # RR
    -0.1, 0.9, -1.8,  # RL
    0.0, 0.0, 0.0, 0.0,
]

KP = {"hip": 20.0, "thigh": 20.0, "calf": 40.0}
KD = {"hip": 1.0, "thigh": 1.0, "calf": 2.0}
EFFORT = {"hip": 23.5, "thigh": 23.5, "calf": 45.0}
WHEEL_KV = 2.0
WHEEL_EFFORT = 45.0


def build_model() -> Path:
    model_dir = PKG / "model"
    assets_dir = model_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for f in SRC_ASSETS.iterdir():
        if f.is_file():
            shutil.copy2(f, assets_dir / f.name)

    text = (SRC_XML / "go2w.xml").read_text(encoding="utf-8")
    root = ET.fromstring(text)

    # Align armature with the training actuator cfg (calf 0.02, wheels 0.02).
    for default in root.findall(".//default"):
        if default.get("class") == "knee":
            joint = default.find("joint")
            if joint is not None:
                joint.set("armature", "0.02")
    for joint in root.findall(".//joint"):
        if joint.get("name", "").endswith("_wheel_joint"):
            joint.set("armature", "0.02")

    actuator = ET.SubElement(root, "actuator")
    for name in TREE_JOINTS:
        role = "wheel" if "_wheel_" in name else name.split("_")[1].lower()
        if role == "wheel":
            ET.SubElement(actuator, "general", {
                "name": name, "joint": name,
                "forcerange": f"-{WHEEL_EFFORT:g} {WHEEL_EFFORT:g}",
                "gainprm": f"{WHEEL_KV:g}", "biasprm": f"0 0 {-WHEEL_KV:g}",
            })
        else:
            ET.SubElement(actuator, "general", {
                "name": name, "joint": name,
                "forcerange": f"-{EFFORT[role]:g} {EFFORT[role]:g}",
                "gainprm": f"{KP[role]:g}", "biasprm": f"0 {-KP[role]:g} {-KD[role]:g}",
            })

    ET.indent(root, space="  ")
    out = model_dir / "robot.xml"
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=False)
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    PKG.mkdir(parents=True, exist_ok=True)
    model_xml = build_model()

    mesh_files = sorted(p.name for p in (PKG / "model" / "assets").iterdir())

    write_json(PKG / "robot_package.json", {
        "schema_version": "robot-package-1.0",
        "package_id": "unitree_go2w",
        "task_kind": "generic",
        "capabilities": ["generic_mjlab", "mjlab_source_profiles", "mujoco_sim"],
        "model": {"format": "mjcf", "path": "model/robot.xml", "assets_path": "model/assets"},
        "contract_path": "contract.json",
        "training_config_path": "training/config.json",
        "simulation_config_path": "simulation/config.json",
        "display_name": "Unitree Go2-W",
        "source_project": str(SRC),
    })

    write_json(PKG / "contract.json", {
        "schema_version": "robot-contract-2.0",
        "contract_id": "unitree_go2w_contract_v1",
        "robot_id": "unitree_go2w",
        "family": "Unitree Go2-W",
        "size_class": "M",
        "locomotion_type": "W",
        "urdf": {
            "path": "assets/robots/unitree_go2w/model/robot.xml",
            "hash": sha256(model_xml),
            "total_mass_kg": 19.126,
            "mass_source": "mjcf_inertial_sum",
            "mesh_files": mesh_files,
        },
        "joints": {
            "actuated_joints": TREE_JOINTS,
            "passive_joints": [],
            "default_pose": DEFAULT_POSE_SDK,
            "default_pose_order": SDK_JOINTS,
        },
        "observation": {
            "dimension": 57,
            "components": [
                "base_ang_vel", "projected_gravity", "command",
                "joint_pos", "joint_vel",
                "wheel_joint_pos_rel", "wheel_joint_vel_rel",
                "actions",
            ],
        },
        "action": {
            "dimension": 16,
            "joint_order": SDK_JOINTS,
            "action_scale": 0.5,
            "wheel_velocity_scale": 35.0,
        },
        "control": {
            "control_hz": 50,
            "physics_hz": 200,
            "decimation": 4,
        },
        "description": "Unitree Go2-W wheel-legged robot (12 leg joints + 4 wheel joints), hybrid position/velocity control.",
        "tags": ["imported", "package", "unitree_go2w", "wheel_leg"],
        "source": "unitree_rl_mjlab_go2w_import",
        "min_mjlab_version": "1.6.0",
        "python_version": "3.12",
    })

    # --- simulation ---------------------------------------------------------
    scene_body = """<mujoco model="go2w_scene">
  <include file="../model/robot.xml"/>
  <compiler meshdir="../model/assets"/>

  <option timestep="0.005" gravity="0 0 -9.81" integrator="implicitfast" cone="elliptic" impratio="100"/>

  <visual>
    <headlight diffuse="0.82 0.86 0.9" ambient="0.42 0.48 0.54" specular="0.15 0.15 0.18"/>
    <global azimuth="120" elevation="-20"/>
  </visual>

  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0" width="512" height="3072"/>
    <texture type="2d" name="groundplane" builtin="checker" mark="edge"
      rgb1="0.28 0.38 0.46" rgb2="0.16 0.23 0.30" markrgb="0.56 0.64 0.70" width="300" height="300"/>
    <material name="groundplane" texture="groundplane" texuniform="true" texrepeat="5 5" reflectance="0.2"/>
  </asset>

  <worldbody>
    <light pos="0 0 3" dir="0 0 -1" directional="true"/>
    <geom name="floor" size="0 0 0.05" type="plane" material="groundplane" friction="0.8 0.02 0.01"/>
  </worldbody>
</mujoco>
"""
    flat_body = scene_body.replace('model="go2w_scene"', 'model="go2w_flat"')
    (PKG / "simulation").mkdir(exist_ok=True)
    (PKG / "simulation" / "scene.xml").write_text(scene_body, encoding="utf-8")
    (PKG / "simulation" / "flat.xml").write_text(flat_body, encoding="utf-8")

    # policy.onnx (external-data format: policy.onnx + policy.onnx.data)
    policies_dir = PKG / "simulation" / "policies"
    policies_dir.mkdir(exist_ok=True)
    onnx_src = SRC / "deploy" / "robots" / "go2w" / "config" / "policy" / "velocity_legs_only" / "v0" / "exported"
    for name in ("policy.onnx", "policy.onnx.data"):
        shutil.copy2(onnx_src / name, policies_dir / name)

    write_json(PKG / "simulation" / "config.json", {
        "schema_version": "simulation-config-1.0",
        "backend": "mujoco",
        "scene_path": "simulation/scene.xml",
        "initial_base_height": 0.4,
        "actuator_interface": "position_target",
        "control_hz": 50,
        "physics_hz": 200,
        "decimation": 4,
        "stiffness": {"hip": 20.0, "thigh": 20.0, "calf": 40.0, "joint": 20.0},
        "damping": {"hip": 1.0, "thigh": 1.0, "calf": 2.0, "wheel": 2.0, "joint": 1.0},
        "action_scale_by_role": {"leg": 0.5, "wheel": 35.0},
        "velocity_scale": 35.0,
        "control_modes": {
            "wheel": "velocity",
            "FR_wheel_joint": "velocity",
            "FL_wheel_joint": "velocity",
            "RR_wheel_joint": "velocity",
            "RL_wheel_joint": "velocity",
        },
        "torque_limit": 45.0,
        "torque_limits": {"hip": 23.5, "thigh": 23.5, "calf": 45.0, "wheel": 45.0, "joint": 23.5},
        "policy_contract": {
            "observation_kind": "go2w_53",
            "obs_dim": 53,
            "action_dim": 12,
            "history_len": 1,
            "scales": {"ang_vel": 1.0, "dof_pos": 1.0, "dof_vel": 1.0, "command": [1.0, 1.0, 1.0]},
        },
        "policies": [
            {
                "id": "go2w-legs-only-v0",
                "path": "simulation/policies/policy.onnx",
                "label": "Go2-W legs-only velocity v0 (轮随动)",
                "obs_dim": 53,
                "action_dim": 12,
                "history_len": 1,
                "contract": {
                    "observation_kind": "go2w_53",
                    "obs_dim": 53,
                    "action_dim": 12,
                    "history_len": 1,
                    # Exported from unitree_go2w_flat_legs_only_env_cfg: legs use
                    # scale 0.35 and the wheels stay passive (no wheel action).
                    "action_scale": 0.35,
                    "action_joint_order": SDK_LEGS,
                    "wheel_mode": "passive",
                    "scales": {"ang_vel": 1.0, "dof_pos": 1.0, "dof_vel": 1.0, "command": [1.0, 1.0, 1.0]},
                },
            }
        ],
        "default_map": "flat",
        "settle_steps": 500,
        "action_filter_cutoffs": {"leg": 5.0, "wheel": 15.0},
        "terrains": [
            {"id": "flat", "label": "平地", "path": "simulation/flat.xml"},
        ],
    })

    # --- training -----------------------------------------------------------
    write_json(PKG / "training" / "config.json", {
        "robot_id": "unitree_go2w",
        "contract_path": "assets/robots/unitree_go2w/contract.json",
        "profile_id": "go2w-flat",
        "task_name": "go2w_velocity_flat",
        "algorithm": "PPO",
        "backend": "native_mjlab",
        "num_envs": 4096,
        "episode_length_s": 20.0,
        "max_iterations": 10000,
        "learning_rate": 0.001,
        "save_interval": 1000,
        "seed": 1,
        "terrain": {"terrain_type": "plane"},
        "command_ranges": {"lin_vel_x": [-0.5, 1.0], "lin_vel_y": [0.0, 0.0], "ang_vel_z": [-1.0, 1.0]},
    })

    profile_flat = {
        "schema_version": "training-profile-1.0",
        "profile_id": "go2w-flat",
        "display_name": "Go2-W Velocity / Flat (hybrid wheel)",
        "source": "unitree_rl_mjlab_go2w go2w velocity flat",
        "source_root": "C:/Users/31560/Documents/00_open/unitree_rl_mjlab_go2w",
        "entrypoints": {
            "env": "mjlab.tasks.robots.unitree_go2w.velocity.env_cfgs:unitree_go2w_flat_env_cfg",
            "runner": "mjlab.tasks.robots.unitree_go2w.velocity.rl_cfg:unitree_go2w_ppo_runner_cfg",
            "runner_class": "mjlab.tasks.velocity.rl:VelocityOnPolicyRunner",
        },
        "backend": "native_mjlab",
        "task_name": "go2w_velocity_flat",
        "terrain_type": "plane",
        "algorithm": "PPO",
        "num_envs": 4096,
        "episode_length_s": 20.0,
        "command_ranges": {"lin_vel_x": [-0.5, 1.0], "lin_vel_y": [0.0, 0.0], "ang_vel_z": [-1.0, 1.0]},
        "runner": {
            "hidden_dims": [512, 256, 128],
            "learning_rate": 0.001,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_param": 0.2,
            "entropy_coef": 0.01,
            "num_learning_epochs": 5,
            "num_mini_batches": 4,
            "num_steps_per_env": 24,
            "max_iterations": 10000,
            "save_interval": 1000,
        },
        "sort_order": 10,
        "source_project": "unitree_rl_mjlab_go2w",
    }
    profile_rough = {
        **profile_flat,
        "profile_id": "go2w-rough",
        "display_name": "Go2-W Velocity / Rough (hybrid wheel)",
        "source": "unitree_rl_mjlab_go2w go2w velocity rough",
        "entrypoints": {
            "env": "mjlab.tasks.robots.unitree_go2w.velocity.env_cfgs:unitree_go2w_rough_env_cfg",
            "runner": "mjlab.tasks.robots.unitree_go2w.velocity.rl_cfg:unitree_go2w_rough_ppo_runner_cfg",
            "runner_class": "mjlab.tasks.velocity.rl:VelocityOnPolicyRunner",
        },
        "task_name": "go2w_velocity_rough",
        "terrain_type": "rough",
        "command_ranges": {"lin_vel_x": [-0.3, 0.8], "lin_vel_y": [0.0, 0.0], "ang_vel_z": [-0.8, 0.8]},
        "runner": {
            "hidden_dims": [512, 256, 128],
            "learning_rate": 0.0005,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_param": 0.2,
            "entropy_coef": 0.005,
            "num_learning_epochs": 5,
            "num_mini_batches": 4,
            "num_steps_per_env": 24,
            "max_iterations": 10000,
            "save_interval": 1000,
        },
        "sort_order": 20,
    }
    write_json(PKG / "training" / "profiles" / "go2w-flat.json", profile_flat)
    write_json(PKG / "training" / "profiles" / "go2w-rough.json", profile_rough)

    print("package built at", PKG)
    print("robot.xml sha256:", sha256(model_xml))


if __name__ == "__main__":
    main()
