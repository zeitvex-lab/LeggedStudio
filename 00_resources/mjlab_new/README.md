# mjlab_new — 参考资源

> **来源**：`00_open/mjlab_new/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_g1（宇树 G1 人形）
> **定位**：mjlab 新版：机型资产 + MuJoCo RL 任务
> **收录**：407 个文件 / 3.9 MB（其中推理策略/模型文件 0 个）
> **已省略**：106 个文件 / 55.5 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（10 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（78 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（19 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（1 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（98 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（201 个）：文档、说明、许可与零散脚本

## 目录构成

```text
mjlab/  （407 个文件）
    (直接文件)/
    .claude/
    .github/
    docs/
    notebooks/
    scripts/
    src/
    tests/
    typings/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 288 |
| `.rst` | 50 |
| `.md` | 12 |
| `.xml` | 12 |
| `.pyi` | 10 |
| `.yml` | 7 |
| `(无扩展名)` | 6 |
| `.yaml` | 6 |
| `.sh` | 5 |
| `.ipynb` | 2 |
| `.cff` | 1 |
| `.toml` | 1 |
| `.json` | 1 |
| `.bib` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
mjlab/.claude/commands/commit-push-pr.md
mjlab/.claude/commands/update-mjwarp.md
mjlab/.claude/settings.json
mjlab/.dockerignore
mjlab/.github/workflows/ci.yml
mjlab/.github/workflows/claude-code-review.yml
mjlab/.github/workflows/claude.yml
mjlab/.github/workflows/docker.yml
mjlab/.github/workflows/docs.yml
mjlab/.github/workflows/nightly.yml
mjlab/.github/workflows/release.yml
mjlab/.gitignore
mjlab/.pre-commit-config.yaml
mjlab/.python-version
mjlab/AGENTS.md
mjlab/CITATION.cff
mjlab/CLAUDE.md
mjlab/CONTRIBUTING.md
mjlab/Dockerfile
mjlab/LICENSE
mjlab/Makefile
mjlab/README.md
mjlab/RELEASING.md
mjlab/docs/_templates/versioning.html
mjlab/docs/conf.py
mjlab/docs/index.rst
mjlab/docs/source/_static/css/custom.css
mjlab/docs/source/_static/refs.bib
mjlab/docs/source/actions.rst
mjlab/docs/source/actuators.rst
mjlab/docs/source/api/actuator.rst
mjlab/docs/source/api/entity.rst
mjlab/docs/source/api/envs.rst
mjlab/docs/source/api/index.rst
mjlab/docs/source/api/managers.rst
mjlab/docs/source/api/rl.rst
mjlab/docs/source/api/scene.rst
mjlab/docs/source/api/sensor.rst
mjlab/docs/source/api/sim.rst
mjlab/docs/source/api/tasks.rst
mjlab/docs/source/api/terrains.rst
mjlab/docs/source/api/viewer.rst
mjlab/docs/source/architecture_overview.rst
mjlab/docs/source/changelog.rst
mjlab/docs/source/commands.rst
mjlab/docs/source/contributing.rst
mjlab/docs/source/curriculum.rst
mjlab/docs/source/debugging/export_scene.rst
mjlab/docs/source/debugging/nan_guard.rst
mjlab/docs/source/entity/entity_data.rst
mjlab/docs/source/entity/index.rst
mjlab/docs/source/entity/per_world_mesh.rst
mjlab/docs/source/environment_config.rst
mjlab/docs/source/events.rst
mjlab/docs/source/faq.rst
mjlab/docs/source/installation.rst
mjlab/docs/source/metrics.rst
mjlab/docs/source/migration_isaac_lab.rst
mjlab/docs/source/motivation.rst
mjlab/docs/source/observations.rst
mjlab/docs/source/randomization.rst
mjlab/docs/source/recorders.rst
mjlab/docs/source/research.rst
mjlab/docs/source/rewards.rst
mjlab/docs/source/scene.rst
mjlab/docs/source/sensors/index.rst
mjlab/docs/source/sensors/raycast_sensor.rst
mjlab/docs/source/sensors/rgbd_camera.rst
mjlab/docs/source/terminations.rst
mjlab/docs/source/terrain.rst
mjlab/docs/source/training/cloud.rst
mjlab/docs/source/training/distributed_training.rst
mjlab/docs/source/training/motion_imitation.rst
mjlab/docs/source/training/rsl_rl.rst
mjlab/docs/source/tutorials.rst
mjlab/docs/source/tutorials/cartpole.rst
mjlab/docs/source/viewers.rst
mjlab/notebooks/create_new_task.ipynb
mjlab/notebooks/demo.ipynb
mjlab/pyproject.toml
mjlab/scripts/benchmarks/README.md
mjlab/scripts/benchmarks/generate_report.py
mjlab/scripts/benchmarks/measure_throughput.py
mjlab/scripts/benchmarks/nightly_train.sh
mjlab/scripts/benchmarks/systemd/README.md
mjlab/scripts/benchmarks/systemd/mjlab-nightly.service
mjlab/scripts/benchmarks/systemd/mjlab-nightly.timer
mjlab/scripts/cloud/README.md
mjlab/scripts/cloud/sweep-agent.yaml
mjlab/scripts/cloud/sweep-cluster.yaml
mjlab/scripts/cloud/sweep-launch.sh
mjlab/scripts/cloud/sweep.yaml
mjlab/scripts/cloud/train-docker.yaml
mjlab/scripts/cloud/train.yaml
mjlab/scripts/demos/body_impulse.py
mjlab/scripts/demos/contact_sensor_decimation.py
mjlab/scripts/demos/differential_ik.py
mjlab/scripts/demos/flat_patch_terrain.py
mjlab/scripts/demos/raycast_sensor.py
mjlab/scripts/fix_mjpython_macos.sh
mjlab/scripts/run_docker.sh
mjlab/scripts/tools/render_terrain_gallery.py
mjlab/scripts/tools/terrain_explorer.py
mjlab/src/mjlab/__init__.py
mjlab/src/mjlab/actuator/__init__.py
mjlab/src/mjlab/actuator/actuator.py
mjlab/src/mjlab/actuator/builtin_actuator.py
mjlab/src/mjlab/actuator/builtin_group.py
mjlab/src/mjlab/actuator/dc_actuator.py
mjlab/src/mjlab/actuator/fused_group.py
mjlab/src/mjlab/actuator/learned_actuator.py
mjlab/src/mjlab/actuator/pd_actuator.py
mjlab/src/mjlab/actuator/xml_actuator.py
mjlab/src/mjlab/asset_zoo/README.md
mjlab/src/mjlab/asset_zoo/__init__.py
mjlab/src/mjlab/asset_zoo/robots/__init__.py
mjlab/src/mjlab/asset_zoo/robots/i2rt_yam/__init__.py
mjlab/src/mjlab/asset_zoo/robots/i2rt_yam/xmls/yam.xml
mjlab/src/mjlab/asset_zoo/robots/i2rt_yam/yam_constants.py
mjlab/src/mjlab/asset_zoo/robots/unitree_g1/__init__.py
mjlab/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py
mjlab/src/mjlab/asset_zoo/robots/unitree_g1/xmls/g1.xml
mjlab/src/mjlab/asset_zoo/robots/unitree_go1/__init__.py
mjlab/src/mjlab/asset_zoo/robots/unitree_go1/go1_constants.py
mjlab/src/mjlab/asset_zoo/robots/unitree_go1/xmls/go1.xml
mjlab/src/mjlab/entity/__init__.py
mjlab/src/mjlab/entity/data.py
mjlab/src/mjlab/entity/entity.py
mjlab/src/mjlab/entity/variants.py
mjlab/src/mjlab/envs/__init__.py
mjlab/src/mjlab/envs/manager_based_rl_env.py
mjlab/src/mjlab/envs/mdp/__init__.py
mjlab/src/mjlab/envs/mdp/actions/__init__.py
mjlab/src/mjlab/envs/mdp/actions/actions.py
mjlab/src/mjlab/envs/mdp/actions/differential_ik.py
mjlab/src/mjlab/envs/mdp/curriculums.py
mjlab/src/mjlab/envs/mdp/dr/__init__.py
mjlab/src/mjlab/envs/mdp/dr/_core.py
mjlab/src/mjlab/envs/mdp/dr/_types.py
mjlab/src/mjlab/envs/mdp/dr/actuator.py
mjlab/src/mjlab/envs/mdp/dr/body.py
mjlab/src/mjlab/envs/mdp/dr/camera.py
mjlab/src/mjlab/envs/mdp/dr/geom.py
mjlab/src/mjlab/envs/mdp/dr/joint.py
mjlab/src/mjlab/envs/mdp/dr/light.py
mjlab/src/mjlab/envs/mdp/dr/material.py
mjlab/src/mjlab/envs/mdp/dr/pair.py
mjlab/src/mjlab/envs/mdp/dr/site.py
mjlab/src/mjlab/envs/mdp/dr/tendon.py
mjlab/src/mjlab/envs/mdp/events.py
mjlab/src/mjlab/envs/mdp/metrics.py
mjlab/src/mjlab/envs/mdp/observations.py
mjlab/src/mjlab/envs/mdp/rewards.py
mjlab/src/mjlab/envs/mdp/terminations.py
mjlab/src/mjlab/envs/types.py
mjlab/src/mjlab/managers/__init__.py
mjlab/src/mjlab/managers/action_manager.py
mjlab/src/mjlab/managers/command_manager.py
mjlab/src/mjlab/managers/curriculum_manager.py
mjlab/src/mjlab/managers/event_manager.py
mjlab/src/mjlab/managers/manager_base.py
mjlab/src/mjlab/managers/metrics_manager.py
mjlab/src/mjlab/managers/observation_manager.py
mjlab/src/mjlab/managers/recorder_manager.py
mjlab/src/mjlab/managers/reward_manager.py
mjlab/src/mjlab/managers/scene_entity_config.py
mjlab/src/mjlab/managers/termination_manager.py
mjlab/src/mjlab/py.typed
mjlab/src/mjlab/rl/__init__.py
mjlab/src/mjlab/rl/config.py
mjlab/src/mjlab/rl/exporter_utils.py
mjlab/src/mjlab/rl/runner.py
mjlab/src/mjlab/rl/spatial_softmax.py
mjlab/src/mjlab/rl/vecenv_wrapper.py
mjlab/src/mjlab/scene/__init__.py
mjlab/src/mjlab/scene/scene.py
mjlab/src/mjlab/scene/scene.xml
mjlab/src/mjlab/scripts/_cli.py
mjlab/src/mjlab/scripts/csv_to_npz.py
mjlab/src/mjlab/scripts/demo.py
mjlab/src/mjlab/scripts/export_scene.py
mjlab/src/mjlab/scripts/gcs.py
mjlab/src/mjlab/scripts/list_envs.py
mjlab/src/mjlab/scripts/nan_viz.py
mjlab/src/mjlab/scripts/play.py
mjlab/src/mjlab/scripts/train.py
mjlab/src/mjlab/scripts/visualize_terrain.py
mjlab/src/mjlab/sensor/__init__.py
mjlab/src/mjlab/sensor/builtin_sensor.py
mjlab/src/mjlab/sensor/camera_sensor.py
mjlab/src/mjlab/sensor/contact_sensor.py
mjlab/src/mjlab/sensor/raycast_sensor.py
mjlab/src/mjlab/sensor/sensor.py
mjlab/src/mjlab/sensor/sensor_context.py
mjlab/src/mjlab/sensor/terrain_height_sensor.py
mjlab/src/mjlab/sim/__init__.py
mjlab/src/mjlab/sim/randomization.py
mjlab/src/mjlab/sim/sim.py
mjlab/src/mjlab/sim/sim_data.py
mjlab/src/mjlab/tasks/__init__.py
mjlab/src/mjlab/tasks/cartpole/__init__.py
mjlab/src/mjlab/tasks/cartpole/cartpole.xml
mjlab/src/mjlab/tasks/cartpole/cartpole_env_cfg.py
mjlab/src/mjlab/tasks/manipulation/__init__.py
mjlab/src/mjlab/tasks/manipulation/config/__init__.py
mjlab/src/mjlab/tasks/manipulation/config/yam/__init__.py
mjlab/src/mjlab/tasks/manipulation/config/yam/env_cfgs.py
mjlab/src/mjlab/tasks/manipulation/config/yam/rl_cfg.py
mjlab/src/mjlab/tasks/manipulation/lift_cube_env_cfg.py
mjlab/src/mjlab/tasks/manipulation/mdp/__init__.py
mjlab/src/mjlab/tasks/manipulation/mdp/commands.py
mjlab/src/mjlab/tasks/manipulation/mdp/observations.py
mjlab/src/mjlab/tasks/manipulation/mdp/rewards.py
mjlab/src/mjlab/tasks/manipulation/mdp/terminations.py
mjlab/src/mjlab/tasks/manipulation/rl/__init__.py
mjlab/src/mjlab/tasks/manipulation/rl/runner.py
mjlab/src/mjlab/tasks/registry.py
mjlab/src/mjlab/tasks/tracking/__init__.py
mjlab/src/mjlab/tasks/tracking/config/__init__.py
mjlab/src/mjlab/tasks/tracking/config/g1/__init__.py
mjlab/src/mjlab/tasks/tracking/config/g1/env_cfgs.py
mjlab/src/mjlab/tasks/tracking/config/g1/rl_cfg.py
mjlab/src/mjlab/tasks/tracking/mdp/__init__.py
mjlab/src/mjlab/tasks/tracking/mdp/commands.py
mjlab/src/mjlab/tasks/tracking/mdp/metrics.py
mjlab/src/mjlab/tasks/tracking/mdp/observations.py
mjlab/src/mjlab/tasks/tracking/mdp/rewards.py
mjlab/src/mjlab/tasks/tracking/mdp/terminations.py
mjlab/src/mjlab/tasks/tracking/rl/__init__.py
mjlab/src/mjlab/tasks/tracking/rl/runner.py
mjlab/src/mjlab/tasks/tracking/scripts/evaluate.py
mjlab/src/mjlab/tasks/tracking/tracking_env_cfg.py
mjlab/src/mjlab/tasks/velocity/__init__.py
mjlab/src/mjlab/tasks/velocity/config/__init__.py
mjlab/src/mjlab/tasks/velocity/config/g1/__init__.py
mjlab/src/mjlab/tasks/velocity/config/g1/env_cfgs.py
mjlab/src/mjlab/tasks/velocity/config/g1/rl_cfg.py
mjlab/src/mjlab/tasks/velocity/config/go1/__init__.py
mjlab/src/mjlab/tasks/velocity/config/go1/env_cfgs.py
mjlab/src/mjlab/tasks/velocity/config/go1/rl_cfg.py
mjlab/src/mjlab/tasks/velocity/mdp/__init__.py
mjlab/src/mjlab/tasks/velocity/mdp/curriculums.py
mjlab/src/mjlab/tasks/velocity/mdp/observations.py
mjlab/src/mjlab/tasks/velocity/mdp/rewards.py
mjlab/src/mjlab/tasks/velocity/mdp/terminations.py
mjlab/src/mjlab/tasks/velocity/mdp/terrain_utils.py
mjlab/src/mjlab/tasks/velocity/mdp/velocity_command.py
mjlab/src/mjlab/tasks/velocity/rl/__init__.py
mjlab/src/mjlab/tasks/velocity/rl/runner.py
mjlab/src/mjlab/tasks/velocity/velocity_env_cfg.py
mjlab/src/mjlab/terrains/README.md
mjlab/src/mjlab/terrains/__init__.py
mjlab/src/mjlab/terrains/config.py
mjlab/src/mjlab/terrains/heightfield_terrains.py
mjlab/src/mjlab/terrains/primitive_terrains.py
mjlab/src/mjlab/terrains/terrain_entity.py
mjlab/src/mjlab/terrains/terrain_generator.py
mjlab/src/mjlab/terrains/utils.py
mjlab/src/mjlab/utils/__init__.py
mjlab/src/mjlab/utils/actuator.py
mjlab/src/mjlab/utils/buffers/__init__.py
mjlab/src/mjlab/utils/buffers/circular_buffer.py
mjlab/src/mjlab/utils/buffers/delay_buffer.py
mjlab/src/mjlab/utils/color.py
mjlab/src/mjlab/utils/gpu.py
mjlab/src/mjlab/utils/lab_api/__init__.py
mjlab/src/mjlab/utils/lab_api/math.py
mjlab/src/mjlab/utils/lab_api/string.py
mjlab/src/mjlab/utils/lab_api/tasks/importer.py
mjlab/src/mjlab/utils/logging.py
mjlab/src/mjlab/utils/mujoco.py
mjlab/src/mjlab/utils/nan_guard.py
mjlab/src/mjlab/utils/noise/__init__.py
mjlab/src/mjlab/utils/noise/noise_cfg.py
mjlab/src/mjlab/utils/noise/noise_model.py
mjlab/src/mjlab/utils/os.py
mjlab/src/mjlab/utils/random.py
mjlab/src/mjlab/utils/spaces.py
mjlab/src/mjlab/utils/spec.py
mjlab/src/mjlab/utils/spec_config.py
mjlab/src/mjlab/utils/string.py
mjlab/src/mjlab/utils/torch.py
mjlab/src/mjlab/utils/wandb.py
mjlab/src/mjlab/utils/wrappers/__init__.py
mjlab/src/mjlab/utils/wrappers/video_recorder.py
mjlab/src/mjlab/utils/xml.py
mjlab/src/mjlab/viewer/__init__.py
mjlab/src/mjlab/viewer/base.py
mjlab/src/mjlab/viewer/debug_visualizer.py
mjlab/src/mjlab/viewer/model_sync.py
mjlab/src/mjlab/viewer/native/__init__.py
mjlab/src/mjlab/viewer/native/keys.py
mjlab/src/mjlab/viewer/native/viewer.py
mjlab/src/mjlab/viewer/native/visualizer.py
mjlab/src/mjlab/viewer/offscreen_renderer.py
mjlab/src/mjlab/viewer/viewer_config.py
mjlab/src/mjlab/viewer/viser/__init__.py
mjlab/src/mjlab/viewer/viser/camera_viewer.py
mjlab/src/mjlab/viewer/viser/overlays.py
mjlab/src/mjlab/viewer/viser/reward_bar_panel.py
mjlab/src/mjlab/viewer/viser/scene.py
mjlab/src/mjlab/viewer/viser/term_plotter.py
mjlab/src/mjlab/viewer/viser/viewer.py
mjlab/tests/conftest.py
mjlab/tests/fixtures/biped.xml
mjlab/tests/fixtures/fixed_base_articulated.xml
mjlab/tests/fixtures/fixed_base_box.xml
mjlab/tests/fixtures/floating_base_articulated.xml
mjlab/tests/fixtures/floating_base_box.xml
mjlab/tests/fixtures/quadcopter.xml
mjlab/tests/fixtures/tendon_finger.xml
mjlab/tests/smoke_test.py
mjlab/tests/test_action_manager.py
mjlab/tests/test_actions.py
mjlab/tests/test_actuator.py
mjlab/tests/test_actuator_builtin_group.py
mjlab/tests/test_asset_zoo.py
mjlab/tests/test_auto_reset.py
mjlab/tests/test_builtin_dcmotor_actuator.py
mjlab/tests/test_builtin_group.py
mjlab/tests/test_builtin_pd_actuator.py
mjlab/tests/test_builtin_sensor.py
mjlab/tests/test_camera_sensor.py
mjlab/tests/test_circular_buffer.py
mjlab/tests/test_command_manager.py
mjlab/tests/test_contact_sensor.py
mjlab/tests/test_curriculum_manager.py
mjlab/tests/test_dc_actuator.py
mjlab/tests/test_delay_buffer.py
mjlab/tests/test_delayed_actuator.py
mjlab/tests/test_differential_ik_action.py
mjlab/tests/test_domain_randomization.py
mjlab/tests/test_encoder_bias.py
mjlab/tests/test_entity.py
mjlab/tests/test_entity_data.py
mjlab/tests/test_envs_curriculums.py
mjlab/tests/test_events.py
mjlab/tests/test_flat_patch_sampling.py
mjlab/tests/test_foot_height_sensor.py
mjlab/tests/test_fused_group.py
mjlab/tests/test_g1_constants.py
mjlab/tests/test_go1_constants.py
mjlab/tests/test_gpu_selection.py
mjlab/tests/test_lab_api_math.py
mjlab/tests/test_learned_actuator.py
mjlab/tests/test_manager_config_immutability.py
mjlab/tests/test_manipulation_commands.py
mjlab/tests/test_manipulation_observations.py
mjlab/tests/test_metrics_manager.py
mjlab/tests/test_nan_guard.py
mjlab/tests/test_native_viewer_actions.py
mjlab/tests/test_notebooks.py
mjlab/tests/test_observation_delay.py
mjlab/tests/test_observation_history.py
mjlab/tests/test_observation_manager.py
mjlab/tests/test_observation_nan_handling.py
mjlab/tests/test_observation_noise.py
mjlab/tests/test_offscreen_renderer.py
mjlab/tests/test_pd_actuator.py
mjlab/tests/test_perlin_terrain.py
mjlab/tests/test_projected_gravity_sensor.py
mjlab/tests/test_raycast_sensor.py
mjlab/tests/test_recorder_manager.py
mjlab/tests/test_reward_bar_panel.py
mjlab/tests/test_rewards.py
mjlab/tests/test_rl_exporter.py
mjlab/tests/test_runner.py
mjlab/tests/test_scene.py
mjlab/tests/test_scene_entity_config.py
mjlab/tests/test_sensor_caching.py
mjlab/tests/test_sim.py
mjlab/tests/test_sim_data.py
mjlab/tests/test_spec_config.py
mjlab/tests/test_spec_utils.py
mjlab/tests/test_task_configs.py
mjlab/tests/test_terminations.py
mjlab/tests/test_terrain_config.py
mjlab/tests/test_terrain_proportion_spawning.py
mjlab/tests/test_terrain_utils.py
mjlab/tests/test_terrains.py
mjlab/tests/test_tracking_metrics.py
mjlab/tests/test_tracking_task.py
mjlab/tests/test_tyro_defaults.py
mjlab/tests/test_tyro_flags.py
mjlab/tests/test_variants.py
mjlab/tests/test_velocity_command.py
mjlab/tests/test_velocity_rewards.py
mjlab/tests/test_velocity_task.py
mjlab/tests/test_velocity_terrain_curriculum.py
mjlab/tests/test_video_recorder.py
mjlab/tests/test_viewer_tick.py
mjlab/tests/test_viser_conversions.py
mjlab/tests/test_viser_update_policy.py
mjlab/tests/test_xml_actuator.py
mjlab/tests/test_xml_utils.py
mjlab/typings/generate_mujoco_stubs.sh
mjlab/typings/mujoco/__init__.pyi
mjlab/typings/mujoco/_callbacks.pyi
mjlab/typings/mujoco/_constants.pyi
mjlab/typings/mujoco/_enums.pyi
mjlab/typings/mujoco/_errors.pyi
mjlab/typings/mujoco/_functions.pyi
mjlab/typings/mujoco/_render.pyi
mjlab/typings/mujoco/_specs.pyi
mjlab/typings/mujoco/_structs.pyi
mjlab/typings/mujoco/viewer.pyi
mjlab/typings/postprocess_stubs.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `mjlab` | 1 | 857 KB | [`mjlab/_OMITTED.md`](./mjlab/_OMITTED.md) |
| `mjlab/docs/source/_static` | 14 | 9.8 MB | [`mjlab/docs/source/_static/_OMITTED.md`](./mjlab/docs/source/_static/_OMITTED.md) |
| `mjlab/docs/source/_static/changelog` | 3 | 1.9 MB | [`mjlab/docs/source/_static/changelog/_OMITTED.md`](./mjlab/docs/source/_static/changelog/_OMITTED.md) |
| `mjlab/docs/source/_static/content` | 8 | 3.2 MB | [`mjlab/docs/source/_static/content/_OMITTED.md`](./mjlab/docs/source/_static/content/_OMITTED.md) |
| `mjlab/docs/source/_static/terrains` | 17 | 4.9 MB | [`mjlab/docs/source/_static/terrains/_OMITTED.md`](./mjlab/docs/source/_static/terrains/_OMITTED.md) |
| `mjlab/docs/source/_static/tutorials` | 2 | 670 KB | [`mjlab/docs/source/_static/tutorials/_OMITTED.md`](./mjlab/docs/source/_static/tutorials/_OMITTED.md) |
| `mjlab/scripts/benchmarks/nightly_images` | 3 | 624 KB | [`mjlab/scripts/benchmarks/nightly_images/_OMITTED.md`](./mjlab/scripts/benchmarks/nightly_images/_OMITTED.md) |
| `mjlab/src/mjlab/asset_zoo/robots/i2rt_yam/xmls/assets` | 18 | 5.0 MB | [`mjlab/src/mjlab/asset_zoo/robots/i2rt_yam/xmls/assets/_OMITTED.md`](./mjlab/src/mjlab/asset_zoo/robots/i2rt_yam/xmls/assets/_OMITTED.md) |
| `mjlab/src/mjlab/asset_zoo/robots/unitree_g1/xmls/assets` | 35 | 18.8 MB | [`mjlab/src/mjlab/asset_zoo/robots/unitree_g1/xmls/assets/_OMITTED.md`](./mjlab/src/mjlab/asset_zoo/robots/unitree_g1/xmls/assets/_OMITTED.md) |
| `mjlab/src/mjlab/asset_zoo/robots/unitree_go1/xmls/assets` | 5 | 9.8 MB | [`mjlab/src/mjlab/asset_zoo/robots/unitree_go1/xmls/assets/_OMITTED.md`](./mjlab/src/mjlab/asset_zoo/robots/unitree_go1/xmls/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
