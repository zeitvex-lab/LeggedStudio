# walk-these-ways — 参考资源

> **来源**：`00_open/walk-these-ways/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）
> **定位**：Improbable AI walk-these-ways：Go1 快速步态 RL 训练与部署（go1_gym / go1_gym_deploy）
> **收录**：103 个文件 / 35.1 MB（其中推理策略/模型文件 4 个）
> **已省略**：28 个文件 / 65.5 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（5 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（15 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（42 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（1 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（4 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（6 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（30 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
LICENSES/  （2 个文件）
    legged_gym/
    rsl_rl/
go1_gym/  （15 个文件）
    (直接文件)/
    envs/
    utils/
go1_gym_deploy/  （38 个文件）
    (直接文件)/
    autostart/
    docker/
    envs/
    installer/
    lcm_types/
    scripts/
    tests/
    unitree_legged_sdk_bin/
    utils/
go1_gym_learn/  （18 个文件）
    (直接文件)/
    env/
    eval_metrics/
    ppo/
    ppo_cse/
    utils/
resources/  （11 个文件）
    actuator_nets/
    objects/
    robots/
runs/  （7 个文件）
    gait-conditioned-agility/
scripts/  （8 个文件）
    (直接文件)/
    actuator_net/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 65 |
| `(无扩展名)` | 7 |
| `.sh` | 7 |
| `.meta` | 5 |
| `.lcm` | 4 |
| `.urdf` | 4 |
| `.pkl` | 3 |
| `.pt` | 2 |
| `.jit` | 2 |
| `.md` | 1 |
| `.cpp` | 1 |
| `.xml` | 1 |
| `.yml` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
LICENSE
LICENSES/legged_gym/LICENSE
LICENSES/rsl_rl/LICENSE
README.md
go1_gym/__init__.py
go1_gym/envs/__init__.py
go1_gym/envs/base/__init__.py
go1_gym/envs/base/base_task.py
go1_gym/envs/base/curriculum.py
go1_gym/envs/base/legged_robot.py
go1_gym/envs/base/legged_robot_config.py
go1_gym/envs/go1/__init__.py
go1_gym/envs/go1/go1_config.py
go1_gym/envs/go1/velocity_tracking/__init__.py
go1_gym/envs/rewards/corl_rewards.py
go1_gym/envs/wrappers/history_wrapper.py
go1_gym/utils/__init__.py
go1_gym/utils/math_utils.py
go1_gym/utils/terrain.py
go1_gym_deploy/__init__.py
go1_gym_deploy/autostart/start_controller.sh
go1_gym_deploy/autostart/start_unitree_sdk.sh
go1_gym_deploy/docker/Dockerfile
go1_gym_deploy/docker/Makefile
go1_gym_deploy/docker/entrypoint.sh
go1_gym_deploy/docker/unzip_image.sh
go1_gym_deploy/docker/zip_image.sh
go1_gym_deploy/envs/__init__.py
go1_gym_deploy/envs/history_wrapper.py
go1_gym_deploy/envs/lcm_agent.py
go1_gym_deploy/installer/install_deployment_code.sh
go1_gym_deploy/lcm_types/__init__.py
go1_gym_deploy/lcm_types/camera_message_lcmt.py
go1_gym_deploy/lcm_types/camera_message_rect_wide.py
go1_gym_deploy/lcm_types/leg_control_data_lcmt.lcm
go1_gym_deploy/lcm_types/leg_control_data_lcmt.py
go1_gym_deploy/lcm_types/pd_tau_targets_lcmt.lcm
go1_gym_deploy/lcm_types/pd_tau_targets_lcmt.py
go1_gym_deploy/lcm_types/rc_command_lcmt.lcm
go1_gym_deploy/lcm_types/rc_command_lcmt.py
go1_gym_deploy/lcm_types/state_estimator_lcmt.lcm
go1_gym_deploy/lcm_types/state_estimator_lcmt.py
go1_gym_deploy/scripts/__init__.py
go1_gym_deploy/scripts/deploy_policy.py
go1_gym_deploy/scripts/send_to_unitree.sh
go1_gym_deploy/setup.py
go1_gym_deploy/tests/__init__.py
go1_gym_deploy/tests/check_camera_msgs.py
go1_gym_deploy/unitree_legged_sdk_bin/__init__.py
go1_gym_deploy/unitree_legged_sdk_bin/lcm_position
go1_gym_deploy/unitree_legged_sdk_bin/lcm_position.cpp
go1_gym_deploy/utils/__init__.py
go1_gym_deploy/utils/cheetah_state_estimator.py
go1_gym_deploy/utils/command_profile.py
go1_gym_deploy/utils/deployment_runner.py
go1_gym_deploy/utils/logger.py
go1_gym_deploy/utils/network_config_unitree.py
go1_gym_learn/__init__.py
go1_gym_learn/env/__init__.py
go1_gym_learn/env/vec_env.py
go1_gym_learn/eval_metrics/__init__.py
go1_gym_learn/eval_metrics/domain_randomization.py
go1_gym_learn/eval_metrics/metrics.py
go1_gym_learn/ppo/__init__.py
go1_gym_learn/ppo/actor_critic.py
go1_gym_learn/ppo/metrics_caches.py
go1_gym_learn/ppo/ppo.py
go1_gym_learn/ppo/rollout_storage.py
go1_gym_learn/ppo_cse/__init__.py
go1_gym_learn/ppo_cse/actor_critic.py
go1_gym_learn/ppo_cse/metrics_caches.py
go1_gym_learn/ppo_cse/ppo.py
go1_gym_learn/ppo_cse/rollout_storage.py
go1_gym_learn/utils/__init__.py
go1_gym_learn/utils/utils.py
resources/actuator_nets/unitree_go1.pt
resources/objects/cube.urdf
resources/robots/go1/urdf/go1.urdf
resources/robots/go1/xml/go1.xml
resources/robots/mini_cheetah/meshes/lower_leg.dae.meta
resources/robots/mini_cheetah/meshes/mini_abad.obj.meta
resources/robots/mini_cheetah/meshes/mini_body.obj.meta
resources/robots/mini_cheetah/meshes/mini_lower_link.obj.meta
resources/robots/mini_cheetah/meshes/mini_upper_link.obj.meta
resources/robots/mini_cheetah/urdf/mini_cheetah.urdf
resources/robots/mini_cheetah/urdf/mini_cheetah_simple.urdf
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/.charts.yml
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/checkpoints/ac_weights_last.pt
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/checkpoints/adaptation_module_latest.jit
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/checkpoints/body_latest.jit
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/curriculum/info.pkl
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/metrics.pkl
runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/parameters.pkl
scripts/__init__.py
scripts/actuator_net/__init__.py
scripts/actuator_net/eval.py
scripts/actuator_net/train.py
scripts/actuator_net/utils.py
scripts/play.py
scripts/test.py
scripts/train.py
setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `media` | 1 | 6.0 MB | [`media/_OMITTED.md`](./media/_OMITTED.md) |
| `resources/robots/go1/meshes` | 5 | 9.8 MB | [`resources/robots/go1/meshes/_OMITTED.md`](./resources/robots/go1/meshes/_OMITTED.md) |
| `resources/robots/mini_cheetah/meshes` | 5 | 5.8 MB | [`resources/robots/mini_cheetah/meshes/_OMITTED.md`](./resources/robots/mini_cheetah/meshes/_OMITTED.md) |
| `resources/robots/mini_cheetah/urdf/meshes` | 4 | 3.7 MB | [`resources/robots/mini_cheetah/urdf/meshes/_OMITTED.md`](./resources/robots/mini_cheetah/urdf/meshes/_OMITTED.md) |
| `resources/textures` | 11 | 18.2 MB | [`resources/textures/_OMITTED.md`](./resources/textures/_OMITTED.md) |
| `runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/curriculum` | 1 | 21.6 MB | [`runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/curriculum/_OMITTED.md`](./runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/curriculum/_OMITTED.md) |
| `runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/videos` | 1 | 322 KB | [`runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/videos/_OMITTED.md`](./runs/gait-conditioned-agility/pretrain-v0/train/025417.456545/videos/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
