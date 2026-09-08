"""One-off converter: raw retarget pkls -> tracking-loader schema.

The ``raw_run`` pkls carry ``local_body_pos`` for every link plus
``link_body_list`` names, but lack the ``key_body_pos_relative_to_base``
subset and the velocity fields the tracking loader expects.  This script
selects the loader's 19 key bodies by name, finite-differences root/dof
velocities (root angular velocity from quaternion increments), and writes
schema-compatible pkls alongside the originals.
"""

import glob
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets" / "robots" / "unitree_g1" / "training" / "source" / "g1_tracking" / "src"))
from tasks.tracking.motion_loader import KEY_BODY_NAMES  # noqa: E402


def convert(path: Path) -> None:
    with open(path, "rb") as f:
        d = pickle.load(f)
    if "key_body_pos_relative_to_base" in d:
        return  # already compatible

    names = list(d["link_body_list"])
    fps = float(d["fps"])
    dt = 1.0 / fps

    idx = []
    for want in KEY_BODY_NAMES:
        matches = [i for i, n in enumerate(names) if n == want]
        if not matches:
            # tolerate prefix/suffix variants (e.g. *_link missing)
            matches = [i for i, n in enumerate(names) if n.rstrip("_link") in want]
        assert matches, f"{path.name}: key body {want!r} not in {names}"
        idx.append(matches[0])
    local = np.asarray(d["local_body_pos"], dtype=np.float64)
    key = local[:, idx, :]  # (T, 19, 3)
    d["key_body_pos_relative_to_base"] = key.astype(np.float32)

    root_pos = np.asarray(d["root_pos"], dtype=np.float64)
    root_quat_xyzw = np.asarray(d["root_rot"], dtype=np.float64)
    dof_pos = np.asarray(d["dof_pos"], dtype=np.float64)

    d["root_lin_vel"] = np.gradient(root_pos, dt, axis=0).astype(np.float32)
    d["dof_vel"] = np.gradient(dof_pos, dt, axis=0).astype(np.float32)

    rot = Rotation.from_quat(root_quat_xyzw)
    next_rot = Rotation.from_quat(np.roll(root_quat_xyzw, -1, axis=0))
    rel = rot.inv() * next_rot  # per-frame delta rotation
    dtvec = rel.as_rotvec() / dt
    d["root_ang_vel"] = np.concatenate([dtvec[:-1], dtvec[-1:]], axis=0).astype(np.float32)

    out = path.with_suffix("")  # strip .pkl
    out = out.with_suffix(".rawconv.pkl")
    with open(out, "wb") as f:
        pickle.dump(d, f)
    print(f"{path.name} -> {out.name} ({root_pos.shape[0]} frames)")


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "robots" / "unitree_g1" / "training" / "source" / "g1_tracking" / "assets" / "motions" / "g1" / "tracking"
    # only the bare *_stageii.pkl files are the raw variant
    for p in sorted(root.glob("*_stageii.pkl")):
        convert(p)


if __name__ == "__main__":
    main()
