# rl_training — 参考资源

> **来源**：`00_open/rl_training/`　｜　**类型**：参考项目
> **关联机型**：deeprobotics_lite3（云深处 Lite3 四足）、deeprobotics_m20（云深处 M20 轮足）
> **定位**：云深处 RL 训练任务与配置
> **收录**：133 个文件 / 39.7 MB（其中推理策略/模型文件 0 个）
> **已省略**：3 个文件 / 476 KB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（28 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（90 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（13 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （10 个文件）
scripts/  （7 个文件）
    reinforcement_learning/
    tools/
source/  （116 个文件）
    rl_training/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 75 |
| `.txt` | 47 |
| `(无扩展名)` | 6 |
| `.toml` | 3 |
| `.md` | 2 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.gitignore
.gitmodules
CONTRIBUTORS.md
LICENSE
LICENSE-robot_lab
README.md
VERSION
pyproject.toml
scripts/reinforcement_learning/rl_utils.py
scripts/reinforcement_learning/rsl_rl/cli_args.py
scripts/reinforcement_learning/rsl_rl/play.py
scripts/reinforcement_learning/rsl_rl/train.py
scripts/tools/compare_runs.py
scripts/tools/export_onnx_fast.py
scripts/tools/list_envs.py
source/rl_training/config/extension.toml
source/rl_training/pyproject.toml
source/rl_training/rl_training/__init__.py
source/rl_training/rl_training/actuator/PDActuator.py
source/rl_training/rl_training/actuator/__init__.py
source/rl_training/rl_training/assets/__init__.py
source/rl_training/rl_training/assets/deeprobotics.py
source/rl_training/rl_training/envs/__init__.py
source/rl_training/rl_training/envs/amp_locomotion_env.py
source/rl_training/rl_training/managers/__init__.py
source/rl_training/rl_training/managers/amp_helper_manager.py
source/rl_training/rl_training/rsl_rl/__init__.py
source/rl_training/rl_training/rsl_rl/algorithms/__init__.py
source/rl_training/rl_training/rsl_rl/algorithms/ppo_amp.py
source/rl_training/rl_training/rsl_rl/datasets/__init__.py
source/rl_training/rl_training/rsl_rl/datasets/motion_loader.py
source/rl_training/rl_training/rsl_rl/datasets/motion_util.py
source/rl_training/rl_training/rsl_rl/datasets/pose3d.py
source/rl_training/rl_training/rsl_rl/modules/__init__.py
source/rl_training/rl_training/rsl_rl/modules/amp_discriminator.py
source/rl_training/rl_training/rsl_rl/modules/ce_net.py
source/rl_training/rl_training/rsl_rl/runners/__init__.py
source/rl_training/rl_training/rsl_rl/runners/amp_on_policy_runner.py
source/rl_training/rl_training/rsl_rl/storage/__init__.py
source/rl_training/rl_training/rsl_rl/storage/amp_storage.py
source/rl_training/rl_training/rsl_rl/utils/__init__.py
source/rl_training/rl_training/rsl_rl/utils/utils.py
source/rl_training/rl_training/tasks/__init__.py
source/rl_training/rl_training/tasks/manager_based/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/amp_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/config/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/config/humanoid/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/config/humanoid/dr02/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/config/humanoid/dr02/agents/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/config/humanoid/dr02/agents/rsl_rl_amp_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/config/humanoid/dr02/flat_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/ACCAD_Male2Walking_c3d_B10 -  Walk turn left 45_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/ACCAD_Male2Walking_c3d_B14 -  Walk turn right 45 t2_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/ACCAD_Male2Walking_c3d_B4 - Stand to Walk backwards_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/ACCAD_Male2Walking_c3d_B5 -  Walk backwards_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_turn_LeftTurn07_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_turn_RightTurn06_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_turn_bend_left02_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_turn_bend_right06_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_WalkingStraightBackwards05_1_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_WalkingStraightBackwards06_1_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_WalkingStraightBackwards09_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_WalkingStraightBackwards10_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_WalkingStraightForwards02_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_WalkingStraightForwards10_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_walking_fast02_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_walking_medium04_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/KIT_walk_walking_slow01_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/SFU_0005_Walking001_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/SFU_0008_Walking002_poses.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_clockwise_fast.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_clockwise_fast.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_clockwise_medium.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_clockwise_slow.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_counterclockwise_fast.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_counterclockwise_medium.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_counterclockwise_slow.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_turn_in_place_counterclockwise_very_fast.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_fast_1.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_fast_2.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_medium_1.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_medium_2.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_slow_1.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_slow_2.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_slow_3.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_backward_slow_4.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_forward_fast_1.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_forward_fast_2.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_forward_medium_1.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_forward_medium_2.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_forward_slow_1.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_forward_slow_2.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_turn_clockwise_medium.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_turn_clockwise_slow.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_turn_counterclockwise_fast.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_turn_counterclockwise_medium.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/datasets/amp_dataset_ik/nokov_walk_turn_counterclockwise_slow.txt
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/commands.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/curriculums.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/events.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/observations.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/rewards.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/symmetry/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/symmetry/dr02.py
source/rl_training/rl_training/tasks/manager_based/locomotion/amp/mdp/terminations.py
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
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/rough_env_cfg.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/__init__.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/commands.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/curriculums.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/events.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/observations.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/mdp/rewards.py
source/rl_training/rl_training/tasks/manager_based/locomotion/velocity/velocity_env_cfg.py
source/rl_training/rl_training/ui_extension_example.py
source/rl_training/setup.py
tree.txt
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs/imgs` | 3 | 476 KB | [`docs/imgs/_OMITTED.md`](./docs/imgs/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
