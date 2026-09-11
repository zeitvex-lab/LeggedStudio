# m20_rl_isaacsim — 参考资源

> **来源**：`00_open/m20_rl_isaacsim/`　｜　**类型**：参考项目
> **关联机型**：deeprobotics_m20（云深处 M20 轮足）、deeprobotics_lite3（云深处 Lite3 四足）
> **定位**：M20 轮足 IsaacSim RL 工程
> **收录**：87 个文件 / 3.7 MB（其中推理策略/模型文件 4 个）
> **已省略**：76 个文件 / 67.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（10 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（25 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（7 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（4 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（23 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（18 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （14 个文件）
deep_robotics_model/  （10 个文件）
    (直接文件)/
    Lite3/
    M20/
    X30/
docs/  （1 个文件）
    (直接文件)/
exported/  （4 个文件）
    (直接文件)/
scripts/  （16 个文件）
    reinforcement_learning/
    tools/
source/  （42 个文件）
    rl_training/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 50 |
| `.md` | 7 |
| `(无扩展名)` | 6 |
| `.txt` | 6 |
| `.onnx` | 4 |
| `.toml` | 3 |
| `.xml` | 3 |
| `.urdf` | 3 |
| `.yaml` | 2 |
| `.gv` | 1 |
| `.pdf` | 1 |
| `.sh` | 1 |

## 文件索引（项目内相对路径）

```text
CLAUDE.md
CONTRIBUTORS.md
LICENSE
LICENSE-robot_lab
README.md
VERSION
deep_robotics_model/.gitattributes
deep_robotics_model/Contributors.md
deep_robotics_model/LICENSE.txt
deep_robotics_model/Lite3/Lite3_mjcf/mjcf/Lite3.xml
deep_robotics_model/Lite3/Lite3_urdf/urdf/Lite3.urdf
deep_robotics_model/M20/M20_mjcf/mjcf/M20.xml
deep_robotics_model/M20/M20_urdf/urdf/M20.urdf
deep_robotics_model/README.md
deep_robotics_model/X30/X30_mjcf/mjcf/X30.xml
deep_robotics_model/X30/X30_urdf/urdf/X30.urdf
docs/M20_导航系统交接文档.md
exported/m20_new1_policy.onnx
exported/m20_new_policy.onnx
exported/m20_policy.onnx
exported/yk_policy.onnx
frames_2026-04-22_16.07.26.gv
frames_2026-04-22_16.07.26.pdf
pyproject.toml
scripts/reinforcement_learning/rl_utils.py
scripts/reinforcement_learning/rsl_rl/cli_args.py
scripts/reinforcement_learning/rsl_rl/m20_nav_app.py
scripts/reinforcement_learning/rsl_rl/m20_nav_app_beifen.py
scripts/reinforcement_learning/rsl_rl/m20_sensor_saver.py
scripts/reinforcement_learning/rsl_rl/map/full_warehouse.yaml
scripts/reinforcement_learning/rsl_rl/map/yq_1_mesh_vis.yaml
scripts/reinforcement_learning/rsl_rl/play.py
scripts/reinforcement_learning/rsl_rl/play_onnx_perception.py
scripts/reinforcement_learning/rsl_rl/ros2_bridge_graph_m20.py
scripts/reinforcement_learning/rsl_rl/ros2_bridge_graph_m20_1.py
scripts/reinforcement_learning/rsl_rl/ros2_cmd_vel_bridge.py
scripts/reinforcement_learning/rsl_rl/train.py
scripts/tools/compare_runs.py
scripts/tools/export_onnx_fast.py
scripts/tools/list_envs.py
simple_nav2.launch.py
source/rl_training/config/extension.toml
source/rl_training/pyproject.toml
source/rl_training/rl_training.egg-info/PKG-INFO
source/rl_training/rl_training.egg-info/SOURCES.txt
source/rl_training/rl_training.egg-info/dependency_links.txt
source/rl_training/rl_training.egg-info/not-zip-safe
source/rl_training/rl_training.egg-info/requires.txt
source/rl_training/rl_training.egg-info/top_level.txt
source/rl_training/rl_training/__init__.py
source/rl_training/rl_training/assets/__init__.py
source/rl_training/rl_training/assets/deeprobotics.py
source/rl_training/rl_training/tasks/__init__.py
source/rl_training/rl_training/tasks/manager_based/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/quadruped/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/agents/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/agents/rsl_rl_ppo_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/flat_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/rough_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/agents/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/agents/rsl_rl_ppo_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/flat_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/m20_perception_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/m20_sensors_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/m20_sensors_cfg_1.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/rough_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/rough_fixed_obstacle_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/terrains/hf_terrains.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/commands.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/curriculums.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/events.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/observations.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/rewards.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/velocity_env_cfg.py
source/rl_training/rl_training/ui_extension_example.py
source/rl_training/setup.py
start_m20_nav.sh
test.py
tree.txt
use.md
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `deep_robotics_model/Lite3/Lite3_mjcf/meshes` | 4 | 3.3 MB | [`deep_robotics_model/Lite3/Lite3_mjcf/meshes/_OMITTED.md`](./deep_robotics_model/Lite3/Lite3_mjcf/meshes/_OMITTED.md) |
| `deep_robotics_model/Lite3/Lite3_urdf/meshes` | 4 | 3.3 MB | [`deep_robotics_model/Lite3/Lite3_urdf/meshes/_OMITTED.md`](./deep_robotics_model/Lite3/Lite3_urdf/meshes/_OMITTED.md) |
| `deep_robotics_model/Lite3/Lite3_usd` | 1 | 1 KB | [`deep_robotics_model/Lite3/Lite3_usd/_OMITTED.md`](./deep_robotics_model/Lite3/Lite3_usd/_OMITTED.md) |
| `deep_robotics_model/Lite3/Lite3_usd/configuration` | 4 | 4.8 MB | [`deep_robotics_model/Lite3/Lite3_usd/configuration/_OMITTED.md`](./deep_robotics_model/Lite3/Lite3_usd/configuration/_OMITTED.md) |
| `deep_robotics_model/M20/M20_mjcf/meshes` | 17 | 11.4 MB | [`deep_robotics_model/M20/M20_mjcf/meshes/_OMITTED.md`](./deep_robotics_model/M20/M20_mjcf/meshes/_OMITTED.md) |
| `deep_robotics_model/M20/M20_urdf/meshes` | 17 | 11.4 MB | [`deep_robotics_model/M20/M20_urdf/meshes/_OMITTED.md`](./deep_robotics_model/M20/M20_urdf/meshes/_OMITTED.md) |
| `deep_robotics_model/M20/M20_usd` | 1 | 5 KB | [`deep_robotics_model/M20/M20_usd/_OMITTED.md`](./deep_robotics_model/M20/M20_usd/_OMITTED.md) |
| `deep_robotics_model/M20/M20_usd/configuration` | 4 | 16.4 MB | [`deep_robotics_model/M20/M20_usd/configuration/_OMITTED.md`](./deep_robotics_model/M20/M20_usd/configuration/_OMITTED.md) |
| `deep_robotics_model/X30/X30_mjcf/meshes` | 4 | 4.0 MB | [`deep_robotics_model/X30/X30_mjcf/meshes/_OMITTED.md`](./deep_robotics_model/X30/X30_mjcf/meshes/_OMITTED.md) |
| `deep_robotics_model/X30/X30_urdf/meshes` | 4 | 4.0 MB | [`deep_robotics_model/X30/X30_urdf/meshes/_OMITTED.md`](./deep_robotics_model/X30/X30_urdf/meshes/_OMITTED.md) |
| `deep_robotics_model/X30/X30_usd` | 1 | 1 KB | [`deep_robotics_model/X30/X30_usd/_OMITTED.md`](./deep_robotics_model/X30/X30_usd/_OMITTED.md) |
| `deep_robotics_model/X30/X30_usd/configuration` | 4 | 5.8 MB | [`deep_robotics_model/X30/X30_usd/configuration/_OMITTED.md`](./deep_robotics_model/X30/X30_usd/configuration/_OMITTED.md) |
| `deep_robotics_model/images` | 6 | 1.0 MB | [`deep_robotics_model/images/_OMITTED.md`](./deep_robotics_model/images/_OMITTED.md) |
| `docs/imgs` | 2 | 351 KB | [`docs/imgs/_OMITTED.md`](./docs/imgs/_OMITTED.md) |
| `scripts/reinforcement_learning/rsl_rl/map` | 3 | 1.2 MB | [`scripts/reinforcement_learning/rsl_rl/map/_OMITTED.md`](./scripts/reinforcement_learning/rsl_rl/map/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
