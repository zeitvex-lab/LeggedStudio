# InstinctMJ — 参考资源

> **来源**：`00_open/InstinctMJ/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：InstinctMJ：G1 人形 mjlab 工程
> **收录**：221 个文件 / 1.9 MB（其中推理策略/模型文件 0 个）
> **已省略**：85 个文件 / 41.2 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（10 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（83 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（21 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（38 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（69 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （8 个文件）
src/  （213 个文件）
    instinct_mj/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 203 |
| `.md` | 6 |
| `.urdf` | 4 |
| `(无扩展名)` | 3 |
| `.xml` | 3 |
| `.yaml` | 1 |
| `.toml` | 1 |

## 文件索引（项目内相对路径）

```text
.flake8
.gitignore
.pre-commit-config.yaml
CONTRIBUTING.md
CONTRIBUTOR_AGREEMENT.md
LICENSE
README.md
pyproject.toml
src/instinct_mj/__init__.py
src/instinct_mj/assets/__init__.py
src/instinct_mj/assets/resources/unitree_g1/scene.xml
src/instinct_mj/assets/resources/unitree_g1/urdf/g1_29dof_torsobase_boxHand.urdf
src/instinct_mj/assets/resources/unitree_g1/urdf/g1_29dof_torsobase_cylinder.urdf
src/instinct_mj/assets/resources/unitree_g1/urdf/g1_29dof_torsobase_popsicle.urdf
src/instinct_mj/assets/resources/unitree_g1/urdf/g1_29dof_torsobase_simplified.urdf
src/instinct_mj/assets/resources/unitree_g1/xml/g1_29dof_torsobase_popsicle.xml
src/instinct_mj/assets/unitree_g1.py
src/instinct_mj/envs/__init__.py
src/instinct_mj/envs/manager_based_rl_env.py
src/instinct_mj/envs/manager_based_rl_env_cfg.py
src/instinct_mj/envs/mdp/__init__.py
src/instinct_mj/envs/mdp/actions/__init__.py
src/instinct_mj/envs/mdp/actions/action_cfg.py
src/instinct_mj/envs/mdp/actions/joint_actions.py
src/instinct_mj/envs/mdp/commands/__init__.py
src/instinct_mj/envs/mdp/commands/commands_cfg.py
src/instinct_mj/envs/mdp/commands/shadowing_command.py
src/instinct_mj/envs/mdp/commands/utils.py
src/instinct_mj/envs/mdp/curriculums/__init__.py
src/instinct_mj/envs/mdp/curriculums/motion_reference.py
src/instinct_mj/envs/mdp/events/__init__.py
src/instinct_mj/envs/mdp/events/motion_reference.py
src/instinct_mj/envs/mdp/events/randomization.py
src/instinct_mj/envs/mdp/events/terrain.py
src/instinct_mj/envs/mdp/observations/__init__.py
src/instinct_mj/envs/mdp/observations/body.py
src/instinct_mj/envs/mdp/observations/command.py
src/instinct_mj/envs/mdp/observations/expanded.py
src/instinct_mj/envs/mdp/observations/exteroception.py
src/instinct_mj/envs/mdp/observations/motion_reference.py
src/instinct_mj/envs/mdp/observations/reference_as_state.py
src/instinct_mj/envs/mdp/observations/reference_masked_proprioception.py
src/instinct_mj/envs/mdp/rewards/__init__.py
src/instinct_mj/envs/mdp/rewards/motion_reference.py
src/instinct_mj/envs/mdp/rewards/regularizations.py
src/instinct_mj/envs/mdp/rewards/shadowing_command.py
src/instinct_mj/envs/mdp/rewards/volume_points.py
src/instinct_mj/envs/mdp/terminations/__init__.py
src/instinct_mj/envs/mdp/terminations/general.py
src/instinct_mj/envs/mdp/terminations/motion_reference.py
src/instinct_mj/envs/scene.py
src/instinct_mj/managers/__init__.py
src/instinct_mj/managers/manager_term_cfg.py
src/instinct_mj/managers/reward_manager.py
src/instinct_mj/monitors/__init__.py
src/instinct_mj/monitors/monitor_cfg.py
src/instinct_mj/monitors/monitor_manager.py
src/instinct_mj/monitors/monitors.py
src/instinct_mj/motion_reference/__init__.py
src/instinct_mj/motion_reference/motion_buffer.py
src/instinct_mj/motion_reference/motion_files/__init__.py
src/instinct_mj/motion_reference/motion_files/aistpp_motion.py
src/instinct_mj/motion_reference/motion_files/aistpp_motion_cfg.py
src/instinct_mj/motion_reference/motion_files/amass_motion.py
src/instinct_mj/motion_reference/motion_files/amass_motion_cfg.py
src/instinct_mj/motion_reference/motion_files/emberUcb.py
src/instinct_mj/motion_reference/motion_files/emberUcb_cfg.py
src/instinct_mj/motion_reference/motion_files/omomo_motion.py
src/instinct_mj/motion_reference/motion_files/omomo_motion_cfg.py
src/instinct_mj/motion_reference/motion_files/terrain_motion.py
src/instinct_mj/motion_reference/motion_files/terrain_motion_cfg.py
src/instinct_mj/motion_reference/motion_generators/__init__.py
src/instinct_mj/motion_reference/motion_generators/stay_still.py
src/instinct_mj/motion_reference/motion_generators/stay_still_cfg.py
src/instinct_mj/motion_reference/motion_reference_cfg.py
src/instinct_mj/motion_reference/motion_reference_data.py
src/instinct_mj/motion_reference/motion_reference_hoi_data.py
src/instinct_mj/motion_reference/motion_reference_manager.py
src/instinct_mj/motion_reference/utils.py
src/instinct_mj/rl/__init__.py
src/instinct_mj/rl/config.py
src/instinct_mj/rl/module_cfg.py
src/instinct_mj/rl/vecenv_wrapper.py
src/instinct_mj/scripts/GMR_to_instinct.py
src/instinct_mj/scripts/__init__.py
src/instinct_mj/scripts/amass_filter.py
src/instinct_mj/scripts/amass_visualize.py
src/instinct_mj/scripts/instinct_rl/__init__.py
src/instinct_mj/scripts/instinct_rl/cli_args.py
src/instinct_mj/scripts/instinct_rl/play.py
src/instinct_mj/scripts/instinct_rl/plotter.py
src/instinct_mj/scripts/instinct_rl/train.py
src/instinct_mj/scripts/list_envs.py
src/instinct_mj/scripts/motion_matched_metadata_generator.py
src/instinct_mj/scripts/multi_play.py
src/instinct_mj/scripts/phalp_to_amass.py
src/instinct_mj/scripts/rename_template.py
src/instinct_mj/sensors/__init__.py
src/instinct_mj/sensors/grouped_ray_caster/__init__.py
src/instinct_mj/sensors/grouped_ray_caster/grouped_ray_caster.py
src/instinct_mj/sensors/grouped_ray_caster/grouped_ray_caster_camera.py
src/instinct_mj/sensors/grouped_ray_caster/grouped_ray_caster_camera_cfg.py
src/instinct_mj/sensors/grouped_ray_caster/grouped_ray_caster_cfg.py
src/instinct_mj/sensors/noisy_camera/__init__.py
src/instinct_mj/sensors/noisy_camera/noisy_camera.py
src/instinct_mj/sensors/noisy_camera/noisy_camera_cfg.py
src/instinct_mj/sensors/noisy_camera/noisy_grouped_raycaster_camera.py
src/instinct_mj/sensors/noisy_camera/noisy_grouped_raycaster_camera_cfg.py
src/instinct_mj/sensors/noisy_camera/noisy_raycaster_camera.py
src/instinct_mj/sensors/noisy_camera/noisy_raycaster_camera_cfg.py
src/instinct_mj/sensors/noisy_camera/noisy_tiled_camera.py
src/instinct_mj/sensors/noisy_camera/noisy_tiled_camera_cfg.py
src/instinct_mj/sensors/volume_points/__init__.py
src/instinct_mj/sensors/volume_points/points_generator.py
src/instinct_mj/sensors/volume_points/points_generator_cfg.py
src/instinct_mj/sensors/volume_points/volume_points.py
src/instinct_mj/sensors/volume_points/volume_points_cfg.py
src/instinct_mj/sensors/volume_points/volume_points_data.py
src/instinct_mj/tasks/__init__.py
src/instinct_mj/tasks/config/__init__.py
src/instinct_mj/tasks/config/rl_utils.py
src/instinct_mj/tasks/locomotion/__init__.py
src/instinct_mj/tasks/locomotion/config/__init__.py
src/instinct_mj/tasks/locomotion/config/g1/__init__.py
src/instinct_mj/tasks/locomotion/config/g1/flat_env_cfg.py
src/instinct_mj/tasks/locomotion/config/g1/rl_cfg.py
src/instinct_mj/tasks/locomotion/mdp/__init__.py
src/instinct_mj/tasks/locomotion/mdp/curriculums.py
src/instinct_mj/tasks/locomotion/mdp/events.py
src/instinct_mj/tasks/locomotion/mdp/observations.py
src/instinct_mj/tasks/locomotion/mdp/rewards.py
src/instinct_mj/tasks/locomotion/mdp/terminations.py
src/instinct_mj/tasks/parkour/README.md
src/instinct_mj/tasks/parkour/__init__.py
src/instinct_mj/tasks/parkour/config/__init__.py
src/instinct_mj/tasks/parkour/config/g1/__init__.py
src/instinct_mj/tasks/parkour/config/g1/g1_parkour_target_amp_cfg.py
src/instinct_mj/tasks/parkour/config/g1/rl_cfg.py
src/instinct_mj/tasks/parkour/config/parkour_env_cfg.py
src/instinct_mj/tasks/parkour/mdp/__init__.py
src/instinct_mj/tasks/parkour/mdp/commands/__init__.py
src/instinct_mj/tasks/parkour/mdp/commands/commands_cfg.py
src/instinct_mj/tasks/parkour/mdp/commands/pose_velocity_command.py
src/instinct_mj/tasks/parkour/mdp/curriculums.py
src/instinct_mj/tasks/parkour/mdp/events.py
src/instinct_mj/tasks/parkour/mdp/rewards.py
src/instinct_mj/tasks/parkour/mdp/terminations.py
src/instinct_mj/tasks/parkour/mjcf/g1_29dof_torsoBase_popsicle_with_shoe.xml
src/instinct_mj/tasks/parkour/scripts/onnxer.py
src/instinct_mj/tasks/registry.py
src/instinct_mj/tasks/shadowing/README.md
src/instinct_mj/tasks/shadowing/__init__.py
src/instinct_mj/tasks/shadowing/beyondmimic/README.md
src/instinct_mj/tasks/shadowing/beyondmimic/__init__.py
src/instinct_mj/tasks/shadowing/beyondmimic/beyondmimic_env_cfg.py
src/instinct_mj/tasks/shadowing/beyondmimic/config/__init__.py
src/instinct_mj/tasks/shadowing/beyondmimic/config/g1/__init__.py
src/instinct_mj/tasks/shadowing/beyondmimic/config/g1/beyondmimic_plane_cfg.py
src/instinct_mj/tasks/shadowing/beyondmimic/config/g1/rl_cfg.py
src/instinct_mj/tasks/shadowing/mdp/__init__.py
src/instinct_mj/tasks/shadowing/mdp/curriculums.py
src/instinct_mj/tasks/shadowing/mdp/events.py
src/instinct_mj/tasks/shadowing/perceptive/__init__.py
src/instinct_mj/tasks/shadowing/perceptive/config/__init__.py
src/instinct_mj/tasks/shadowing/perceptive/config/g1/__init__.py
src/instinct_mj/tasks/shadowing/perceptive/config/g1/perceptive_shadowing_cfg.py
src/instinct_mj/tasks/shadowing/perceptive/config/g1/perceptive_vae_cfg.py
src/instinct_mj/tasks/shadowing/perceptive/config/g1/rl_cfg.py
src/instinct_mj/tasks/shadowing/perceptive/perceptive_env_cfg.py
src/instinct_mj/tasks/shadowing/perceptive_hoi/__init__.py
src/instinct_mj/tasks/shadowing/perceptive_hoi/config/__init__.py
src/instinct_mj/tasks/shadowing/perceptive_hoi/config/g1/__init__.py
src/instinct_mj/tasks/shadowing/perceptive_hoi/config/g1/perceptive_shadowing_cfg.py
src/instinct_mj/tasks/shadowing/perceptive_hoi/config/g1/rl_cfg.py
src/instinct_mj/tasks/shadowing/perceptive_hoi/perceptive_env_cfg.py
src/instinct_mj/tasks/shadowing/whole_body/__init__.py
src/instinct_mj/tasks/shadowing/whole_body/config/__init__.py
src/instinct_mj/tasks/shadowing/whole_body/config/g1/__init__.py
src/instinct_mj/tasks/shadowing/whole_body/config/g1/plane_shadowing_cfg.py
src/instinct_mj/tasks/shadowing/whole_body/config/g1/rl_cfg.py
src/instinct_mj/tasks/shadowing/whole_body/shadowing_env_cfg.py
src/instinct_mj/terrains/__init__.py
src/instinct_mj/terrains/height_field/__init__.py
src/instinct_mj/terrains/height_field/hf_terrains.py
src/instinct_mj/terrains/height_field/hf_terrains_cfg.py
src/instinct_mj/terrains/height_field/utils.py
src/instinct_mj/terrains/terrain_entity_cfg.py
src/instinct_mj/terrains/terrain_generator.py
src/instinct_mj/terrains/terrain_generator_cfg.py
src/instinct_mj/terrains/terrain_importer.py
src/instinct_mj/terrains/terrain_importer_cfg.py
src/instinct_mj/terrains/trimesh/__init__.py
src/instinct_mj/terrains/trimesh/mesh_terrains.py
src/instinct_mj/terrains/trimesh/mesh_terrains_cfg.py
src/instinct_mj/terrains/trimesh/utils.py
src/instinct_mj/terrains/virtual_obstacle/__init__.py
src/instinct_mj/terrains/virtual_obstacle/edge_cylinder.py
src/instinct_mj/terrains/virtual_obstacle/edge_cylinder_cfg.py
src/instinct_mj/terrains/virtual_obstacle/virtual_obstacle_base.py
src/instinct_mj/utils/__init__.py
src/instinct_mj/utils/buffers/__init__.py
src/instinct_mj/utils/buffers/async_circular_buffer.py
src/instinct_mj/utils/buffers/async_delay_buffer.py
src/instinct_mj/utils/dict.py
src/instinct_mj/utils/humanoid_fk.py
src/instinct_mj/utils/humanoid_ik.py
src/instinct_mj/utils/live_plotter.py
src/instinct_mj/utils/math.py
src/instinct_mj/utils/noise/__init__.py
src/instinct_mj/utils/noise/noise_cfg.py
src/instinct_mj/utils/noise/noise_model.py
src/instinct_mj/utils/perlin.py
src/instinct_mj/utils/retarget_smpl_to_joint.py
src/instinct_mj/utils/timestamped_buffer.py
src/instinct_mj/utils/torch.py
src/instinct_mj/utils/warp/__init__.py
src/instinct_mj/utils/warp/cylinder.py
src/instinct_mj/utils/warp/kernels.py
src/instinct_mj/utils/warp/raycast.py
src/instinct_mj/visualization/__init__.py
src/instinct_mj/visualization/marker_cfg.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 381 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `src/instinct_mj/assets/resources/unitree_g1/meshes` | 84 | 40.9 MB | [`src/instinct_mj/assets/resources/unitree_g1/meshes/_OMITTED.md`](./src/instinct_mj/assets/resources/unitree_g1/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
