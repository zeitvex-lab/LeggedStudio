# unitree_rl_mjlab_go2w — 参考资源

> **来源**：`00_open/unitree_rl_mjlab_go2w/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2w（宇树 Go2W 轮足）、unitree_go2（宇树 Go2 四足）、unitree_g1（宇树 G1 人形）
> **定位**：Go2W 专用 mjlab RL 工程（含 Go2/G1 资产）
> **收录**：384 个文件 / 18.5 MB（其中推理策略/模型文件 3 个）
> **已省略**：180 个文件 / 217.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（12 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（89 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（119 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（7 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（3 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（11 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（143 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
deploy/  （119 个文件）
    include/
    robots/
    thirdparty/
doc/  （6 个文件）
    (直接文件)/
    license/
mjlab/  （238 个文件）
    (直接文件)/
    actuator/
    asset_zoo/
    entity/
    envs/
    managers/
    motions/
    rl/
    rsl_rl/
    scene/
    sensor/
    sim/
    tasks/
    terrains/
    utils/
    viewer/
scripts/  （8 个文件）
    (直接文件)/
tests/  （9 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 248 |
| `.h` | 49 |
| `(无扩展名)` | 17 |
| `.cpp` | 13 |
| `.md` | 12 |
| `.yaml` | 12 |
| `.txt` | 8 |
| `.cmake` | 8 |
| `.xml` | 6 |
| `.onnx` | 3 |
| `.data` | 3 |
| `.pc` | 2 |
| `.hpp` | 1 |
| `.npz` | 1 |
| `.csv` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
LICENCE
README.md
deploy/include/FSM/BaseState.h
deploy/include/FSM/CtrlFSM.h
deploy/include/FSM/FSMState.h
deploy/include/FSM/State_FixStand.h
deploy/include/FSM/State_Passive.h
deploy/include/FSM/State_RLBase.h
deploy/include/LinearInterpolator.h
deploy/include/isaaclab/algorithms/algorithms.h
deploy/include/isaaclab/assets/articulation/articulation.h
deploy/include/isaaclab/devices/keyboard/keyboard.h
deploy/include/isaaclab/envs/manager_based_rl_env.h
deploy/include/isaaclab/envs/mdp/actions/joint_actions.h
deploy/include/isaaclab/envs/mdp/observations/observations.h
deploy/include/isaaclab/envs/mdp/terminations.h
deploy/include/isaaclab/manager/action_manager.h
deploy/include/isaaclab/manager/manager_term_cfg.h
deploy/include/isaaclab/manager/observation_manager.h
deploy/include/isaaclab/utils/utils.h
deploy/include/param.h
deploy/include/unitree_articulation.h
deploy/include/unitree_joystick_dsl.hpp
deploy/robots/g1/CMakeLists.txt
deploy/robots/g1/config/config.yaml
deploy/robots/g1/config/policy/mimic/dance1_subject2/exported/policy.onnx
deploy/robots/g1/config/policy/mimic/dance1_subject2/exported/policy.onnx.data
deploy/robots/g1/config/policy/mimic/dance1_subject2/params/dance1_subject2.npz
deploy/robots/g1/config/policy/mimic/dance1_subject2/params/deploy.yaml
deploy/robots/g1/config/policy/velocity/v0/exported/policy.onnx
deploy/robots/g1/config/policy/velocity/v0/exported/policy.onnx.data
deploy/robots/g1/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/g1/include/State_Mimic.h
deploy/robots/g1/include/Types.h
deploy/robots/g1/main.cpp
deploy/robots/g1/src/State_Mimic.cpp
deploy/robots/g1/src/State_RLBase.cpp
deploy/robots/g1_23dof/CMakeLists.txt
deploy/robots/g1_23dof/config/config.yaml
deploy/robots/g1_23dof/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/g1_23dof/include/Types.h
deploy/robots/g1_23dof/main.cpp
deploy/robots/g1_23dof/src/State_RLBase.cpp
deploy/robots/go2/CMakeLists.txt
deploy/robots/go2/config/config.yaml
deploy/robots/go2/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/go2/include/Types.h
deploy/robots/go2/main.cpp
deploy/robots/go2/src/State_RLBase.cpp
deploy/robots/go2w/CMakeLists.txt
deploy/robots/go2w/config/config.yaml
deploy/robots/go2w/config/policy/velocity/v0/README.md
deploy/robots/go2w/config/policy/velocity/v0/exported/.gitkeep
deploy/robots/go2w/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/go2w/config/policy/velocity_legs_only/v0/README.md
deploy/robots/go2w/config/policy/velocity_legs_only/v0/exported/.gitkeep
deploy/robots/go2w/config/policy/velocity_legs_only/v0/exported/policy.onnx
deploy/robots/go2w/config/policy/velocity_legs_only/v0/exported/policy.onnx.data
deploy/robots/go2w/config/policy/velocity_legs_only/v0/params/deploy.yaml
deploy/robots/go2w/include/Types.h
deploy/robots/go2w/main.cpp
deploy/robots/go2w/src/State_RLBase.cpp
deploy/robots/h1_2/CMakeLists.txt
deploy/robots/h1_2/config/config.yaml
deploy/robots/h1_2/config/policy/velocity/v0/params/deploy.yaml
deploy/robots/h1_2/include/Types.h
deploy/robots/h1_2/main.cpp
deploy/robots/h1_2/src/State_RLBase.cpp
deploy/thirdparty/cnpy/CMakeLists.txt
deploy/thirdparty/cnpy/LICENSE
deploy/thirdparty/cnpy/README.md
deploy/thirdparty/cnpy/cnpy.cpp
deploy/thirdparty/cnpy/cnpy.h
deploy/thirdparty/cnpy/example1.cpp
deploy/thirdparty/cnpy/mat2npz
deploy/thirdparty/cnpy/npy2mat
deploy/thirdparty/cnpy/npz2mat
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/GIT_COMMIT_ID
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/LICENSE
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/Privacy.md
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/README.md
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/ThirdPartyNotices.txt
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/VERSION_NUMBER
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/core/providers/custom_op_context.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/core/providers/resource.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/cpu_provider_factory.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_c_api.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_cxx_api.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_cxx_inline.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_float16.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_lite_custom_op.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_run_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/onnxruntime_session_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/include/provider_options.h
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfig.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfigVersion.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets-release.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets.cmake
deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/pkgconfig/libonnxruntime.pc
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/GIT_COMMIT_ID
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/LICENSE
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/Privacy.md
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/README.md
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/ThirdPartyNotices.txt
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/VERSION_NUMBER
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/core/providers/custom_op_context.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/core/providers/resource.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/cpu_provider_factory.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_c_api.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_cxx_api.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_cxx_inline.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_float16.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_lite_custom_op.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_run_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/onnxruntime_session_options_config_keys.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/include/provider_options.h
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfig.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeConfigVersion.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets-release.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/cmake/onnxruntime/onnxruntimeTargets.cmake
deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/pkgconfig/libonnxruntime.pc
doc/go2w_development.md
doc/license/cnpy-license
doc/license/mjlab-license
doc/license/onnxruntime-license
doc/setup.md
doc/step_field.md
mjlab/__init__.py
mjlab/actuator/__init__.py
mjlab/actuator/actuator.py
mjlab/actuator/builtin_actuator.py
mjlab/actuator/builtin_group.py
mjlab/actuator/dc_actuator.py
mjlab/actuator/delayed_actuator.py
mjlab/actuator/learned_actuator.py
mjlab/actuator/pd_actuator.py
mjlab/actuator/xml_actuator.py
mjlab/asset_zoo/__init__.py
mjlab/asset_zoo/robots/__init__.py
mjlab/asset_zoo/robots/unitree_g1/__init__.py
mjlab/asset_zoo/robots/unitree_g1/g1_23dof_constants.py
mjlab/asset_zoo/robots/unitree_g1/g1_constants.py
mjlab/asset_zoo/robots/unitree_g1/xmls/g1.xml
mjlab/asset_zoo/robots/unitree_g1/xmls/g1_23dof.xml
mjlab/asset_zoo/robots/unitree_go2/__init__.py
mjlab/asset_zoo/robots/unitree_go2/go2_constants.py
mjlab/asset_zoo/robots/unitree_go2/xmls/go2.xml
mjlab/asset_zoo/robots/unitree_go2w/__init__.py
mjlab/asset_zoo/robots/unitree_go2w/go2w_constants.py
mjlab/asset_zoo/robots/unitree_go2w/xmls/go2w.xml
mjlab/asset_zoo/robots/unitree_h1_2/__init__.py
mjlab/asset_zoo/robots/unitree_h1_2/h1_2_constants.py
mjlab/asset_zoo/robots/unitree_h1_2/xmls/h1_2.xml
mjlab/entity/__init__.py
mjlab/entity/data.py
mjlab/entity/entity.py
mjlab/envs/__init__.py
mjlab/envs/manager_based_rl_env.py
mjlab/envs/mdp/__init__.py
mjlab/envs/mdp/actions/__init__.py
mjlab/envs/mdp/actions/actions.py
mjlab/envs/mdp/events.py
mjlab/envs/mdp/observations.py
mjlab/envs/mdp/rewards.py
mjlab/envs/mdp/terminations.py
mjlab/envs/types.py
mjlab/managers/__init__.py
mjlab/managers/action_manager.py
mjlab/managers/command_manager.py
mjlab/managers/curriculum_manager.py
mjlab/managers/event_manager.py
mjlab/managers/manager_base.py
mjlab/managers/observation_manager.py
mjlab/managers/reward_manager.py
mjlab/managers/scene_entity_config.py
mjlab/managers/termination_manager.py
mjlab/motions/__init__.py
mjlab/motions/g1/dance1_subject2.csv
mjlab/rl/__init__.py
mjlab/rl/config.py
mjlab/rl/exporter_utils.py
mjlab/rl/vecenv_wrapper.py
mjlab/rsl_rl/__init__.py
mjlab/rsl_rl/algorithms/__init__.py
mjlab/rsl_rl/algorithms/distillation.py
mjlab/rsl_rl/algorithms/ppo.py
mjlab/rsl_rl/env/__init__.py
mjlab/rsl_rl/env/vec_env.py
mjlab/rsl_rl/modules/__init__.py
mjlab/rsl_rl/modules/actor_critic.py
mjlab/rsl_rl/modules/actor_critic_recurrent.py
mjlab/rsl_rl/modules/rnd.py
mjlab/rsl_rl/modules/student_teacher.py
mjlab/rsl_rl/modules/student_teacher_recurrent.py
mjlab/rsl_rl/modules/symmetry.py
mjlab/rsl_rl/networks/__init__.py
mjlab/rsl_rl/networks/memory.py
mjlab/rsl_rl/networks/mlp.py
mjlab/rsl_rl/networks/normalization.py
mjlab/rsl_rl/runners/__init__.py
mjlab/rsl_rl/runners/distillation_runner.py
mjlab/rsl_rl/runners/on_policy_runner.py
mjlab/rsl_rl/storage/__init__.py
mjlab/rsl_rl/storage/rollout_storage.py
mjlab/rsl_rl/utils/__init__.py
mjlab/rsl_rl/utils/exporter.py
mjlab/rsl_rl/utils/neptune_utils.py
mjlab/rsl_rl/utils/utils.py
mjlab/rsl_rl/utils/wandb_utils.py
mjlab/scene/__init__.py
mjlab/scene/scene.py
mjlab/scene/scene.xml
mjlab/sensor/__init__.py
mjlab/sensor/builtin_sensor.py
mjlab/sensor/contact_sensor.py
mjlab/sensor/raycast_sensor.py
mjlab/sensor/sensor.py
mjlab/sim/__init__.py
mjlab/sim/randomization.py
mjlab/sim/sim.py
mjlab/sim/sim_data.py
mjlab/tasks/__init__.py
mjlab/tasks/registry.py
mjlab/tasks/robots/__init__.py
mjlab/tasks/robots/unitree_g1/__init__.py
mjlab/tasks/robots/unitree_g1/tracking/__init__.py
mjlab/tasks/robots/unitree_g1/tracking/env_cfgs.py
mjlab/tasks/robots/unitree_g1/tracking/mdp/__init__.py
mjlab/tasks/robots/unitree_g1/tracking/mdp/commands.py
mjlab/tasks/robots/unitree_g1/tracking/mdp/metrics.py
mjlab/tasks/robots/unitree_g1/tracking/mdp/observations.py
mjlab/tasks/robots/unitree_g1/tracking/mdp/rewards.py
mjlab/tasks/robots/unitree_g1/tracking/mdp/terminations.py
mjlab/tasks/robots/unitree_g1/tracking/rl_cfg.py
mjlab/tasks/robots/unitree_g1/tracking/tracking_env_cfg.py
mjlab/tasks/robots/unitree_g1/velocity/__init__.py
mjlab/tasks/robots/unitree_g1/velocity/env_cfgs.py
mjlab/tasks/robots/unitree_g1/velocity/mdp/__init__.py
mjlab/tasks/robots/unitree_g1/velocity/mdp/curriculums.py
mjlab/tasks/robots/unitree_g1/velocity/mdp/observations.py
mjlab/tasks/robots/unitree_g1/velocity/mdp/rewards.py
mjlab/tasks/robots/unitree_g1/velocity/mdp/terminations.py
mjlab/tasks/robots/unitree_g1/velocity/mdp/velocity_command.py
mjlab/tasks/robots/unitree_g1/velocity/rl_cfg.py
mjlab/tasks/robots/unitree_g1/velocity/velocity_env_cfg.py
mjlab/tasks/robots/unitree_g1_23dof/__init__.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/__init__.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/env_cfgs.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/mdp/__init__.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/mdp/curriculums.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/mdp/observations.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/mdp/rewards.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/mdp/terminations.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/mdp/velocity_command.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/rl_cfg.py
mjlab/tasks/robots/unitree_g1_23dof/velocity/velocity_env_cfg.py
mjlab/tasks/robots/unitree_go2/__init__.py
mjlab/tasks/robots/unitree_go2/velocity/__init__.py
mjlab/tasks/robots/unitree_go2/velocity/env_cfgs.py
mjlab/tasks/robots/unitree_go2/velocity/mdp/__init__.py
mjlab/tasks/robots/unitree_go2/velocity/mdp/curriculums.py
mjlab/tasks/robots/unitree_go2/velocity/mdp/observations.py
mjlab/tasks/robots/unitree_go2/velocity/mdp/rewards.py
mjlab/tasks/robots/unitree_go2/velocity/mdp/terminations.py
mjlab/tasks/robots/unitree_go2/velocity/mdp/velocity_command.py
mjlab/tasks/robots/unitree_go2/velocity/rl_cfg.py
mjlab/tasks/robots/unitree_go2/velocity/velocity_env_cfg.py
mjlab/tasks/robots/unitree_go2w/__init__.py
mjlab/tasks/robots/unitree_go2w/velocity/__init__.py
mjlab/tasks/robots/unitree_go2w/velocity/base.py
mjlab/tasks/robots/unitree_go2w/velocity/env_cfgs.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/__init__.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/curriculums.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/feet_rewards.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/observations.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/posture_rewards.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/rewards.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/terminations.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/tracking_rewards.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/velocity_command.py
mjlab/tasks/robots/unitree_go2w/velocity/mdp/wheel_rewards.py
mjlab/tasks/robots/unitree_go2w/velocity/rl_cfg.py
mjlab/tasks/robots/unitree_go2w/velocity/velocity_env_cfg.py
mjlab/tasks/robots/unitree_h1_2/__init__.py
mjlab/tasks/robots/unitree_h1_2/velocity/__init__.py
mjlab/tasks/robots/unitree_h1_2/velocity/env_cfgs.py
mjlab/tasks/robots/unitree_h1_2/velocity/mdp/__init__.py
mjlab/tasks/robots/unitree_h1_2/velocity/mdp/curriculums.py
mjlab/tasks/robots/unitree_h1_2/velocity/mdp/observations.py
mjlab/tasks/robots/unitree_h1_2/velocity/mdp/rewards.py
mjlab/tasks/robots/unitree_h1_2/velocity/mdp/terminations.py
mjlab/tasks/robots/unitree_h1_2/velocity/mdp/velocity_command.py
mjlab/tasks/robots/unitree_h1_2/velocity/rl_cfg.py
mjlab/tasks/robots/unitree_h1_2/velocity/velocity_env_cfg.py
mjlab/tasks/tracking/__init__.py
mjlab/tasks/tracking/mdp/__init__.py
mjlab/tasks/tracking/mdp/commands.py
mjlab/tasks/tracking/mdp/metrics.py
mjlab/tasks/tracking/mdp/observations.py
mjlab/tasks/tracking/mdp/rewards.py
mjlab/tasks/tracking/mdp/terminations.py
mjlab/tasks/tracking/rl/__init__.py
mjlab/tasks/tracking/rl/exporter.py
mjlab/tasks/tracking/rl/runner.py
mjlab/tasks/tracking/scripts/evaluate.py
mjlab/tasks/velocity/__init__.py
mjlab/tasks/velocity/mdp/__init__.py
mjlab/tasks/velocity/mdp/curriculums.py
mjlab/tasks/velocity/mdp/observations.py
mjlab/tasks/velocity/mdp/rewards.py
mjlab/tasks/velocity/mdp/terminations.py
mjlab/tasks/velocity/mdp/velocity_command.py
mjlab/tasks/velocity/rl/__init__.py
mjlab/tasks/velocity/rl/exporter.py
mjlab/tasks/velocity/rl/runner.py
mjlab/terrains/README.md
mjlab/terrains/__init__.py
mjlab/terrains/config.py
mjlab/terrains/heightfield_terrains.py
mjlab/terrains/primitive_terrains.py
mjlab/terrains/terrain_generator.py
mjlab/terrains/terrain_importer.py
mjlab/terrains/utils.py
mjlab/utils/__init__.py
mjlab/utils/actuator.py
mjlab/utils/buffers/__init__.py
mjlab/utils/buffers/circular_buffer.py
mjlab/utils/buffers/delay_buffer.py
mjlab/utils/color.py
mjlab/utils/gpu.py
mjlab/utils/lab_api/__init__.py
mjlab/utils/lab_api/math.py
mjlab/utils/lab_api/rl/exporter.py
mjlab/utils/lab_api/string.py
mjlab/utils/lab_api/tasks/importer.py
mjlab/utils/logging.py
mjlab/utils/mujoco.py
mjlab/utils/nan_guard.py
mjlab/utils/noise/__init__.py
mjlab/utils/noise/noise_cfg.py
mjlab/utils/noise/noise_model.py
mjlab/utils/os.py
mjlab/utils/random.py
mjlab/utils/spaces.py
mjlab/utils/spec.py
mjlab/utils/spec_config.py
mjlab/utils/string.py
mjlab/utils/torch.py
mjlab/utils/wandb.py
mjlab/utils/wrappers/__init__.py
mjlab/utils/wrappers/video_recorder.py
mjlab/viewer/__init__.py
mjlab/viewer/base.py
mjlab/viewer/debug_visualizer.py
mjlab/viewer/native/__init__.py
mjlab/viewer/native/keys.py
mjlab/viewer/native/viewer.py
mjlab/viewer/native/visualizer.py
mjlab/viewer/offscreen_renderer.py
mjlab/viewer/viewer_config.py
mjlab/viewer/viser/__init__.py
mjlab/viewer/viser/conversions.py
mjlab/viewer/viser/reward_plotter.py
mjlab/viewer/viser/scene.py
mjlab/viewer/viser/viewer.py
scripts/_task_cli.py
scripts/csv_to_npz.py
scripts/demo.py
scripts/gcs.py
scripts/list_envs.py
scripts/nan_viz.py
scripts/play.py
scripts/train.py
setup.py
tests/test_go2w_core_helpers.py
tests/test_go2w_deploy_consistency.py
tests/test_go2w_smoke.py
tests/test_os_utils.py
tests/test_robot_task_imports.py
tests/test_robot_task_smoke.py
tests/test_runner_checkpoint_iteration.py
tests/test_task_cli.py
tests/test_task_registry.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib` | 4 | 17.0 MB | [`deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/_OMITTED.md`](./deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib/_OMITTED.md) |
| `deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib` | 2 | 20.1 MB | [`deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/_OMITTED.md`](./deploy/thirdparty/onnxruntime-linux-x64-1.22.0/lib/_OMITTED.md) |
| `doc/gif` | 8 | 38.7 MB | [`doc/gif/_OMITTED.md`](./doc/gif/_OMITTED.md) |
| `mjlab/asset_zoo/robots/unitree_g1/xmls/assets` | 38 | 32.9 MB | [`mjlab/asset_zoo/robots/unitree_g1/xmls/assets/_OMITTED.md`](./mjlab/asset_zoo/robots/unitree_g1/xmls/assets/_OMITTED.md) |
| `mjlab/asset_zoo/robots/unitree_go2/xmls/assets` | 16 | 27.8 MB | [`mjlab/asset_zoo/robots/unitree_go2/xmls/assets/_OMITTED.md`](./mjlab/asset_zoo/robots/unitree_go2/xmls/assets/_OMITTED.md) |
| `mjlab/asset_zoo/robots/unitree_go2w/xmls/assets` | 22 | 32.7 MB | [`mjlab/asset_zoo/robots/unitree_go2w/xmls/assets/_OMITTED.md`](./mjlab/asset_zoo/robots/unitree_go2w/xmls/assets/_OMITTED.md) |
| `mjlab/asset_zoo/robots/unitree_h1_2/xmls/assets` | 90 | 47.9 MB | [`mjlab/asset_zoo/robots/unitree_h1_2/xmls/assets/_OMITTED.md`](./mjlab/asset_zoo/robots/unitree_h1_2/xmls/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
