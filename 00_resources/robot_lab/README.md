# robot_lab — 参考资源

> **来源**：`00_open/robot_lab/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、unitree_g1（宇树 G1 人形）、deeprobotics_lite3（云深处 Lite3 四足）、deeprobotics_m20（云深处 M20 轮足）
> **定位**：robot_lab：IsaacLab 版多机型训练框架
> **收录**：370 个文件 / 3.5 MB（其中推理策略/模型文件 0 个）
> **已省略**：539 个文件 / 459.4 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（77 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（36 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（25 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（156 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（7 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（69 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （10 个文件）
.github/  （5 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
    workflows/
docker/  （3 个文件）
    (直接文件)/
docs/  （1 个文件）
    (直接文件)/
scripts/  （34 个文件）
    (直接文件)/
    isaaclab/
    mjlab/
source/  （308 个文件）
    robot_lab/
tests/  （9 个文件）
    framework/
    integration/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 286 |
| `.urdf` | 31 |
| `.mtl` | 27 |
| `(无扩展名)` | 6 |
| `.md` | 5 |
| `.yaml` | 4 |
| `.toml` | 3 |
| `.yml` | 2 |
| `.csv` | 2 |
| `.sh` | 1 |
| `.txt` | 1 |
| `.base` | 1 |
| `.npz` | 1 |

## 文件索引（项目内相对路径）

```text
.dockerignore
.gitattributes
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/config.yml
.github/LICENSE_HEADER.txt
.github/PULL_REQUEST_TEMPLATE.md
.github/workflows/pre-commit.yaml
.gitignore
.pre-commit-config.yaml
CONTRIBUTORS.md
LICENSE
README.md
VERSION
docker/.env.base
docker/Dockerfile
docker/docker-compose.yaml
docs/migration-from-subclass.md
pyproject.toml
scripts/__init__.py
scripts/isaaclab/__init__.py
scripts/isaaclab/reinforcement_learning/__init__.py
scripts/isaaclab/reinforcement_learning/cusrl/__init__.py
scripts/isaaclab/reinforcement_learning/cusrl/play.py
scripts/isaaclab/reinforcement_learning/cusrl/train.py
scripts/isaaclab/reinforcement_learning/rl_utils.py
scripts/isaaclab/reinforcement_learning/rsl_rl/__init__.py
scripts/isaaclab/reinforcement_learning/rsl_rl/cli_args.py
scripts/isaaclab/reinforcement_learning/rsl_rl/play.py
scripts/isaaclab/reinforcement_learning/rsl_rl/play_cs.py
scripts/isaaclab/reinforcement_learning/rsl_rl/train.py
scripts/isaaclab/reinforcement_learning/skrl/__init__.py
scripts/isaaclab/reinforcement_learning/skrl/play.py
scripts/isaaclab/reinforcement_learning/skrl/train.py
scripts/isaaclab/tools/beyondmimic/csv_to_npz.py
scripts/isaaclab/tools/beyondmimic/replay_npz.py
scripts/isaaclab/tools/clean_trash.py
scripts/isaaclab/tools/convert_mjcf.py
scripts/isaaclab/tools/convert_urdf.py
scripts/isaaclab/tools/delivery.py
scripts/isaaclab/tools/list_envs.py
scripts/isaaclab/tools/random_agent.py
scripts/isaaclab/tools/train_batch.py
scripts/isaaclab/tools/zero_agent.py
scripts/mjlab/__init__.py
scripts/mjlab/reinforcement_learning/__init__.py
scripts/mjlab/reinforcement_learning/rsl_rl/__init__.py
scripts/mjlab/reinforcement_learning/rsl_rl/play.py
scripts/mjlab/reinforcement_learning/rsl_rl/train.py
scripts/mjlab/tools/__init__.py
scripts/mjlab/tools/list_envs.py
scripts/play.py
scripts/train.py
setup_env.sh
source/robot_lab/config/extension.toml
source/robot_lab/data/Robots/agibot/d1/urdf/edu.urdf
source/robot_lab/data/Robots/booster/t1_description/meshes/AL1.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/AL2.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/AL3.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/AR1.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/AR2.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/AR3.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Ankle_cross_left.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Ankle_cross_right.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Foot_link.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/H1.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/H2.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Hip_pitch_left.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Hip_pitch_right.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Hip_roll_left.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Hip_roll_right.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Hip_yaw.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Left_hand.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Right_hand.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Shank_left.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Shank_right.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Trunk.mtl
source/robot_lab/data/Robots/booster/t1_description/meshes/Waist.mtl
source/robot_lab/data/Robots/booster/t1_description/urdf/robot.urdf
source/robot_lab/data/Robots/ddt/tita_description/urdf/tita.urdf
source/robot_lab/data/Robots/deeprobotics/lite3_description/urdf/lite3.urdf
source/robot_lab/data/Robots/deeprobotics/m20_description/urdf/m20.urdf
source/robot_lab/data/Robots/fftai/gr1t1_description/urdf/GR1T1.urdf
source/robot_lab/data/Robots/fftai/gr1t1_description/urdf/GR1T1_lower_limb.urdf
source/robot_lab/data/Robots/fftai/gr1t2_description/urdf/GR1T2.urdf
source/robot_lab/data/Robots/fftai/gr1t2_description/urdf/GR1T2_lower_limb.urdf
source/robot_lab/data/Robots/magiclab/magicbot-Gen1/urdf/MAGICBOT.urdf
source/robot_lab/data/Robots/magiclab/magicbot-Gen1/urdf/MAGICBOT_with_hand.urdf
source/robot_lab/data/Robots/magiclab/magicbot-Z1/urdf/MagicBotZ1.urdf
source/robot_lab/data/Robots/magiclab/magicdog/urdf/magicdog.urdf
source/robot_lab/data/Robots/magiclab/magicdog_w/urdf/magicdog_w.urdf
source/robot_lab/data/Robots/openloong/loong_description/urdf/loong.urdf
source/robot_lab/data/Robots/roboparty/atom01_description/urdf/atom01.urdf
source/robot_lab/data/Robots/robotera/xbot_description/meshes/base_link.mtl
source/robot_lab/data/Robots/robotera/xbot_description/meshes/d455.mtl
source/robot_lab/data/Robots/robotera/xbot_description/meshes/head.mtl
source/robot_lab/data/Robots/robotera/xbot_description/meshes/left_leg_pitch_link.mtl
source/robot_lab/data/Robots/robotera/xbot_description/meshes/right_leg_pitch_link.mtl
source/robot_lab/data/Robots/robotera/xbot_description/urdf/robot.urdf
source/robot_lab/data/Robots/unitree/a1_description/urdf/a1.urdf
source/robot_lab/data/Robots/unitree/b2_description/urdf/b2_description.urdf
source/robot_lab/data/Robots/unitree/b2w_description/urdf/b2w_description.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_23dof_rev_1_0.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_29dof_lock_waist_rev_1_0.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_29dof_lock_waist_with_hand_rev_1_0.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_29dof_rev_1_0.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_29dof_rev_1_0_with_inspire_hand_DFQ.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_29dof_rev_1_0_with_inspire_hand_FTP.urdf
source/robot_lab/data/Robots/unitree/g1_description/urdf/g1_29dof_with_hand_rev_1_0.urdf
source/robot_lab/data/Robots/unitree/go2_description/urdf/go2_description.urdf
source/robot_lab/data/Robots/unitree/go2w_description/urdf/go2w_description.urdf
source/robot_lab/data/Robots/zsibot/zsl1_description/urdf/zsl1.urdf
source/robot_lab/data/Robots/zsibot/zsl1w_description/urdf/zsl1w.urdf
source/robot_lab/pyproject.toml
source/robot_lab/robot_lab/__init__.py
source/robot_lab/robot_lab/assets/__init__.py
source/robot_lab/robot_lab/assets/agibot.py
source/robot_lab/robot_lab/assets/booster.py
source/robot_lab/robot_lab/assets/builders/__init__.py
source/robot_lab/robot_lab/assets/builders/isaaclab.py
source/robot_lab/robot_lab/assets/builders/mjlab.py
source/robot_lab/robot_lab/assets/data/__init__.py
source/robot_lab/robot_lab/assets/data/unitree_a1.py
source/robot_lab/robot_lab/assets/ddtrobot.py
source/robot_lab/robot_lab/assets/deeprobotics.py
source/robot_lab/robot_lab/assets/fftai.py
source/robot_lab/robot_lab/assets/magiclab.py
source/robot_lab/robot_lab/assets/openloong.py
source/robot_lab/robot_lab/assets/roboparty.py
source/robot_lab/robot_lab/assets/robotera.py
source/robot_lab/robot_lab/assets/unitree.py
source/robot_lab/robot_lab/assets/zsibot.py
source/robot_lab/robot_lab/framework/__init__.py
source/robot_lab/robot_lab/framework/detect.py
source/robot_lab/robot_lab/framework/isaaclab/__init__.py
source/robot_lab/robot_lab/framework/isaaclab/app.py
source/robot_lab/robot_lab/framework/isaaclab/cfg_types.py
source/robot_lab/robot_lab/framework/isaaclab/contact.py
source/robot_lab/robot_lab/framework/isaaclab/container.py
source/robot_lab/robot_lab/framework/isaaclab/events.py
source/robot_lab/robot_lab/framework/isaaclab/mdp_aliases.py
source/robot_lab/robot_lab/framework/isaaclab/obs_group.py
source/robot_lab/robot_lab/framework/isaaclab/register.py
source/robot_lab/robot_lab/framework/isaaclab/rl.py
source/robot_lab/robot_lab/framework/isaaclab/scene.py
source/robot_lab/robot_lab/framework/isaaclab/sensors.py
source/robot_lab/robot_lab/framework/isaaclab/sim_settings.py
source/robot_lab/robot_lab/framework/mjlab/__init__.py
source/robot_lab/robot_lab/framework/mjlab/app.py
source/robot_lab/robot_lab/framework/mjlab/cfg_types.py
source/robot_lab/robot_lab/framework/mjlab/contact.py
source/robot_lab/robot_lab/framework/mjlab/container.py
source/robot_lab/robot_lab/framework/mjlab/events.py
source/robot_lab/robot_lab/framework/mjlab/mdp_aliases.py
source/robot_lab/robot_lab/framework/mjlab/obs_group.py
source/robot_lab/robot_lab/framework/mjlab/register.py
source/robot_lab/robot_lab/framework/mjlab/rl.py
source/robot_lab/robot_lab/framework/mjlab/scene.py
source/robot_lab/robot_lab/framework/mjlab/sensors.py
source/robot_lab/robot_lab/framework/mjlab/sim_settings.py
source/robot_lab/robot_lab/framework/spec.py
source/robot_lab/robot_lab/tasks/__init__.py
source/robot_lab/robot_lab/tasks/direct/__init__.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/__init__.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/agents/__init__.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/agents/skrl_dance_amp_cfg.yaml
source/robot_lab/robot_lab/tasks/direct/g1_amp/g1_amp_env.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/g1_amp_env_cfg.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/README.md
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/__init__.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/csv2npz.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/g1_dance1_subject2_30.npz
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/motion_loader.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/motion_replayer.py
source/robot_lab/robot_lab/tasks/direct/g1_amp/motions/motion_viewer.py
source/robot_lab/robot_lab/tasks/manager_based/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/g1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/g1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/g1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/g1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/g1/motion/G1_Take_102.bvh_60hz.csv
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/config/g1/motion/G1_gangnam_style_V01.bvh_60hz.csv
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/mdp/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/mdp/commands.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/mdp/events.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/mdp/observations.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/mdp/rewards.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/mdp/terminations.py
source/robot_lab/robot_lab/tasks/manager_based/beyondmimic/tracking_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/booster_t1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/booster_t1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/booster_t1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/booster_t1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/booster_t1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/booster_t1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t2/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t2/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t2/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t2/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t2/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/fftai_gr1t2/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_gen1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_gen1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_gen1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_gen1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_gen1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_gen1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_z1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_z1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_z1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_z1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_z1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/magiclab_magicbot_z1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/openloong_loong/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/openloong_loong/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/openloong_loong/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/openloong_loong/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/openloong_loong/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/openloong_loong/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/roboparty_atom01/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/roboparty_atom01/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/roboparty_atom01/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/roboparty_atom01/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/roboparty_atom01/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/roboparty_atom01/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/robotera_xbot/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/robotera_xbot/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/robotera_xbot/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/robotera_xbot/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/robotera_xbot/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/robotera_xbot/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_g1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_g1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_g1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_g1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_g1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_g1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_h1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_h1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_h1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_h1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_h1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/humanoid/unitree_h1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/env/rewards.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/others/unitree_a1_handstand/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/agibot_d1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/agibot_d1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/agibot_d1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/agibot_d1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/agibot_d1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/agibot_d1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/agents/cusrl_distillation_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/agents/rsl_rl_distillation_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/anymal_d/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/deeprobotics_lite3/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/magiclab_magicdog/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/magiclab_magicdog/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/magiclab_magicdog/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/magiclab_magicdog/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/magiclab_magicdog/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/magiclab_magicdog/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_a1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_a1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_a1/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_a1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_a1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_a1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_b2/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_b2/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_b2/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_b2/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_b2/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_b2/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_go2/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_go2/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_go2/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_go2/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_go2/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/unitree_go2/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/zsibot_zsl1/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/zsibot_zsl1/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/zsibot_zsl1/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/zsibot_zsl1/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/quadruped/zsibot_zsl1/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/ddtrobot_tita/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/ddtrobot_tita/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/ddtrobot_tita/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/ddtrobot_tita/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/ddtrobot_tita/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/ddtrobot_tita/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/deeprobotics_m20/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/magiclab_magicdogw/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/magiclab_magicdogw/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/magiclab_magicdogw/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/magiclab_magicdogw/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/magiclab_magicdogw/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/magiclab_magicdogw/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_go2w/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_go2w/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_go2w/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_go2w/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_go2w/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_go2w/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/zsibot_zsl1w/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/zsibot_zsl1w/agents/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/zsibot_zsl1w/agents/cusrl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/zsibot_zsl1w/agents/rsl_rl_ppo_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/zsibot_zsl1w/flat_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/zsibot_zsl1w/rough_env_cfg.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/commands.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/curriculums.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/events.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/observations.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/rewards.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/symmetry/__init__.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/symmetry/anymal.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/utils.py
source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/velocity_env_cfg.py
source/robot_lab/robot_lab/ui_extension_example.py
source/robot_lab/setup.py
tests/framework/__init__.py
tests/framework/test_container_isaaclab.py
tests/framework/test_container_mjlab.py
tests/framework/test_detect.py
tests/framework/test_imports.py
tests/framework/test_no_framework_imports.py
tests/framework/test_spec.py
tests/integration/__init__.py
tests/integration/test_smoke.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs/imgs` | 24 | 12.4 MB | [`docs/imgs/_OMITTED.md`](./docs/imgs/_OMITTED.md) |
| `source/robot_lab/data/Robots/agibot/d1/meshes` | 17 | 14.6 MB | [`source/robot_lab/data/Robots/agibot/d1/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/agibot/d1/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/booster/t1_description/meshes` | 23 | 10.4 MB | [`source/robot_lab/data/Robots/booster/t1_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/booster/t1_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/ddt/tita_description/meshes` | 9 | 5.6 MB | [`source/robot_lab/data/Robots/ddt/tita_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/ddt/tita_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/deeprobotics/lite3_description/meshes` | 17 | 11.0 MB | [`source/robot_lab/data/Robots/deeprobotics/lite3_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/deeprobotics/lite3_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/deeprobotics/m20_description/meshes` | 17 | 11.4 MB | [`source/robot_lab/data/Robots/deeprobotics/m20_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/deeprobotics/m20_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/fftai/gr1t1_description/meshes` | 33 | 16.5 MB | [`source/robot_lab/data/Robots/fftai/gr1t1_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/fftai/gr1t1_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/fftai/gr1t2_description/meshes` | 34 | 13.2 MB | [`source/robot_lab/data/Robots/fftai/gr1t2_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/fftai/gr1t2_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/magiclab/magicbot-Gen1/meshes` | 56 | 27.3 MB | [`source/robot_lab/data/Robots/magiclab/magicbot-Gen1/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/magiclab/magicbot-Gen1/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/magiclab/magicbot-Z1/meshes` | 25 | 16.3 MB | [`source/robot_lab/data/Robots/magiclab/magicbot-Z1/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/magiclab/magicbot-Z1/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/magiclab/magicdog/meshes` | 7 | 13.0 MB | [`source/robot_lab/data/Robots/magiclab/magicdog/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/magiclab/magicdog/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/magiclab/magicdog_w/meshes` | 8 | 15.3 MB | [`source/robot_lab/data/Robots/magiclab/magicdog_w/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/magiclab/magicdog_w/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/openloong/loong_description/meshes` | 32 | 30.5 MB | [`source/robot_lab/data/Robots/openloong/loong_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/openloong/loong_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/roboparty/atom01_description/meshes` | 24 | 11.7 MB | [`source/robot_lab/data/Robots/roboparty/atom01_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/roboparty/atom01_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/robotera/xbot_description/meshes` | 88 | 18.1 MB | [`source/robot_lab/data/Robots/robotera/xbot_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/robotera/xbot_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/unitree/a1_description/meshes` | 6 | 8.7 MB | [`source/robot_lab/data/Robots/unitree/a1_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/unitree/a1_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/unitree/b2_description/meshes` | 13 | 19.6 MB | [`source/robot_lab/data/Robots/unitree/b2_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/unitree/b2_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/unitree/b2w_description/meshes` | 17 | 79.4 MB | [`source/robot_lab/data/Robots/unitree/b2w_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/unitree/b2w_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/unitree/g1_description/meshes` | 38 | 32.9 MB | [`source/robot_lab/data/Robots/unitree/g1_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/unitree/g1_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/unitree/go2_description/meshes` | 7 | 24.7 MB | [`source/robot_lab/data/Robots/unitree/go2_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/unitree/go2_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/unitree/go2w_description/meshes` | 9 | 29.0 MB | [`source/robot_lab/data/Robots/unitree/go2w_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/unitree/go2w_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/zsibot/zsl1_description/meshes` | 17 | 2.4 MB | [`source/robot_lab/data/Robots/zsibot/zsl1_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/zsibot/zsl1_description/meshes/_OMITTED.md) |
| `source/robot_lab/data/Robots/zsibot/zsl1w_description/meshes` | 18 | 35.4 MB | [`source/robot_lab/data/Robots/zsibot/zsl1w_description/meshes/_OMITTED.md`](./source/robot_lab/data/Robots/zsibot/zsl1w_description/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
