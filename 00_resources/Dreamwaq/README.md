# Dreamwaq — 参考资源

> **来源**：`00_open/Dreamwaq/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、deeprobotics_m20（云深处 M20 轮足）
> **定位**：DreamWaQ 盲式运动控制实现
> **收录**：51 个文件 / 551 KB（其中推理策略/模型文件 0 个）
> **已省略**：64 个文件 / 102.2 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（4 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（14 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（6 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（3 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **文档与其它**（24 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （2 个文件）
deploy/  （7 个文件）
    deploy_mujoco/
legged_gym/  （21 个文件）
    (直接文件)/
    envs/
    scripts/
    utils/
resources/  （6 个文件）
    robots/
rsl_rl/  （15 个文件）
    (直接文件)/
    rsl_rl/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 40 |
| `.xml` | 6 |
| `.yaml` | 2 |
| `.urdf` | 2 |
| `.md` | 1 |

## 文件索引（项目内相对路径）

```text
README.md
deploy/deploy_mujoco/M20/mjcf/M20.xml
deploy/deploy_mujoco/M20/mjcf/scene.xml
deploy/deploy_mujoco/M20/mjcf/scene_terrain.xml
deploy/deploy_mujoco/configs/go2.yaml
deploy/deploy_mujoco/configs/m20.yaml
deploy/deploy_mujoco/deploy_mujoco.py
deploy/deploy_mujoco/deploy_mujoco_go2.py
legged_gym/__init__.py
legged_gym/envs/GO2_Stand/GO2_Handstand/Go2_handstand.py
legged_gym/envs/GO2_Stand/GO2_Handstand/Go2_handstand_Config.py
legged_gym/envs/GO2_Stand/GO2_Leggedstand/Go2_legstand.py
legged_gym/envs/GO2_Stand/GO2_Leggedstand/Go2_legstand_Config.py
legged_gym/envs/M20/m20.py
legged_gym/envs/M20/m20_config.py
legged_gym/envs/__init__.py
legged_gym/envs/base/base_config.py
legged_gym/envs/base/base_task.py
legged_gym/envs/base/legged_robot.py
legged_gym/envs/base/legged_robot_config.py
legged_gym/scripts/play.py
legged_gym/scripts/plot_data.py
legged_gym/scripts/train.py
legged_gym/utils/__init__.py
legged_gym/utils/helpers.py
legged_gym/utils/logger.py
legged_gym/utils/math.py
legged_gym/utils/task_registry.py
legged_gym/utils/terrain.py
resources/robots/go2/go2/1.py
resources/robots/go2/go2/go2.xml
resources/robots/go2/go2/scene.xml
resources/robots/go2/go2/scene_terrain.xml
resources/robots/go2/urdf/go2.urdf
resources/robots/m20/urdf/m20.urdf
rsl_rl/rsl_rl/__init__.py
rsl_rl/rsl_rl/algorithms/__init__.py
rsl_rl/rsl_rl/algorithms/ppo_dreamwaq.py
rsl_rl/rsl_rl/env/__init__.py
rsl_rl/rsl_rl/env/vec_env.py
rsl_rl/rsl_rl/modules/__init__.py
rsl_rl/rsl_rl/modules/actor_critic_dreamwaq.py
rsl_rl/rsl_rl/modules/vae.py
rsl_rl/rsl_rl/runners/__init__.py
rsl_rl/rsl_rl/runners/dreamwaq_runner.py
rsl_rl/rsl_rl/storage/__init__.py
rsl_rl/rsl_rl/storage/rollout_storage_dreamwaq.py
rsl_rl/rsl_rl/utils/__init__.py
rsl_rl/rsl_rl/utils/utils.py
rsl_rl/setup.py
setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 26.2 MB | [`_OMITTED.md`](./_OMITTED.md) |
| `deploy/deploy_mujoco/M20/meshes` | 17 | 11.4 MB | [`deploy/deploy_mujoco/M20/meshes/_OMITTED.md`](./deploy/deploy_mujoco/M20/meshes/_OMITTED.md) |
| `deploy/deploy_mujoco/M20/mjcf` | 2 | 19 KB | [`deploy/deploy_mujoco/M20/mjcf/_OMITTED.md`](./deploy/deploy_mujoco/M20/mjcf/_OMITTED.md) |
| `resources/robots/go2/dae` | 7 | 24.7 MB | [`resources/robots/go2/dae/_OMITTED.md`](./resources/robots/go2/dae/_OMITTED.md) |
| `resources/robots/go2/go2` | 3 | 629 KB | [`resources/robots/go2/go2/_OMITTED.md`](./resources/robots/go2/go2/_OMITTED.md) |
| `resources/robots/go2/go2/assets` | 17 | 27.8 MB | [`resources/robots/go2/go2/assets/_OMITTED.md`](./resources/robots/go2/go2/assets/_OMITTED.md) |
| `resources/robots/m20/meshes` | 17 | 11.4 MB | [`resources/robots/m20/meshes/_OMITTED.md`](./resources/robots/m20/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
