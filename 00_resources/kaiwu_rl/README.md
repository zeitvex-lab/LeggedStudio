# kaiwu_rl — 参考资源

> **来源**：`00_open/kaiwu_rl/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_g1（宇树 G1 人形）
> **定位**：开悟 RL 工程（Go2/G1）
> **收录**：284 个文件 / 28.3 MB（其中推理策略/模型文件 7 个）
> **已省略**：49 个文件 / 81.5 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（9 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（80 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（76 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（55 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（2 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（9 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（53 个）：文档、说明、许可与零散脚本

## 目录构成

```text
RoboGauge/  （134 个文件）
    (直接文件)/
    assets/
    resources/
    robogauge/
    scripts/
go2_rl_gym/  （87 个文件）
    (直接文件)/
    deploy/
    doc/
    legged_gym/
    resources/
    rsl_rl/
    tools/
unitree_cpp_deploy/  （63 个文件）
    (直接文件)/
    deploy/
    docs/
    resources/
    scripts/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 130 |
| `.xml` | 51 |
| `.h` | 30 |
| `.md` | 21 |
| `(无扩展名)` | 11 |
| `.cpp` | 9 |
| `.pt` | 7 |
| `.txt` | 7 |
| `.sh` | 6 |
| `.yaml` | 5 |
| `.urdf` | 2 |
| `.drawio` | 2 |
| `.hpp` | 2 |
| `.toml` | 1 |

## 文件索引（项目内相对路径）

```text
RoboGauge/.gitignore
RoboGauge/.python-version
RoboGauge/CMD.md
RoboGauge/LICENSE
RoboGauge/README.md
RoboGauge/README_zh.md
RoboGauge/UPDATE.md
RoboGauge/assets/docs/friction_margin.md
RoboGauge/assets/docs/mujoco_contact_version_analysis_zh.md
RoboGauge/assets/docs/zmp_margin.md
RoboGauge/assets/robogauge_basepipeline.drawio
RoboGauge/assets/robogauge_levelpipeline.drawio
RoboGauge/pyproject.toml
RoboGauge/resources/models/go2/go2_cts_max2_100k.pt
RoboGauge/resources/models/go2/go2_moe_cts_124k.pt
RoboGauge/resources/models/go2/go2_moe_cts_137k_0.6739.pt
RoboGauge/resources/models/go2/go2_moe_cts_8experts_2cmd_100k.pt
RoboGauge/resources/robots/go2/go2.xml
RoboGauge/resources/terrains/flat.xml
RoboGauge/resources/terrains/obstacle/obstacle_1.xml
RoboGauge/resources/terrains/obstacle/obstacle_10.xml
RoboGauge/resources/terrains/obstacle/obstacle_2.xml
RoboGauge/resources/terrains/obstacle/obstacle_3.xml
RoboGauge/resources/terrains/obstacle/obstacle_4.xml
RoboGauge/resources/terrains/obstacle/obstacle_5.xml
RoboGauge/resources/terrains/obstacle/obstacle_6.xml
RoboGauge/resources/terrains/obstacle/obstacle_7.xml
RoboGauge/resources/terrains/obstacle/obstacle_8.xml
RoboGauge/resources/terrains/obstacle/obstacle_9.xml
RoboGauge/resources/terrains/slope/slope_1.xml
RoboGauge/resources/terrains/slope/slope_10.xml
RoboGauge/resources/terrains/slope/slope_2.xml
RoboGauge/resources/terrains/slope/slope_3.xml
RoboGauge/resources/terrains/slope/slope_4.xml
RoboGauge/resources/terrains/slope/slope_5.xml
RoboGauge/resources/terrains/slope/slope_6.xml
RoboGauge/resources/terrains/slope/slope_7.xml
RoboGauge/resources/terrains/slope/slope_8.xml
RoboGauge/resources/terrains/slope/slope_9.xml
RoboGauge/resources/terrains/slope_5.xml
RoboGauge/resources/terrains/slope_5_old.xml
RoboGauge/resources/terrains/stairs/stairs_1.xml
RoboGauge/resources/terrains/stairs/stairs_10.xml
RoboGauge/resources/terrains/stairs/stairs_2.xml
RoboGauge/resources/terrains/stairs/stairs_3.xml
RoboGauge/resources/terrains/stairs/stairs_4.xml
RoboGauge/resources/terrains/stairs/stairs_5.xml
RoboGauge/resources/terrains/stairs/stairs_6.xml
RoboGauge/resources/terrains/stairs/stairs_7.xml
RoboGauge/resources/terrains/stairs/stairs_8.xml
RoboGauge/resources/terrains/stairs/stairs_9.xml
RoboGauge/resources/terrains/wall/10x10_wall.xml
RoboGauge/resources/terrains/wave/wave_1.xml
RoboGauge/resources/terrains/wave/wave_10.xml
RoboGauge/resources/terrains/wave/wave_2.xml
RoboGauge/resources/terrains/wave/wave_3.xml
RoboGauge/resources/terrains/wave/wave_4.xml
RoboGauge/resources/terrains/wave/wave_5.xml
RoboGauge/resources/terrains/wave/wave_6.xml
RoboGauge/resources/terrains/wave/wave_7.xml
RoboGauge/resources/terrains/wave/wave_8.xml
RoboGauge/resources/terrains/wave/wave_9.xml
RoboGauge/robogauge.sh
RoboGauge/robogauge/__init__.py
RoboGauge/robogauge/scripts/client.py
RoboGauge/robogauge/scripts/evaluate_models.txt
RoboGauge/robogauge/scripts/run.py
RoboGauge/robogauge/scripts/run_eval_models.sh
RoboGauge/robogauge/scripts/server.py
RoboGauge/robogauge/scripts/status.py
RoboGauge/robogauge/tasks/__init__.py
RoboGauge/robogauge/tasks/custom/go2/__init__.py
RoboGauge/robogauge/tasks/custom/go2/go2_flat_task.py
RoboGauge/robogauge/tasks/custom/go2/go2_obstacle_task.py
RoboGauge/robogauge/tasks/custom/go2/go2_slope_task.py
RoboGauge/robogauge/tasks/custom/go2/go2_stairs_task.py
RoboGauge/robogauge/tasks/custom/go2/go2_wave_task.py
RoboGauge/robogauge/tasks/gauge/__init__.py
RoboGauge/robogauge/tasks/gauge/base_gauge.py
RoboGauge/robogauge/tasks/gauge/base_gauge_config.py
RoboGauge/robogauge/tasks/gauge/gauge_configs/flat_gauge_config.py
RoboGauge/robogauge/tasks/gauge/gauge_configs/obstacle_gauge_config.py
RoboGauge/robogauge/tasks/gauge/gauge_configs/slope_gauge_config.py
RoboGauge/robogauge/tasks/gauge/gauge_configs/stairs_gauge_config.py
RoboGauge/robogauge/tasks/gauge/gauge_configs/terrain_levels_config.py
RoboGauge/robogauge/tasks/gauge/gauge_configs/wave_gauge_config.py
RoboGauge/robogauge/tasks/gauge/goal_data.py
RoboGauge/robogauge/tasks/gauge/goals/__init__.py
RoboGauge/robogauge/tasks/gauge/goals/base_goal.py
RoboGauge/robogauge/tasks/gauge/goals/joystick_goal.py
RoboGauge/robogauge/tasks/gauge/goals/velocity_goals.py
RoboGauge/robogauge/tasks/gauge/metrics/__init__.py
RoboGauge/robogauge/tasks/gauge/metrics/base_metric.py
RoboGauge/robogauge/tasks/gauge/metrics/dof_metrics.py
RoboGauge/robogauge/tasks/gauge/metrics/stable_metric.py
RoboGauge/robogauge/tasks/gauge/metrics/vel_metrics.py
RoboGauge/robogauge/tasks/gauge/metrics/visualization.py
RoboGauge/robogauge/tasks/pipeline/__init__.py
RoboGauge/robogauge/tasks/pipeline/base_pipeline.py
RoboGauge/robogauge/tasks/pipeline/level_pipeline.py
RoboGauge/robogauge/tasks/pipeline/multi_pipeline.py
RoboGauge/robogauge/tasks/pipeline/stress_pipeline.py
RoboGauge/robogauge/tasks/robots/__init__.py
RoboGauge/robogauge/tasks/robots/base_robot.py
RoboGauge/robogauge/tasks/robots/base_robot_config.py
RoboGauge/robogauge/tasks/robots/go2/go2.py
RoboGauge/robogauge/tasks/robots/go2/go2_config.py
RoboGauge/robogauge/tasks/robots/go2/go2_lab_config.py
RoboGauge/robogauge/tasks/robots/go2/go2_moe.py
RoboGauge/robogauge/tasks/robots/go2/go2_moe_config.py
RoboGauge/robogauge/tasks/simulator/__init__.py
RoboGauge/robogauge/tasks/simulator/mujoco_config.py
RoboGauge/robogauge/tasks/simulator/mujoco_simulator.py
RoboGauge/robogauge/tasks/simulator/sim_data.py
RoboGauge/robogauge/utils/config.py
RoboGauge/robogauge/utils/file_utils.py
RoboGauge/robogauge/utils/helpers.py
RoboGauge/robogauge/utils/logger.py
RoboGauge/robogauge/utils/math_utils.py
RoboGauge/robogauge/utils/measure.py
RoboGauge/robogauge/utils/process_utils.py
RoboGauge/robogauge/utils/progress_monitor.py
RoboGauge/robogauge/utils/task_register.py
RoboGauge/robogauge/utils/visualize/plot_latent_pca_cmd.py
RoboGauge/robogauge/utils/visualize/plot_latent_pca_terrain.py
RoboGauge/robogauge/utils/visualize/plot_latent_tsne.py
RoboGauge/robogauge/utils/visualize/plot_radar_and_bar.py
RoboGauge/robogauge/utils/visualize/plot_terrain_levels.py
RoboGauge/scripts/eval_jit_models_to_tensorboard.py
RoboGauge/scripts/run.sh
RoboGauge/scripts/run_models.sh
RoboGauge/scripts/run_save_latent.sh
RoboGauge/scripts/run_save_video.sh
RoboGauge/setup.py
go2_rl_gym/.gitignore
go2_rl_gym/LICENSE
go2_rl_gym/README.md
go2_rl_gym/README_zh.md
go2_rl_gym/UPDATE.md
go2_rl_gym/cmd.md
go2_rl_gym/deploy/deploy_mujoco/configs/go2.yaml
go2_rl_gym/deploy/deploy_mujoco/deploy_go2.py
go2_rl_gym/deploy/deploy_mujoco/utils.py
go2_rl_gym/deploy/deploy_real/common/command_helper.py
go2_rl_gym/deploy/deploy_real/common/remote_controller.py
go2_rl_gym/deploy/deploy_real/common/rotation_helper.py
go2_rl_gym/deploy/deploy_real/config_go2.py
go2_rl_gym/deploy/deploy_real/configs/go2.yaml
go2_rl_gym/deploy/deploy_real/deploy_real_go2.py
go2_rl_gym/deploy/pre_train/go2/go2_cts_150k.pt
go2_rl_gym/deploy/pre_train/go2/go2_moe_cts_137k_0.6739.pt
go2_rl_gym/deploy/pre_train/go2/go2_moe_cts_high_slope_thre_164k_0.6715.pt
go2_rl_gym/doc/setup_en.md
go2_rl_gym/doc/setup_zh.md
go2_rl_gym/legged_gym/LICENSE
go2_rl_gym/legged_gym/__init__.py
go2_rl_gym/legged_gym/envs/__init__.py
go2_rl_gym/legged_gym/envs/base/base_config.py
go2_rl_gym/legged_gym/envs/base/base_task.py
go2_rl_gym/legged_gym/envs/base/legged_robot.py
go2_rl_gym/legged_gym/envs/base/legged_robot_config.py
go2_rl_gym/legged_gym/envs/go2/go2_config.py
go2_rl_gym/legged_gym/envs/go2/go2_config_fast_flat_move.py
go2_rl_gym/legged_gym/envs/go2/go2_config_vanilla.py
go2_rl_gym/legged_gym/envs/go2/go2_config_vanilla_with_dynamic_cmd.py
go2_rl_gym/legged_gym/envs/go2/go2_env.py
go2_rl_gym/legged_gym/scripts/play.py
go2_rl_gym/legged_gym/scripts/train.py
go2_rl_gym/legged_gym/utils/__init__.py
go2_rl_gym/legged_gym/utils/exporter.py
go2_rl_gym/legged_gym/utils/helpers.py
go2_rl_gym/legged_gym/utils/isaacgym_utils.py
go2_rl_gym/legged_gym/utils/logger.py
go2_rl_gym/legged_gym/utils/math.py
go2_rl_gym/legged_gym/utils/task_registry.py
go2_rl_gym/legged_gym/utils/terrain.py
go2_rl_gym/resources/robots/go2/cross_slope.xml
go2_rl_gym/resources/robots/go2/cross_stairs.xml
go2_rl_gym/resources/robots/go2/flat.xml
go2_rl_gym/resources/robots/go2/go2.xml
go2_rl_gym/resources/robots/go2/race_track.xml
go2_rl_gym/resources/robots/go2/stairs.xml
go2_rl_gym/resources/robots/go2/urdf/go2.urdf
go2_rl_gym/rsl_rl/.gitignore
go2_rl_gym/rsl_rl/LICENSE
go2_rl_gym/rsl_rl/README.md
go2_rl_gym/rsl_rl/licenses/dependencies/numpy_license.txt
go2_rl_gym/rsl_rl/licenses/dependencies/torch_license.txt
go2_rl_gym/rsl_rl/rsl_rl/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/ac_moe_cts.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/cts.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/dual_moe_cts.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/mcp_cts.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/moe_cts.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/moe_ng_cts.py
go2_rl_gym/rsl_rl/rsl_rl/algorithms/ppo.py
go2_rl_gym/rsl_rl/rsl_rl/env/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/env/vec_env.py
go2_rl_gym/rsl_rl/rsl_rl/modules/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_ac_moe_cts.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_cts.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_dual_moe_cts.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_mcp_cts.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_moe_cts.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_moe_ng_cts.py
go2_rl_gym/rsl_rl/rsl_rl/modules/actor_critic_recurrent.py
go2_rl_gym/rsl_rl/rsl_rl/modules/utils.py
go2_rl_gym/rsl_rl/rsl_rl/runners/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/runners/on_policy_runner.py
go2_rl_gym/rsl_rl/rsl_rl/runners/on_policy_runner_cts.py
go2_rl_gym/rsl_rl/rsl_rl/storage/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/storage/rollout_storage.py
go2_rl_gym/rsl_rl/rsl_rl/storage/rollout_storage_cts.py
go2_rl_gym/rsl_rl/rsl_rl/utils/__init__.py
go2_rl_gym/rsl_rl/rsl_rl/utils/utils.py
go2_rl_gym/rsl_rl/setup.py
go2_rl_gym/setup.py
go2_rl_gym/tools/logs_compress.py
go2_rl_gym/tools/logs_merge.py
unitree_cpp_deploy/.gitignore
unitree_cpp_deploy/LICENSE
unitree_cpp_deploy/README.md
unitree_cpp_deploy/README_zh.md
unitree_cpp_deploy/UPDATE.md
unitree_cpp_deploy/deploy/include/DataLogger.h
unitree_cpp_deploy/deploy/include/FSM/BaseState.h
unitree_cpp_deploy/deploy/include/FSM/CtrlFSM.h
unitree_cpp_deploy/deploy/include/FSM/FSMState.h
unitree_cpp_deploy/deploy/include/FSM/State_Fix.h
unitree_cpp_deploy/deploy/include/FSM/State_Passive.h
unitree_cpp_deploy/deploy/include/FSM/State_RLBase.h
unitree_cpp_deploy/deploy/include/LinearInterpolator.h
unitree_cpp_deploy/deploy/include/UdpSocket.h
unitree_cpp_deploy/deploy/include/isaaclab/algorithms/algorithms.h
unitree_cpp_deploy/deploy/include/isaaclab/assets/articulation/articulation.h
unitree_cpp_deploy/deploy/include/isaaclab/devices/keyboard/keyboard.h
unitree_cpp_deploy/deploy/include/isaaclab/envs/manager_based_rl_env.h
unitree_cpp_deploy/deploy/include/isaaclab/envs/mdp/actions/joint_actions.h
unitree_cpp_deploy/deploy/include/isaaclab/envs/mdp/commands/motion_command.h
unitree_cpp_deploy/deploy/include/isaaclab/envs/mdp/observations/motion_observations.h
unitree_cpp_deploy/deploy/include/isaaclab/envs/mdp/observations/observations.h
unitree_cpp_deploy/deploy/include/isaaclab/envs/mdp/terminations.h
unitree_cpp_deploy/deploy/include/isaaclab/manager/action_manager.h
unitree_cpp_deploy/deploy/include/isaaclab/manager/manager_term_cfg.h
unitree_cpp_deploy/deploy/include/isaaclab/manager/observation_manager.h
unitree_cpp_deploy/deploy/include/param.h
unitree_cpp_deploy/deploy/include/unitree_articulation.h
unitree_cpp_deploy/deploy/include/unitree_joystick_dsl.hpp
unitree_cpp_deploy/deploy/include/utils/VelocityCommandDamper.h
unitree_cpp_deploy/deploy/robots/g1/CMakeLists.txt
unitree_cpp_deploy/deploy/robots/g1/config/config.yaml
unitree_cpp_deploy/deploy/robots/g1/config/config_bfm.yaml
unitree_cpp_deploy/deploy/robots/g1/include/State_BFM.h
unitree_cpp_deploy/deploy/robots/g1/include/State_Mimic.h
unitree_cpp_deploy/deploy/robots/g1/include/State_OmniXtreme.h
unitree_cpp_deploy/deploy/robots/g1/include/Types.h
unitree_cpp_deploy/deploy/robots/g1/main.cpp
unitree_cpp_deploy/deploy/robots/g1/src/State_BFM.cpp
unitree_cpp_deploy/deploy/robots/g1/src/State_Mimic.cpp
unitree_cpp_deploy/deploy/robots/g1/src/State_OmniXtreme.cpp
unitree_cpp_deploy/deploy/robots/g1/src/State_RLBase.cpp
unitree_cpp_deploy/deploy/robots/go2/CMakeLists.txt
unitree_cpp_deploy/deploy/robots/go2/config/config.yaml
unitree_cpp_deploy/deploy/robots/go2/include/Types.h
unitree_cpp_deploy/deploy/robots/go2/main.cpp
unitree_cpp_deploy/deploy/robots/go2/src/State_RLBase.cpp
unitree_cpp_deploy/deploy/thirdparty/cnpy/CMakeLists.txt
unitree_cpp_deploy/deploy/thirdparty/cnpy/LICENSE
unitree_cpp_deploy/deploy/thirdparty/cnpy/README.md
unitree_cpp_deploy/deploy/thirdparty/cnpy/cnpy.cpp
unitree_cpp_deploy/deploy/thirdparty/cnpy/cnpy.h
unitree_cpp_deploy/deploy/thirdparty/cnpy/example1.cpp
unitree_cpp_deploy/deploy/thirdparty/nlohmann/json.hpp
unitree_cpp_deploy/deploy/tools/video/extract_frames_from_video.py
unitree_cpp_deploy/deploy/tools/visualize_logs.py
unitree_cpp_deploy/deploy/tools/visualize_position.py
unitree_cpp_deploy/docs/g1_setup_zh.md
unitree_cpp_deploy/docs/licenses/unitree-rl-lab-license.txt
unitree_cpp_deploy/docs/obs_group.md
unitree_cpp_deploy/docs/robot_params.md
unitree_cpp_deploy/resources/go2.urdf
unitree_cpp_deploy/scripts/udp_test.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `RoboGauge/assets` | 3 | 254 KB | [`RoboGauge/assets/_OMITTED.md`](./RoboGauge/assets/_OMITTED.md) |
| `RoboGauge/resources/robots/go2/assets` | 16 | 27.8 MB | [`RoboGauge/resources/robots/go2/assets/_OMITTED.md`](./RoboGauge/resources/robots/go2/assets/_OMITTED.md) |
| `RoboGauge/resources/terrains/wave` | 1 | 26 KB | [`RoboGauge/resources/terrains/wave/_OMITTED.md`](./RoboGauge/resources/terrains/wave/_OMITTED.md) |
| `go2_rl_gym/resources/robots/go2/assets` | 18 | 28.7 MB | [`go2_rl_gym/resources/robots/go2/assets/_OMITTED.md`](./go2_rl_gym/resources/robots/go2/assets/_OMITTED.md) |
| `go2_rl_gym/resources/robots/go2/dae` | 7 | 24.7 MB | [`go2_rl_gym/resources/robots/go2/dae/_OMITTED.md`](./go2_rl_gym/resources/robots/go2/dae/_OMITTED.md) |
| `go2_rl_gym/resources/robots/go2/imgs` | 4 | 9 KB | [`go2_rl_gym/resources/robots/go2/imgs/_OMITTED.md`](./go2_rl_gym/resources/robots/go2/imgs/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
