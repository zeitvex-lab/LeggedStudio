# Validation matrix

| Layer | Isaac Gym | MJLab |
|---|---|---|
| Asset | URDF + local meshes | Native MJCF preferred; URDF is discovery/load fallback |
| Semantics | legged_gym config, actuator/terrain/reward | EntityCfg, actuator/sensor/contact config |
| Contract | action shape/order, control dt | same action shape/order, control dt |
| Smoke test | one env reset + one step | one env reset + one step |

An XML file is not automatically MJLab-ready: inspect actuators, sensors,
joint limits, free-root, contact geoms, and body names. A URDF fallback proves
only that MuJoCo can parse the model; it does not prove equivalent dynamics or
task behavior. When converting URDF to MJCF, write the generated file beside
the source, preserve attribution, and compare joint names, masses, inertias,
limits, and mesh scales before enabling training.
