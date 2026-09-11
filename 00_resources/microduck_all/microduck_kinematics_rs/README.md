# microduck_kinematics

Standalone forward kinematics for the microduck robot, driven by the MJCF.

## Why

`microduck_runtime` had a hand-rolled FK chain hardcoded in
`src/kinematics.rs` (head camera only, v1 + v1.5 inlined). This crate
replaces it with a tiny MJCF-driven model that:

- Parses the kinematic tree (bodies, hinge joints, sites) directly from
  `assets/<version>/robot_walk.xml`.
- Returns the pose of any site in the trunk frame for any joint vector.
- Adds new robot versions by dropping a new MJCF into `assets/`.
- Is validated against MuJoCo via fixtures regenerable with `uv`.

IK is intentionally not implemented — the runtime doesn't use any.

## Usage

```rust
use microduck_kinematics::{JointVector, Model};

let model = Model::v1_5();
let mut q = JointVector::new();
q.set("head_yaw", 0.3);
q.set("head_pitch", -0.2);

let cam = model.site_pose("head_camera", &q);
println!("head_camera @ {:?}", cam.translation);
```

`Model::v1()`, `Model::v1_5()` and `Model::alpha()` load the bundled
MJCFs at compile time. `Model::from_mjcf_str(xml)` accepts any compatible
MJCF for future versions.

## Supported sites

| Site            | v1 | v1.5 | alpha |
|-----------------|----|------|-----------|
| `head_camera`   | ✓  | ✓    | ✓         |
| `torso_camera`  | ✓  | ✓    | —         |
| `tof`           | —  | —    | ✓         |
| `imu`           | ✓  | ✓    | ✓         |
| `left_foot`     | ✓  | ✓    | ✓         |
| `right_foot`    | ✓  | ✓    | ✓         |
| `mouth_tip`     | ✓  | —    | ✓         |

`mouth_tip` on v1.5 is downstream of two passive joints closed by an
equality constraint; the crate would need a constraint solver to expose
it, which isn't worth it until something consumes it. alpha dropped
the passive linkage, so its `mouth_tip` is a rigid site and FK-computable
again. alpha also replaces the `torso_camera` site with `tof`.

## Updating MJCFs

The shipped MJCFs are stripped (no geoms, meshes, materials, actuators,
sensors, contacts, equalities) so the repo stays small and MuJoCo can
load them without any STLs on disk.

```sh
# v1 lives on `main`, v1.5 on `v1.5` of mjlab_microduck.
cp ~/MISC/mjlab_microduck/src/mjlab_microduck/robot/microduck/robot_walk.xml \
   assets/v1.5/robot_walk.xml
git -C ~/MISC/mjlab_microduck show main:src/mjlab_microduck/robot/microduck/robot_walk.xml \
   > assets/v1/robot_walk.xml

python3 scripts/strip_mjcf.py assets/v1/robot_walk.xml    assets/v1/robot_walk.xml
python3 scripts/strip_mjcf.py assets/v1.5/robot_walk.xml  assets/v1.5/robot_walk.xml

# alpha: stripped straight from the current mjlab working tree.
python3 scripts/strip_mjcf.py \
   ~/MISC/mjlab_microduck/src/mjlab_microduck/robot/microduck/robot_walk.xml \
   assets/alpha/robot_walk.xml
```

## Tests

```sh
# (Re)generate the MuJoCo reference fixtures — only needed when MJCFs change.
uv run --project scripts python scripts/gen_fixtures.py

# Run the FK-vs-MuJoCo check.
cargo test
```

The Rust tests don't require Python or MuJoCo at runtime; they only
consume the JSON fixtures under `tests/fixtures/`.
