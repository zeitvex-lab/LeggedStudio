# humanoid-gym — 参考资源

> **来源**：`00_open/humanoid-gym/`　｜　**类型**：人形训练上游参考（humanoid_gym；reward / terrain 组织）
> **关联机型**：（无，通用）
> **定位**：roboterax/humanoid-gym：人形（XBot-L）RL 训练 + Sim2Real 工程（`humanoid/` 下的 envs / algorithms / scripts 与 reward、terrain 组织、参考动作）；EngineAI RL Workspace 自述其 reward 与 terrain 生成部分受该库启发 ⇒ 人形任务的奖励/地形写法对照源
> **收录**：34 个文件 / 2.4 MB（其中推理策略/模型文件 1 个）
> **已省略**：89 个文件 / 26.7 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（2 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（9 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（2 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（1 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（18 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
humanoid/  （26 个文件）
    (直接文件)/
    algo/
    envs/
    scripts/
    utils/
logs/  （1 个文件）
    XBot_ppo/
resources/  （3 个文件）
    robots/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 26 |
| `(无扩展名)` | 3 |
| `.xml` | 2 |
| `.md` | 1 |
| `.pt` | 1 |
| `.urdf` | 1 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.gitignore
README.md
humanoid/__init__.py
humanoid/algo/__init__.py
humanoid/algo/ppo/__init__.py
humanoid/algo/ppo/actor_critic.py
humanoid/algo/ppo/on_policy_runner.py
humanoid/algo/ppo/ppo.py
humanoid/algo/ppo/rollout_storage.py
humanoid/algo/vec_env.py
humanoid/envs/__init__.py
humanoid/envs/base/LICENSE
humanoid/envs/base/base_config.py
humanoid/envs/base/base_task.py
humanoid/envs/base/legged_robot.py
humanoid/envs/base/legged_robot_config.py
humanoid/envs/custom/humanoid_config.py
humanoid/envs/custom/humanoid_env.py
humanoid/scripts/play.py
humanoid/scripts/sim2sim.py
humanoid/scripts/train.py
humanoid/utils/__init__.py
humanoid/utils/calculate_gait.py
humanoid/utils/helpers.py
humanoid/utils/logger.py
humanoid/utils/math.py
humanoid/utils/task_registry.py
humanoid/utils/terrain.py
logs/XBot_ppo/exported/policies/policy_example.pt
resources/robots/XBot/mjcf/XBot-L-terrain.xml
resources/robots/XBot/mjcf/XBot-L.xml
resources/robots/XBot/urdf/XBot-L.urdf
setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `images` | 1 | 13.4 MB | [`images/_OMITTED.md`](./images/_OMITTED.md) |
| `resources/robots/XBot/meshes` | 87 | 13.3 MB | [`resources/robots/XBot/meshes/_OMITTED.md`](./resources/robots/XBot/meshes/_OMITTED.md) |
| `resources/robots/XBot/terrain` | 1 | 6 KB | [`resources/robots/XBot/terrain/_OMITTED.md`](./resources/robots/XBot/terrain/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
