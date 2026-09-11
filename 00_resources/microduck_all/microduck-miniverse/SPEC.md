# Microduck bundle specification

## Scope

The published policy family shares a 61-element observation and 14-element
action layout, but it does not share one physical robot model. Seven policies
use the legged all-collisions MJCF. The two roller policies require four passive
wheel joints and different collision geometry. This repository therefore pins
two embodiment archives and produces one policy per bundle.

## Source pins

- Policy bytes: `pollen-robotics/microduck-simulator` revision
  `10c600e54ea52f239887308387cb8fc458ecb3e4`, path
  `app/public/policies`.
- Robot MJCF and meshes: `pollen-robotics/microduck_rl` revision
  `d424a0c899f6b33cbd3daeb279913134349c0b63`.
- Control frequency: 200 Hz MuJoCo physics, 50 Hz policy and publication,
  policy followed by four physics steps.

## Controller contract

`policy.py` constructs the input in this exact order:

1. trunk angular velocity in the trunk frame, 3 values
2. projected gravity in the trunk frame, 3 values
3. 14 joint positions relative to the published default pose
4. 14 joint velocities
5. the previous raw policy action, 14 values
6. command block `[twist(3), head_pose(4), body_pose(6)]`, 13 values

The ONNX graph emits 14 normalized joint offsets. The controller adds the
published default pose and sends the result as position targets in the stable
servo order recorded in `policy.py`.

Walking and roller bundles expose forward speed and yaw rate. Sit/stand exposes
a boolean posture command. Ground-pick and roller-crouch turn a momentary
trigger into the published cosine/sine phase command. Kick and roulade triggers
run the policy for a bounded window, then hold the default pose. The get-up
policy runs continuously with a zero command block.

## Standard embodiments

Miniverse should register both physical variants under one pinned Microduck RL
source:

- `pollen-robotics/microduck` from `robot_allcollisions.xml`
- `pollen-robotics/microduck-rollers` from
  `robot_allcollisions_rollers.xml`

The importer must verify the exact Git revision and a clean robot asset tree,
archive the complete MJCF dependency closure, copy the Apache-2.0 license, and
derive browser GLBs without treating presentation geometry as collision.

Microduck uses MJCF `fullinertia`. Miniverse must resolve that through the
compiled MuJoCo model when it creates the canonical simulation contract.
Rejecting every non-`diaginertia` body would make the standard package
buildable but unusable at runtime.

## Reproducibility and publication

The source ONNX files remain unchanged in Git LFS. The published graphs use ONNX Elu, which the current Miniverse runtime allowlist does not accept. The builder deterministically lowers each Elu to Exp, Sub, Greater, and Where in the derived copy, then injects metadata because Miniverse requires a graph hash, contract hash, exact tensor
mapping, scene hash, rates, and backend declaration. It then creates ZIP entries
with fixed timestamps, permissions, ordering, and no compression.

Publication is deliberately two-step. `miniverse bundle upload` creates and
validates an immutable revision. `miniverse bundle publish` moves the current
revision pointer only after the upload reports success.
