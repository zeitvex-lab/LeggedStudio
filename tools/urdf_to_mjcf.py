"""Convert a robot URDF into a self-contained MJCF via MuJoCo MjSpec.

The URDF importer resolves collision meshes into primitives where possible and
preserves inertial properties, so the generated MJCF has no mesh dependencies
and compiles standalone.  Visual meshes (DAE) are dropped by the importer;
MJCF does not support DAE anyway.

Usage:
    python tools/urdf_to_mjcf.py <robot.urdf> <out_model.xml> [--meshdir SRC]

The generated MJCF contains joints/bodies/inertials/collision geoms but no
actuators - mjlab actuator configs (BuiltinPositionActuatorCfg etc.) supply
those at training/simulation time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mujoco


def convert(urdf_path: Path, out_path: Path) -> Path:
    spec = mujoco.MjSpec.from_file(str(urdf_path))
    model = spec.compile()  # validate before writing
    out_path.parent.mkdir(parents=True, exist_ok=True)
    xml = spec.to_xml()
    out_path.write_text(xml, encoding="utf-8")
    print(f"converted: nq={model.nq} nu={model.nu} nbody={model.nbody}")
    print(f"wrote {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urdf", type=Path, help="input URDF file")
    parser.add_argument("out_xml", type=Path, help="output MJCF file")
    args = parser.parse_args()
    if not args.urdf.exists():
        print(f"error: {args.urdf} not found", file=sys.stderr)
        raise SystemExit(1)
    convert(args.urdf, args.out_xml)


if __name__ == "__main__":
    main()
