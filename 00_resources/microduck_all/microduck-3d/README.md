# Microduck Robot — 3D Models (STL)

Source: [pollen-robotics/microduck-simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
CAD: [Onshape](https://cad.onshape.com/documents/804927696f06d877f3f1803e/w/5b75db19292e71970de02dee/e/ef6e972847fec8d82570b35e)

> **Important:** use `robot_allcollisions*.xml` for articulated simulation.
> The `microduck_combined*.xml` files are rigid, visual-only wrappers for the
> already assembled STL files; they do not contain movable joints or collisions.

## Loading the MJCF models

| Model | Purpose | Joints | Collisions and actuators |
|------|---------|--------|--------------------------|
| `robot_allcollisions.xml` | Articulated legs model | 14 actuated DOF plus free root | Yes |
| `robot_allcollisions_rollers.xml` | Articulated rollers model | 14 actuated DOF, four passive wheels, plus free root | Yes |
| `microduck_combined.xml` | Rigid preview of `microduck_combined.stl` | Free root only | No |
| `microduck_combined_rollers.xml` | Rigid preview of `microduck_combined_rollers.stl` | Free root only | No |

Load any model from this directory with MuJoCo's Python viewer:

```powershell
python -m mujoco.viewer --mjcf robot_allcollisions.xml
python -m mujoco.viewer --mjcf robot_allcollisions_rollers.xml
python -m mujoco.viewer --mjcf microduck_combined.xml
python -m mujoco.viewer --mjcf microduck_combined_rollers.xml
```

`assemble.py` generates each combined STL from the corresponding articulated
MJCF at zero joint angles. It applies all body and visual-geometry transforms
before concatenating the meshes, so the combined STL is already expressed in
the source model's world frame.

## Structure

```
microduck-stl/
├── README.md                          # This file
├── robot_allcollisions.xml            # MuJoCo MJCF — LEGS variant (walking)
├── robot_allcollisions_rollers.xml    # MuJoCo MJCF — ROLLERS variant (wheeled)
├── kinematics.json                    # Joint tree — LEGS
├── kinematics_rollers.json            # Joint tree — ROLLERS
├── microduck.glb                      # Combined 3D model (GLB format)
└── *.stl                              # 43 binary STL meshes
```

## STL Files by Category

### Body / Torso
| File | Size | Description |
|------|------|-------------|
| `trunk_base.stl` | 39KB | Main body base |
| `left_shell.stl` | 256KB | Left outer shell |
| `right_shell.stl` | 256KB | Right outer shell |
| `banana_pcb_locker.stl` | 12KB | PCB locking bracket |
| `power_support.stl` | 128KB | Power supply support |
| `np_f970.stl` | 248KB | NEMA motor (F970) |

### Head
| File | Size | Description |
|------|------|-------------|
| `top_head_shell.stl` | 195KB | Top head casing |
| `bottom_head_shell.stl` | 231KB | Bottom head casing |
| `face_part.stl` | 137KB | Face plate |
| `jaw.stl` | 121KB | Lower jaw |
| `jaw_soft.stl` | 84KB | Soft jaw part |
| `soft_mouth_top.stl` | 98KB | Soft top mouth |
| `noenoeil.stl` | 12KB | No-eye part (no "œil") |
| `lens.stl` | 23KB | Camera lens |
| `m12_lens_holder.stl` | 98KB | M12 lens mount |
| `neck.stl` | 18KB | Neck segment |
| `neck_pitch.stl` | 85KB | Neck pitch joint part |
| `yaw_roll_motion.stl` | 62KB | Head yaw/roll linkage |
| `motor_support.stl` | 45KB | Motor mounting plate |
| `speaker.stl` | 0.7KB | Speaker (12 triangles) |

### Electronics
| File | Size | Description |
|------|------|-------------|
| `pcb__raspberry_pi_zero_2_w.stl` | 262KB | Raspberry Pi Zero 2 W PCB |
| `elec_rpi_robot_hat_pcb.stl` | 225KB | Robot HAT PCB |

### Legs (left/right)
| File | Size | Description |
|------|------|-------------|
| `hip_l.stl` | 229KB | Hip joint bracket (used for both sides) |
| `upper_leg_left.stl` | 133KB | Upper leg (thigh) — left |
| `upper_leg_right.stl` | 124KB | Upper leg (thigh) — right |
| `upper_leg_rigidity_plate.stl` | 45KB | Upper leg reinforcement |
| `leg.stl` | 166KB | Lower leg (shin) — shared |
| `ankle_left.stl` | 58KB | Ankle — left (legs variant) |
| `ankle_right.stl` | 52KB | Ankle — right (legs variant) |
| `foot_left.stl` | 242KB | Foot — left (legs variant) |
| `foot_right.stl` | 246KB | Foot — right (legs variant) |
| `sole_left.stl` | 197KB | Sole — left (collision) |
| `sole_right.stl` | 199KB | Sole — right (collision) |

### Rollers (wheeled variant only)
| File | Size | Description |
|------|------|-------------|
| `ankle_l_v1.stl` | 79KB | Ankle adapter — left (rollers) |
| `ankle_r_v1.stl` | 69KB | Ankle adapter — right (rollers) |
| `roller_blade.stl` | 262KB | Roller blade frame |
| `rim.stl` | 29KB | Wheel rim |
| `tire.stl` | 88KB | Wheel tire |

### Motors & Bearings
| File | Size | Description |
|------|------|-------------|
| `xl330.stl` | 46KB | XL-330 servo motor (×13 instances) |
| `bearing_roll.stl` | 30KB | Roll bearing |
| `seeed_bearing__configuration__22x16x4.stl` | 260KB | Seeed bearing 22×16×4 |
| `seeed_bearing__configuration_default.stl` | 260KB | Seeed bearing (default config) |
| `yaw2roll.stl` | 120KB | Yaw-to-roll linkage |

## Joint Tree (14 DOF)

```
trunk_base (free)
├── LEFT LEG
│   ├── yaw2roll (left_hip_yaw)
│   │   └── hip_l (left_hip_roll)
│   │       └── upper_leg_left (left_hip_pitch)
│   │           └── leg (left_knee)
│   │               └── ankle_left (left_ankle)
├── RIGHT LEG (mirror)
│   ├── bearing_roll (right_hip_yaw)
│   │   └── hip_l_2 (right_hip_roll)
│   │       └── upper_leg_right (right_hip_pitch)
│   │           └── leg_2 (right_knee)
│   │               └── ankle_right (right_ankle)
└── HEAD
    └── neck (neck_pitch)
        └── neck_pitch (head_pitch)
            └── yaw_roll_motion (head_yaw)
                └── jaw_soft (head_roll)
```

## Variants

| Feature | LEGS (default) | ROLLERS |
|---------|---------------|---------|
| Locomotion | Walking | Skating on 4 wheels |
| Unique meshes | ankle_left/right, foot_left/right, sole_left/right | ankle_l/r_v1, roller_blade, rim, tire |
| Policy | `BEST_alpha_walking.onnx` | `BEST_roller.onnx` |
| Top speed | ~0.3 m/s | ~0.6 m/s |

## Source Repos

- **Simulator (this Space):** [pollen-robotics/microduck-simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
- **Runtime (Rust):** [apirrone/microduck_runtime](https://github.com/apirrone/microduck_runtime)
- **RL Training (Python):** [pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl)
- **CAD (Onshape):** [cad.onshape.com](https://cad.onshape.com/documents/804927696f06d877f3f1803e/w/5b75db19292e71970de02dee/e/ef6e972847fec8d82570b35e)

## Assembly

To assemble the individual STL meshes into a single combined model:

```bash
pip install trimesh numpy
python3 assemble.py                # Both variants
python3 assemble.py --variant legs # Only walking variant
python3 assemble.py --variant rollers  # Only wheeled variant
```

This reads the MJCF transform data (position + quaternion for each body/geom)
and applies it to each STL, producing:
- `microduck_combined.stl` (~9 MB, 188K triangles)
- `microduck_combined_rollers.stl` (~9 MB, 191K triangles)
