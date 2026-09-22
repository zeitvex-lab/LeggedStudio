# legged_gym — 参考资源

> **来源**：`00_open/legged_gym/`　｜　**类型**：训练框架上游参考（legged_gym 原始范式）
> **关联机型**：（无，通用）
> **定位**：leggedrobotics/legged_gym：腿足 RL 训练的**上游范式**（`legged_robot` / `legged_robot_config` / `_get_envs` 任务注册 / `terrain` 生成 / MDP 组织），本库多个训练工程 （go2_rl_gym / LeggedGym-Ex / gym_ex / HIMLoco / EngineAI RL Workspace …）的共同祖先 —— 用于回答"某个写法/约定是哪来的"，并与各分支做差异对照
> **收录**：42 个文件 / 320 KB（其中推理策略/模型文件 1 个）
> **已省略**：73 个文件 / 40.9 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（8 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（12 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（1 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **评测与测试**（1 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（18 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （5 个文件）
.github/  （1 个文件）
    ISSUE_TEMPLATE/
legged_gym/  （22 个文件）
    (直接文件)/
    envs/
    scripts/
    tests/
    utils/
licenses/  （5 个文件）
    assets/
    dependencies/
resources/  （9 个文件）
    actuator_nets/
    robots/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 23 |
| `.txt` | 9 |
| `.urdf` | 4 |
| `(无扩展名)` | 3 |
| `.md` | 2 |
| `.pt` | 1 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.github/ISSUE_TEMPLATE/bug_report.md
.gitignore
LICENSE
README.md
legged_gym/__init__.py
legged_gym/envs/__init__.py
legged_gym/envs/a1/a1_config.py
legged_gym/envs/anymal_b/anymal_b_config.py
legged_gym/envs/anymal_c/anymal.py
legged_gym/envs/anymal_c/flat/anymal_c_flat_config.py
legged_gym/envs/anymal_c/mixed_terrains/anymal_c_rough_config.py
legged_gym/envs/base/base_config.py
legged_gym/envs/base/base_task.py
legged_gym/envs/base/legged_robot.py
legged_gym/envs/base/legged_robot_config.py
legged_gym/envs/cassie/cassie.py
legged_gym/envs/cassie/cassie_config.py
legged_gym/scripts/play.py
legged_gym/scripts/train.py
legged_gym/tests/test_env.py
legged_gym/utils/__init__.py
legged_gym/utils/helpers.py
legged_gym/utils/logger.py
legged_gym/utils/math.py
legged_gym/utils/task_registry.py
legged_gym/utils/terrain.py
licenses/assets/ANYmal_b_license.txt
licenses/assets/ANYmal_c_license.txt
licenses/assets/a1_license.txt
licenses/assets/cassie_license.txt
licenses/dependencies/matplotlib_license.txt
resources/actuator_nets/anydrive_v3_lstm.pt
resources/robots/a1/a1_license.txt
resources/robots/a1/urdf/a1.urdf
resources/robots/anymal_b/ANYmal_b_license.txt
resources/robots/anymal_b/urdf/anymal_b.urdf
resources/robots/anymal_c/ANYmal_c_license.txt
resources/robots/anymal_c/urdf/anymal_c.urdf
resources/robots/cassie/cassie_license.txt
resources/robots/cassie/urdf/cassie.urdf
setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `resources/robots/a1/meshes` | 6 | 8.7 MB | [`resources/robots/a1/meshes/_OMITTED.md`](./resources/robots/a1/meshes/_OMITTED.md) |
| `resources/robots/anymal_b/meshes` | 10 | 21.0 MB | [`resources/robots/anymal_b/meshes/_OMITTED.md`](./resources/robots/anymal_b/meshes/_OMITTED.md) |
| `resources/robots/anymal_c/meshes` | 36 | 7.9 MB | [`resources/robots/anymal_c/meshes/_OMITTED.md`](./resources/robots/anymal_c/meshes/_OMITTED.md) |
| `resources/robots/cassie/meshes` | 21 | 3.3 MB | [`resources/robots/cassie/meshes/_OMITTED.md`](./resources/robots/cassie/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
