"""Generate FK reference fixtures from MuJoCo.

For each robot version, loads the (stripped) MJCF, samples N random joint
configurations within the model's joint limits, runs `mj_kinematics`, and
writes the resulting site poses in trunk_base frame to a JSON file the
Rust tests consume.

Run with:
    uv run --project scripts python scripts/gen_fixtures.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import mujoco
import numpy as np


REPO = Path(__file__).resolve().parent.parent
SEED = 0
N_SAMPLES = 64

# Sites to validate per version. v1.5's mouth_tip lives behind a closed-loop
# constraint we explicitly skip in the kinematics crate.
VERSION_SITES = {
    "v1": ["head_camera", "torso_camera", "imu", "left_foot", "right_foot", "mouth_tip"],
    "v1.5": ["head_camera", "torso_camera", "imu", "left_foot", "right_foot"],
    # alpha: no torso_camera (replaced by `tof`); mouth has no passive
    # linkage so mouth_tip is a rigid, FK-validatable site again.
    "alpha": ["head_camera", "imu", "left_foot", "right_foot", "mouth_tip", "tof"],
}

# Joints whose angle we randomize. Passive joints in v1.5's mouth chain are
# constrained by equalities we don't model and so are left at zero.
SKIP_JOINTS = {"passive_1", "passive_2"}


def fixture_for(version: str, mjcf_path: Path) -> dict:
    model = mujoco.MjModel.from_xml_path(str(mjcf_path))
    data = mujoco.MjData(model)

    # Pin trunk_base to the origin so site_xpos == pose in trunk frame.
    freejoint_qpos = model.jnt_qposadr[model.joint("trunk_base_freejoint").id]
    identity_pose = np.array([0, 0, 0, 1, 0, 0, 0], dtype=np.float64)

    # Index dof joints (hinges) and their qpos addresses + ranges.
    dof_joints = []
    for j in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
        if model.jnt_type[j] != mujoco.mjtJoint.mjJNT_HINGE:
            continue
        if name in SKIP_JOINTS:
            continue
        dof_joints.append({
            "name": name,
            "qposadr": int(model.jnt_qposadr[j]),
            "range": [float(model.jnt_range[j, 0]), float(model.jnt_range[j, 1])],
        })

    rng = np.random.default_rng(SEED + hash(version) % 1000)
    samples = []
    for _ in range(N_SAMPLES):
        data.qpos[:] = 0
        data.qpos[freejoint_qpos : freejoint_qpos + 7] = identity_pose
        angles = {}
        for j in dof_joints:
            lo, hi = j["range"]
            q = float(rng.uniform(lo, hi))
            angles[j["name"]] = q
            data.qpos[j["qposadr"]] = q
        mujoco.mj_kinematics(model, data)

        sites = {}
        for site_name in VERSION_SITES[version]:
            sid = model.site(site_name).id
            pos = data.site_xpos[sid].copy()
            mat = data.site_xmat[sid].reshape(3, 3).copy()
            # 3x3 → quaternion (w, x, y, z) using MuJoCo's helper.
            quat = np.zeros(4, dtype=np.float64)
            mujoco.mju_mat2Quat(quat, mat.flatten())
            sites[site_name] = {
                "pos": pos.tolist(),
                "quat": quat.tolist(),
            }
        samples.append({"joints": angles, "sites": sites})

    return {
        "version": version,
        "n_samples": N_SAMPLES,
        "joint_names": [j["name"] for j in dof_joints],
        "site_names": VERSION_SITES[version],
        "samples": samples,
    }


def main() -> None:
    out_dir = REPO / "tests" / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)
    for version, subdir in [("v1", "v1"), ("v1.5", "v1.5"), ("alpha", "alpha")]:
        mjcf_path = REPO / "assets" / subdir / "robot_walk.xml"
        fx = fixture_for(version, mjcf_path)
        out = out_dir / f"fk_{subdir}.json"
        out.write_text(json.dumps(fx, indent=2))
        print(f"wrote {out.relative_to(REPO)} ({fx['n_samples']} samples, "
              f"{len(fx['site_names'])} sites)")


if __name__ == "__main__":
    main()
