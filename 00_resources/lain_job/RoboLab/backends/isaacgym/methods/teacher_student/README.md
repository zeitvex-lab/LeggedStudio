# Teacher-Student Isaac Gym method extension

Loaded only with `--method teacher_student`. The teacher uses a 99-dimensional
privileged contract covering domain randomization, terrain/foot geometry,
velocity and contacts. The history encoder is optimized separately and used
for inference. The plugin owns its PPO rollout/storage implementation; v2
checkpoints are intentionally rejected.
