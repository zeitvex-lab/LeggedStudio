# engineai_rl_workspace — 参考资源

> **来源**：`00_open/engineai_rl_workspace/`　｜　**类型**：人形/四足 RL 训练·评测框架参考（legged_gym 系）
> **关联机型**：（无，通用）
> **定位**：EngineAI RL Workspace（深圳众擎机器人；GitHub 上可访问的快照为 MeredithRowe/engineai_rl_workspace 的 community 分支，上游 engineai-robotics/engineai_rl_workspace 已不可公开访问）：通用腿足 RL 框架（engineai_gym 环境 / engineai_rl 算法·网络·runner / engineai_rl_workspace 实验与脚本 / engineai_rl_lib 参考状态），训练与播放共用一套 runner 逻辑、run 记录与代码快照可复现、.pt→.onnx/.mnn 格式转换；含 PM01/SA01 双足与 quadruped 资产、actuator_nets 执行器网络
> **收录**：197 个文件 / 1.4 MB（其中推理策略/模型文件 1 个）
> **已省略**：92 个文件 / 111.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（14 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（101 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（1 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（17 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（62 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （7 个文件）
docs/  （5 个文件）
    licenses/
engineai_gym/  （105 个文件）
    (直接文件)/
    engineai_gym/
engineai_rl/  （39 个文件）
    (直接文件)/
    engineai_rl/
engineai_rl_lib/  （22 个文件）
    (直接文件)/
    engineai_rl_lib/
engineai_rl_workspace/  （19 个文件）
    (直接文件)/
    engineai_rl_workspace/
    exps/
    scripts/
    utils/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 158 |
| `.json` | 13 |
| `.urdf` | 8 |
| `(无扩展名)` | 6 |
| `.txt` | 5 |
| `.yaml` | 3 |
| `.md` | 1 |
| `.toml` | 1 |
| `.pt` | 1 |
| `.xml` | 1 |

## 文件索引（项目内相对路径）

```text
.flake8
.gitignore
.pre-commit-config.yaml
LICENSE
README.md
docs/licenses/assets/ANYmal_b_license.txt
docs/licenses/assets/ANYmal_c_license.txt
docs/licenses/assets/a1_license.txt
docs/licenses/assets/pm01_license.txt
docs/licenses/assets/sa01_license.txt
engineai_gym/.gitattributes
engineai_gym/.gitignore
engineai_gym/engineai_gym/__init__.py
engineai_gym/engineai_gym/envs/__init__.py
engineai_gym/engineai_gym/envs/base/config_legged_robot.py
engineai_gym/engineai_gym/envs/base/config_legged_robot_ref.py
engineai_gym/engineai_gym/envs/base/domain_rands/__init__.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_base.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_type_action_lag.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_type_disturbance.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_type_dof.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_type_obs_lag.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_type_rigid_body.py
engineai_gym/engineai_gym/envs/base/domain_rands/domain_rands_type_rigid_shape.py
engineai_gym/engineai_gym/envs/base/env_base.py
engineai_gym/engineai_gym/envs/base/goals/goals.py
engineai_gym/engineai_gym/envs/base/legged_robot.py
engineai_gym/engineai_gym/envs/base/legged_robot_ref.py
engineai_gym/engineai_gym/envs/base/obs/obs.py
engineai_gym/engineai_gym/envs/base/rewards/rewards.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_base.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_action.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_base_pos_ori.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_base_vel.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_collision.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_contact.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_dof.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_gait.py
engineai_gym/engineai_gym/envs/base/rewards/rewards_type_termination.py
engineai_gym/engineai_gym/envs/robots/biped/biped_robot.py
engineai_gym/engineai_gym/envs/robots/biped/config_biped_robot.py
engineai_gym/engineai_gym/envs/robots/biped/goals_biped.py
engineai_gym/engineai_gym/envs/robots/biped/pm01/flat/config_pm01_flat.py
engineai_gym/engineai_gym/envs/robots/biped/pm01/obs_pm01.py
engineai_gym/engineai_gym/envs/robots/biped/pm01/pm01.py
engineai_gym/engineai_gym/envs/robots/biped/pm01/rough/config_pm01_rough.py
engineai_gym/engineai_gym/envs/robots/biped/rewards_biped.py
engineai_gym/engineai_gym/envs/robots/biped/sa01/config_sa01_rough.py
engineai_gym/engineai_gym/envs/robots/biped/sa01/sa01.py
engineai_gym/engineai_gym/envs/robots/quadruped/a1/flat/config_a1_flat.py
engineai_gym/engineai_gym/envs/robots/quadruped/a1/flat/config_a1_flat_ref_state.py
engineai_gym/engineai_gym/envs/robots/quadruped/a1/rough/config_a1_rough.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_b/config_anymal_b_rough.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/anymal.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/domain_rands_anymal_c.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/domain_rands_type_dof_anymal_c.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/flat/config_anymal_c_flat.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/obs_anymal_c.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/rewards_anymal_c.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/rough/config_anymal_c_rough.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/rough/rewards_anymal_c_rough.py
engineai_gym/engineai_gym/envs/robots/quadruped/anymal_c/rough/tester_config.yaml
engineai_gym/engineai_gym/resources/actuator_nets/anydrive_v3_lstm.pt
engineai_gym/engineai_gym/resources/robots/biped/pm01/urdf/pm01.urdf
engineai_gym/engineai_gym/resources/robots/biped/pm01/urdf/pm01_only_legs.urdf
engineai_gym/engineai_gym/resources/robots/biped/pm01/urdf/pm01_only_legs_simple_collision.urdf
engineai_gym/engineai_gym/resources/robots/biped/pm01/urdf/pm01_simple_collision.urdf
engineai_gym/engineai_gym/resources/robots/biped/sa01/urdf/sa01.urdf
engineai_gym/engineai_gym/resources/robots/biped/sa01/urdf/sa01.xml
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/canter0.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/canter1.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/canter2.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/data.py
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/left_turn0.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/left_turn1.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/pace0.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/pace1.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/pace2.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/right_turn0.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/right_turn1.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/trot0.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/trot1.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/mocap_motions/trot2.json
engineai_gym/engineai_gym/resources/robots/quadruped/a1/urdf/a1.urdf
engineai_gym/engineai_gym/resources/robots/quadruped/anymal_b/urdf/anymal_b.urdf
engineai_gym/engineai_gym/resources/robots/quadruped/anymal_c/urdf/anymal_c.urdf
engineai_gym/engineai_gym/tester/__init__.py
engineai_gym/engineai_gym/tester/loggers/__init__.py
engineai_gym/engineai_gym/tester/loggers/logger_base.py
engineai_gym/engineai_gym/tester/loggers/logger_type_base_vel.py
engineai_gym/engineai_gym/tester/loggers/logger_type_force.py
engineai_gym/engineai_gym/tester/loggers/logger_type_position.py
engineai_gym/engineai_gym/tester/loggers/logger_type_torque.py
engineai_gym/engineai_gym/tester/loggers/logger_type_vel.py
engineai_gym/engineai_gym/tester/tester.py
engineai_gym/engineai_gym/tester/tester_config.yaml
engineai_gym/engineai_gym/tester/tester_config_base.py
engineai_gym/engineai_gym/tester/testers/__init__.py
engineai_gym/engineai_gym/tester/testers/tester_backward_commands.py
engineai_gym/engineai_gym/tester/testers/tester_base.py
engineai_gym/engineai_gym/tester/testers/tester_forward_commands.py
engineai_gym/engineai_gym/tester/testers/tester_normal_commands.py
engineai_gym/engineai_gym/tester/testers/tester_x_commands.py
engineai_gym/engineai_gym/tester/testers/tester_y_commands.py
engineai_gym/engineai_gym/tester/testers/tester_yaw_commands.py
engineai_gym/engineai_gym/tester/testers/tester_zero_commands.py
engineai_gym/engineai_gym/utils/__init__.py
engineai_gym/engineai_gym/utils/math.py
engineai_gym/engineai_gym/utils/terrain.py
engineai_gym/engineai_gym/utils/torch_utils.py
engineai_gym/engineai_gym/wrapper/__init__.py
engineai_gym/engineai_gym/wrapper/record_video_wrapper.py
engineai_gym/engineai_gym/wrapper/vec_gym_wrapper.py
engineai_gym/setup.py
engineai_rl/.gitignore
engineai_rl/engineai_rl/__init__.py
engineai_rl/engineai_rl/algos/__init__.py
engineai_rl/engineai_rl/algos/base/__init__.py
engineai_rl/engineai_rl/algos/base/algo_base.py
engineai_rl/engineai_rl/algos/base/base_algo_config.py
engineai_rl/engineai_rl/algos/ppo/__init__.py
engineai_rl/engineai_rl/algos/ppo/config_ppo.py
engineai_rl/engineai_rl/algos/ppo/ppo.py
engineai_rl/engineai_rl/algos/ppo/ppo_amp/amp_discriminator.py
engineai_rl/engineai_rl/algos/ppo/ppo_amp/config_ppo_amp.py
engineai_rl/engineai_rl/algos/ppo/ppo_amp/ppo_amp.py
engineai_rl/engineai_rl/exps/biped/pm01/config_pm01_ppo.py
engineai_rl/engineai_rl/exps/biped/sa01/config_sa01_ppo.py
engineai_rl/engineai_rl/exps/quadruped/a1/config_a1_ppo.py
engineai_rl/engineai_rl/exps/quadruped/a1/config_a1_ppo_amp.py
engineai_rl/engineai_rl/exps/quadruped/anymal_b/config_anymal_b_ppo.py
engineai_rl/engineai_rl/exps/quadruped/anymal_c/flat/config_anymal_c_flat_ppo.py
engineai_rl/engineai_rl/exps/quadruped/anymal_c/rough/config_anymal_c_rough_ppo.py
engineai_rl/engineai_rl/modules/__init__.py
engineai_rl/engineai_rl/modules/actor_critic.py
engineai_rl/engineai_rl/modules/networks/__init__.py
engineai_rl/engineai_rl/modules/networks/mlp.py
engineai_rl/engineai_rl/modules/networks/network_base.py
engineai_rl/engineai_rl/modules/normalizers/__init__.py
engineai_rl/engineai_rl/modules/normalizers/normalizer_amp.py
engineai_rl/engineai_rl/modules/normalizers/normalizer_empirical.py
engineai_rl/engineai_rl/runners/__init__.py
engineai_rl/engineai_rl/runners/on_policy_runner.py
engineai_rl/engineai_rl/runners/runner_base.py
engineai_rl/engineai_rl/storage/__init__.py
engineai_rl/engineai_rl/storage/replay_buffer.py
engineai_rl/engineai_rl/storage/rollout_storage.py
engineai_rl/engineai_rl/utils/__init__.py
engineai_rl/engineai_rl/utils/neptune_utils.py
engineai_rl/engineai_rl/utils/utils.py
engineai_rl/engineai_rl/utils/wandb_utils.py
engineai_rl/engineai_rl/wrapper/input_retrival_env_wrapper.py
engineai_rl/setup.py
engineai_rl_lib/engineai_rl_lib/__init__.py
engineai_rl_lib/engineai_rl_lib/base_config.py
engineai_rl_lib/engineai_rl_lib/class_operations.py
engineai_rl_lib/engineai_rl_lib/colored_log.py
engineai_rl_lib/engineai_rl_lib/command_filter.py
engineai_rl_lib/engineai_rl_lib/convert_mocap_files_from_csv2json.py
engineai_rl_lib/engineai_rl_lib/device.py
engineai_rl_lib/engineai_rl_lib/dict_operations.py
engineai_rl_lib/engineai_rl_lib/files_and_dirs.py
engineai_rl_lib/engineai_rl_lib/git.py
engineai_rl_lib/engineai_rl_lib/json.py
engineai_rl_lib/engineai_rl_lib/math.py
engineai_rl_lib/engineai_rl_lib/redis_lock.py
engineai_rl_lib/engineai_rl_lib/ref_state/__init__.py
engineai_rl_lib/engineai_rl_lib/ref_state/data_base.py
engineai_rl_lib/engineai_rl_lib/ref_state/pose3d.py
engineai_rl_lib/engineai_rl_lib/ref_state/ref_state_loader.py
engineai_rl_lib/engineai_rl_lib/ref_state/ref_state_util.py
engineai_rl_lib/engineai_rl_lib/text.py
engineai_rl_lib/engineai_rl_lib/trajectory.py
engineai_rl_lib/engineai_rl_lib/type.py
engineai_rl_lib/setup.py
engineai_rl_workspace/__init__.py
engineai_rl_workspace/engineai_rl_workspace/__init__.py
engineai_rl_workspace/exps/__init__.py
engineai_rl_workspace/exps/biped/pm01.py
engineai_rl_workspace/exps/biped/sa01.py
engineai_rl_workspace/exps/quadruped/a1.py
engineai_rl_workspace/exps/quadruped/anymal_b.py
engineai_rl_workspace/exps/quadruped/anymal_c.py
engineai_rl_workspace/scripts/export_policy.py
engineai_rl_workspace/scripts/play.py
engineai_rl_workspace/scripts/run_plays_export_policies.py
engineai_rl_workspace/scripts/train.py
engineai_rl_workspace/utils/__init__.py
engineai_rl_workspace/utils/convert_between_py_and_dict.py
engineai_rl_workspace/utils/convert_policy.py
engineai_rl_workspace/utils/exp_registry.py
engineai_rl_workspace/utils/helpers.py
engineai_rl_workspace/utils/process_resume_files.py
engineai_rl_workspace/utils/tester_registry.py
pyproject.toml
setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs` | 2 | 605 KB | [`docs/_OMITTED.md`](./docs/_OMITTED.md) |
| `engineai_gym/engineai_gym/resources/robots/biped/pm01/meshes` | 25 | 64.1 MB | [`engineai_gym/engineai_gym/resources/robots/biped/pm01/meshes/_OMITTED.md`](./engineai_gym/engineai_gym/resources/robots/biped/pm01/meshes/_OMITTED.md) |
| `engineai_gym/engineai_gym/resources/robots/biped/sa01/meshes` | 13 | 8.7 MB | [`engineai_gym/engineai_gym/resources/robots/biped/sa01/meshes/_OMITTED.md`](./engineai_gym/engineai_gym/resources/robots/biped/sa01/meshes/_OMITTED.md) |
| `engineai_gym/engineai_gym/resources/robots/quadruped/a1/meshes` | 6 | 8.7 MB | [`engineai_gym/engineai_gym/resources/robots/quadruped/a1/meshes/_OMITTED.md`](./engineai_gym/engineai_gym/resources/robots/quadruped/a1/meshes/_OMITTED.md) |
| `engineai_gym/engineai_gym/resources/robots/quadruped/anymal_b/meshes` | 10 | 21.0 MB | [`engineai_gym/engineai_gym/resources/robots/quadruped/anymal_b/meshes/_OMITTED.md`](./engineai_gym/engineai_gym/resources/robots/quadruped/anymal_b/meshes/_OMITTED.md) |
| `engineai_gym/engineai_gym/resources/robots/quadruped/anymal_c/meshes` | 36 | 7.9 MB | [`engineai_gym/engineai_gym/resources/robots/quadruped/anymal_c/meshes/_OMITTED.md`](./engineai_gym/engineai_gym/resources/robots/quadruped/anymal_c/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
