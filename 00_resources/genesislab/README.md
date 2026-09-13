# genesislab — 参考资源

> **来源**：`00_open/genesislab/`　｜　**类型**：训练后端候选参考（Genesis + RSL-RL）
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_g1（宇树 G1 人形）
> **定位**：GenesisLab：基于 Genesis 物理引擎的轻量腿足 RL 任务套件（RSL-RL / rl_games 集成）；envs / managers / components / engine 模块化分层，含 Go2 速度跟踪任务与 imitation tracking——第二训练后端（Genesis）候选与「任务套件如何与引擎解耦」的参考
> **收录**：277 个文件 / 1.2 MB（其中推理策略/模型文件 0 个）
> **已省略**：2 个文件 / 3.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（27 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（65 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（1 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（24 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（30 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（5 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（125 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
.github/  （1 个文件）
    workflows/
docs/  （4 个文件）
    dev/
    tutorials/
examples/  （1 个文件）
    (直接文件)/
scripts/  （17 个文件）
    reinforcement_learning/
    setup/
    test/
    tools/
source/  （234 个文件）
    (直接文件)/
    genesis_assets/
    genesis_rl/
    genesis_tasks/
    genesislab/
tests/  （13 个文件）
    (直接文件)/
    engine/
    envs/
    imitation/
    utils/
third_party/  （3 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 250 |
| `.md` | 12 |
| `.toml` | 5 |
| `.sh` | 5 |
| `(无扩展名)` | 2 |
| `.yaml` | 2 |
| `.yml` | 1 |

## 文件索引（项目内相对路径）

```text
.github/workflows/ci.yml
.gitignore
LICENSE
README.md
docs/dev/QUATERNION_FIX_SUMMARY.md
docs/dev/README.md
docs/dev/TODO.md
docs/tutorials/tracking.md
examples/hdri_lighting_example.py
pyproject.toml
scripts/reinforcement_learning/README.md
scripts/reinforcement_learning/rl_games/train.py
scripts/reinforcement_learning/rsl_rl/eval.py
scripts/reinforcement_learning/rsl_rl/play.py
scripts/reinforcement_learning/rsl_rl/train.py
scripts/reinforcement_learning/sb3/play.py
scripts/reinforcement_learning/sb3/train.py
scripts/reinforcement_learning/skrl/train.py
scripts/setup/download_assets.sh
scripts/setup/setup_ext.sh
scripts/setup/setup_ext.yaml
scripts/setup/setup_uv.sh
scripts/setup/setup_vscode.py
scripts/test/clear_usd_cache.sh
scripts/test/test_usd_import.py
scripts/tools/convert_usd_materials.py
scripts/tools/extract_terrain_from_scene.py
source/README.md
source/genesis_assets/genesis_assets/__init__.py
source/genesis_assets/genesis_assets/robots/__init__.py
source/genesis_assets/genesis_assets/robots/booster/__init__.py
source/genesis_assets/genesis_assets/robots/booster/k1.py
source/genesis_assets/genesis_assets/robots/booster/t1.py
source/genesis_assets/genesis_assets/robots/g1/__init__.py
source/genesis_assets/genesis_assets/robots/g1/beyondmimic.py
source/genesis_assets/genesis_assets/robots/g1/official.py
source/genesis_assets/genesis_assets/robots/smpl/__init__.py
source/genesis_assets/genesis_assets/robots/smpl/smpl.py
source/genesis_assets/genesis_assets/robots/smpl/smplx.py
source/genesis_assets/genesis_assets/robots/unitree/__init__.py
source/genesis_assets/genesis_assets/robots/unitree/b2.py
source/genesis_assets/genesis_assets/robots/unitree/go2.py
source/genesis_assets/genesis_assets/robots/unitree/h1.py
source/genesis_assets/pyproject.toml
source/genesis_assets/setup.py
source/genesis_rl/genesis_rl/__init__.py
source/genesis_rl/genesis_rl/rl_games/__init__.py
source/genesis_rl/genesis_rl/rl_games/rl_games.py
source/genesis_rl/genesis_rl/rsl_rl/__init__.py
source/genesis_rl/genesis_rl/rsl_rl/args_cli.py
source/genesis_rl/genesis_rl/rsl_rl/cli/__init__.py
source/genesis_rl/genesis_rl/rsl_rl/cli/play.py
source/genesis_rl/genesis_rl/rsl_rl/cli/train.py
source/genesis_rl/genesis_rl/rsl_rl/configs/__init__.py
source/genesis_rl/genesis_rl/rsl_rl/configs/algo_cfg.py
source/genesis_rl/genesis_rl/rsl_rl/configs/policy_cfg.py
source/genesis_rl/genesis_rl/rsl_rl/configs/runner_cfg.py
source/genesis_rl/genesis_rl/rsl_rl/env_wrappers.py
source/genesis_rl/genesis_rl/rsl_rl/exporter.py
source/genesis_rl/genesis_rl/rsl_rl/gym_utils.py
source/genesis_rl/genesis_rl/rsl_rl/utils/__init__.py
source/genesis_rl/genesis_rl/rsl_rl/utils/config_io.py
source/genesis_rl/genesis_rl/rsl_rl/utils/env_cfg.py
source/genesis_rl/genesis_rl/sb3.py
source/genesis_rl/genesis_rl/skrl.py
source/genesis_rl/pyproject.toml
source/genesis_rl/setup.py
source/genesis_tasks/genesis_tasks/__init__.py
source/genesis_tasks/genesis_tasks/imitation/README.md
source/genesis_tasks/genesis_tasks/imitation/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/agents/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/agents/rsl_rl_ppo_cfg.py
source/genesis_tasks/genesis_tasks/imitation/tracking/components.py
source/genesis_tasks/genesis_tasks/imitation/tracking/mdp/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/mdp/commands.py
source/genesis_tasks/genesis_tasks/imitation/tracking/mdp/events.py
source/genesis_tasks/genesis_tasks/imitation/tracking/mdp/observations.py
source/genesis_tasks/genesis_tasks/imitation/tracking/mdp/rewards.py
source/genesis_tasks/genesis_tasks/imitation/tracking/mdp/terminations.py
source/genesis_tasks/genesis_tasks/imitation/tracking/robots/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/robots/g1/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/robots/g1/g1_tracking_env_cfg.py
source/genesis_tasks/genesis_tasks/imitation/tracking/scripts/fk_to_npz.py
source/genesis_tasks/genesis_tasks/imitation/tracking/tracking_env_cfg.py
source/genesis_tasks/genesis_tasks/imitation/tracking/utils/__init__.py
source/genesis_tasks/genesis_tasks/imitation/tracking/utils/exporter.py
source/genesis_tasks/genesis_tasks/imitation/tracking/utils/my_on_policy_runner.py
source/genesis_tasks/genesis_tasks/locomotion/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/README.md
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/components.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/g1/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/g1/flat_env_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/g1/rsl_rl_ppo_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/hvelocity_env_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/mdp/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/mdp/commands.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/mdp/curriculums.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/mdp/rewards.py
source/genesis_tasks/genesis_tasks/locomotion/hvelocity/mdp/terminations.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/agents/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/agents/rsl_rl_ppo_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/base_velocity_env_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/components.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/mdp/README.md
source/genesis_tasks/genesis_tasks/locomotion/velocity/mdp/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/mdp/commands.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/mdp/curriculums.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/mdp/rewards.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/mdp/terminations.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/b2/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/b2/flat_env_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/b2/rough_env_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/go2/__init__.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/go2/flat_env_cfg.py
source/genesis_tasks/genesis_tasks/locomotion/velocity/robots/go2/rough_env_cfg.py
source/genesis_tasks/genesis_tasks/utils/__init__.py
source/genesis_tasks/genesis_tasks/utils/importer.py
source/genesis_tasks/genesis_tasks/utils/package.py
source/genesis_tasks/pyproject.toml
source/genesis_tasks/setup.py
source/genesislab/genesislab/__init__.py
source/genesislab/genesislab/cli/__init__.py
source/genesislab/genesislab/cli/args.py
source/genesislab/genesislab/components/__init__.py
source/genesislab/genesislab/components/actuators/__init__.py
source/genesislab/genesislab/components/actuators/actuator_base.py
source/genesislab/genesislab/components/actuators/actuator_base_cfg.py
source/genesislab/genesislab/components/actuators/actuator_cfg.py
source/genesislab/genesislab/components/actuators/actuator_net.py
source/genesislab/genesislab/components/actuators/actuator_net_cfg.py
source/genesislab/genesislab/components/actuators/actuator_pd.py
source/genesislab/genesislab/components/actuators/actuator_pd_cfg.py
source/genesislab/genesislab/components/actuators/actuator_robotlib/__init__.py
source/genesislab/genesislab/components/actuators/actuator_robotlib/delay_buffer_wrapper.py
source/genesislab/genesislab/components/actuators/actuator_robotlib/delayed_implicit_actuator.py
source/genesislab/genesislab/components/actuators/actuator_robotlib/unitree_actuator.py
source/genesislab/genesislab/components/actuators/articulation_actions.py
source/genesislab/genesislab/components/additional/__init__.py
source/genesislab/genesislab/components/additional/buffers/__init__.py
source/genesislab/genesislab/components/additional/buffers/circular_buffer.py
source/genesislab/genesislab/components/additional/buffers/delay_buffer.py
source/genesislab/genesislab/components/additional/buffers/linear_interpolation.py
source/genesislab/genesislab/components/additional/noise/__init__.py
source/genesislab/genesislab/components/additional/noise/noise_cfg.py
source/genesislab/genesislab/components/additional/noise/noise_model.py
source/genesislab/genesislab/components/environment_objects/__init__.py
source/genesislab/genesislab/components/environment_objects/object_cfg.py
source/genesislab/genesislab/components/markers/__init__.py
source/genesislab/genesislab/components/markers/arrow_markers.py
source/genesislab/genesislab/components/scene_entity_cfg.py
source/genesislab/genesislab/components/sensors/__init__.py
source/genesislab/genesislab/components/sensors/fake_sensors/__init__.py
source/genesislab/genesislab/components/sensors/fake_sensors/fake_contact_sensor.py
source/genesislab/genesislab/components/sensors/fake_sensors/fake_sensor_base.py
source/genesislab/genesislab/components/sensors/genesis_sensors/__init__.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_camera_sensor.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_contact_bool_sensor.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_depth_camera_sensor.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_imu_sensor.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_lidar_sensor.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_sensor_types.py
source/genesislab/genesislab/components/sensors/genesis_sensors/genesis_sensor_utils.py
source/genesislab/genesislab/components/sensors/genesis_sensors/sensor_base.py
source/genesislab/genesislab/components/sensors/sensor_base.py
source/genesislab/genesislab/components/terrains/__init__.py
source/genesislab/genesislab/components/terrains/config/__init__.py
source/genesislab/genesislab/components/terrains/config/rough.py
source/genesislab/genesislab/components/terrains/genesis_sub_terrain_cfg.py
source/genesislab/genesislab/components/terrains/genesis_terrain_converter.py
source/genesislab/genesislab/components/terrains/height_field/__init__.py
source/genesislab/genesislab/components/terrains/height_field/hf_terrains.py
source/genesislab/genesislab/components/terrains/height_field/hf_terrains_cfg.py
source/genesislab/genesislab/components/terrains/height_field/utils.py
source/genesislab/genesislab/components/terrains/sub_terrain_cfg.py
source/genesislab/genesislab/components/terrains/terrain_cfg.py
source/genesislab/genesislab/components/terrains/terrain_generator.py
source/genesislab/genesislab/components/terrains/terrain_generator_cfg.py
source/genesislab/genesislab/components/terrains/terrain_importer.py
source/genesislab/genesislab/components/terrains/terrain_importer_cfg.py
source/genesislab/genesislab/components/terrains/trimesh/__init__.py
source/genesislab/genesislab/components/terrains/trimesh/mesh_terrains.py
source/genesislab/genesislab/components/terrains/trimesh/mesh_terrains_cfg.py
source/genesislab/genesislab/components/terrains/trimesh/utils.py
source/genesislab/genesislab/components/terrains/utils.py
source/genesislab/genesislab/engine/assets/__init__.py
source/genesislab/genesislab/engine/assets/articulation/__init__.py
source/genesislab/genesislab/engine/assets/articulation/articulation.py
source/genesislab/genesislab/engine/assets/articulation/articulation_cfg.py
source/genesislab/genesislab/engine/assets/lab_asset_base.py
source/genesislab/genesislab/engine/assets/robot/__init__.py
source/genesislab/genesislab/engine/assets/robot/actuator_manager.py
source/genesislab/genesislab/engine/assets/robot/robot.py
source/genesislab/genesislab/engine/assets/robot/robot_cfg.py
source/genesislab/genesislab/engine/assets/utils/__init__.py
source/genesislab/genesislab/engine/assets/utils/name_normalizer.py
source/genesislab/genesislab/engine/binding.py
source/genesislab/genesislab/engine/entity/__init__.py
source/genesislab/genesislab/engine/entity/lab_entity.py
source/genesislab/genesislab/engine/entity/lab_entity_data.py
source/genesislab/genesislab/engine/gstype/__init__.py
source/genesislab/genesislab/engine/scene/__init__.py
source/genesislab/genesislab/engine/scene/camera_cfg.py
source/genesislab/genesislab/engine/scene/lab_scene.py
source/genesislab/genesislab/engine/scene/lab_scene_cfg.py
source/genesislab/genesislab/engine/scene/scene_builder.py
source/genesislab/genesislab/engine/scene/scene_controller.py
source/genesislab/genesislab/engine/scene/terrain_runtime.py
source/genesislab/genesislab/engine/sim/__init__.py
source/genesislab/genesislab/engine/sim/sim_cfg.py
source/genesislab/genesislab/engine/visualize.py
source/genesislab/genesislab/envs/__init__.py
source/genesislab/genesislab/envs/common/__init__.py
source/genesislab/genesislab/envs/common/viewer.py
source/genesislab/genesislab/envs/manager_based_genesis_env.py
source/genesislab/genesislab/envs/manager_based_rl_env.py
source/genesislab/genesislab/envs/mdp/__init__.py
source/genesislab/genesislab/envs/mdp/actions/README.md
source/genesislab/genesislab/envs/mdp/actions/__init__.py
source/genesislab/genesislab/envs/mdp/actions/_action_common.py
source/genesislab/genesislab/envs/mdp/actions/genesis_original_action.py
source/genesislab/genesislab/envs/mdp/actions/joint_position_actions.py
source/genesislab/genesislab/envs/mdp/events/__init__.py
source/genesislab/genesislab/envs/mdp/events/perturb.py
source/genesislab/genesislab/envs/mdp/events/randomization.py
source/genesislab/genesislab/envs/mdp/events/reset.py
source/genesislab/genesislab/envs/mdp/events/utils.py
source/genesislab/genesislab/envs/mdp/observations/__init__.py
source/genesislab/genesislab/envs/mdp/observations/proprioception.py
source/genesislab/genesislab/managers/__init__.py
source/genesislab/genesislab/managers/action_manager.py
source/genesislab/genesislab/managers/command_manager.py
source/genesislab/genesislab/managers/curriculum_manager.py
source/genesislab/genesislab/managers/event_manager.py
source/genesislab/genesislab/managers/manager_base.py
source/genesislab/genesislab/managers/manager_term_cfg.py
source/genesislab/genesislab/managers/object_manager.py
source/genesislab/genesislab/managers/observation_manager.py
source/genesislab/genesislab/managers/recorder_manager.py
source/genesislab/genesislab/managers/reward_manager.py
source/genesislab/genesislab/managers/termination_manager.py
source/genesislab/genesislab/utils/__init__.py
source/genesislab/genesislab/utils/configclass/__init__.py
source/genesislab/genesislab/utils/configclass/configclass.py
source/genesislab/genesislab/utils/configclass/dict.py
source/genesislab/genesislab/utils/configclass/string.py
source/genesislab/genesislab/utils/imports.py
source/genesislab/genesislab/utils/io.py
source/genesislab/genesislab/utils/lighting.py
source/genesislab/genesislab/utils/math/__init__.py
source/genesislab/genesislab/utils/math/rotation.py
source/genesislab/genesislab/utils/math/sample.py
source/genesislab/genesislab/utils/timer.py
source/genesislab/genesislab/utils/timing.py
source/genesislab/genesislab/utils/typing.py
source/genesislab/genesislab/utils/warp.py
source/genesislab/pyproject.toml
source/genesislab/setup.py
tests/conftest.py
tests/engine/__init__.py
tests/engine/entity/__init__.py
tests/engine/entity/test_lab_entity_data.py
tests/envs/__init__.py
tests/envs/mdp/__init__.py
tests/envs/mdp/events/__init__.py
tests/envs/mdp/events/test_event_utils.py
tests/imitation/__init__.py
tests/imitation/test_motion_command.py
tests/utils/__init__.py
tests/utils/math/__init__.py
tests/utils/math/test_rotation.py
third_party/README.md
third_party/setup_third_party.sh
third_party/third_party_repos.yaml
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 587 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `.docs/assets/intro` | 1 | 2.4 MB | [`.docs/assets/intro/_OMITTED.md`](./.docs/assets/intro/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
