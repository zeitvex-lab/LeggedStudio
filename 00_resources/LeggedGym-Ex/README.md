# LeggedGym-Ex — 参考资源

> **来源**：`00_open/LeggedGym-Ex/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go1（宇树 Go1 四足）、unitree_g1（宇树 G1 人形）、limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）
> **定位**：legged_gym 扩展版：多机型训练环境与任务
> **收录**：306 个文件 / 16.2 MB（其中推理策略/模型文件 0 个）
> **已省略**：148 个文件 / 116.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（35 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（63 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（2 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（126 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（5 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（75 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （10 个文件）
.torch_extensions/  （3 个文件）
    gymtorch/
legged_gym/  （90 个文件）
    (直接文件)/
    envs/
    scripts/
    simulator/
    utils/
    warp/
resources/  （153 个文件）
    reference_motion/
    robots/
    sysid/
    terrains/
rsl_rl/  （47 个文件）
    (直接文件)/
    algorithms/
    env/
    modules/
    runners/
    storage/
    utils/
tests/  （3 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 137 |
| `.pkl` | 114 |
| `.urdf` | 18 |
| `.xml` | 15 |
| `.md` | 7 |
| `(无扩展名)` | 6 |
| `.sh` | 2 |
| `.genesis` | 1 |
| `.isaacgym` | 1 |
| `.isaaclab` | 1 |
| `.toml` | 1 |
| `.ninja` | 1 |
| `.txt` | 1 |
| `.csv` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
.torch_extensions/gymtorch/.ninja_deps
.torch_extensions/gymtorch/.ninja_log
.torch_extensions/gymtorch/build.ninja
AGENTS.md
Dockerfile
Dockerfile.genesis
Dockerfile.isaacgym
Dockerfile.isaaclab
LICENSE
README.md
legged_gym/AGENTS.md
legged_gym/__init__.py
legged_gym/envs/AGENTS.md
legged_gym/envs/__init__.py
legged_gym/envs/base/base_config.py
legged_gym/envs/base/base_task.py
legged_gym/envs/base/common_cfgs.py
legged_gym/envs/base/legged_robot.py
legged_gym/envs/base/legged_robot_amp.py
legged_gym/envs/base/legged_robot_config.py
legged_gym/envs/base/legged_robot_cts.py
legged_gym/envs/base/legged_robot_dreamwaq.py
legged_gym/envs/base/legged_robot_ee.py
legged_gym/envs/base/legged_robot_nav.py
legged_gym/envs/base/legged_robot_nav_config.py
legged_gym/envs/base/legged_robot_ts.py
legged_gym/envs/base/legged_robot_ts_depth.py
legged_gym/envs/base/template_cfgs.py
legged_gym/envs/bipedal_walker/bipedal_walker.py
legged_gym/envs/bipedal_walker/bipedal_walker_config.py
legged_gym/envs/g1/__init__.py
legged_gym/envs/g1/g1.py
legged_gym/envs/g1/g1_config.py
legged_gym/envs/g1/g1_deepmimic/g1_deepmimic.py
legged_gym/envs/g1/g1_deepmimic/g1_deepmimic_config.py
legged_gym/envs/g1/g1_motion_vis/g1_motion_vis.py
legged_gym/envs/g1/g1_motion_vis/g1_motion_vis_config.py
legged_gym/envs/go2/go2.py
legged_gym/envs/go2/go2_cat/go2_cat.py
legged_gym/envs/go2/go2_cat/go2_cat_config.py
legged_gym/envs/go2/go2_config.py
legged_gym/envs/go2/go2_cts/go2_cts.py
legged_gym/envs/go2/go2_cts/go2_cts_config.py
legged_gym/envs/go2/go2_dreamwaq/go2_dreamwaq.py
legged_gym/envs/go2/go2_dreamwaq/go2_dreamwaq_config.py
legged_gym/envs/go2/go2_ee/go2_ee.py
legged_gym/envs/go2/go2_ee/go2_ee_config.py
legged_gym/envs/go2/go2_nav/go2_nav.py
legged_gym/envs/go2/go2_nav/go2_nav_config.py
legged_gym/envs/go2/go2_sysid/go2_sysid.py
legged_gym/envs/go2/go2_sysid/go2_sysid_config.py
legged_gym/envs/go2/go2_ts/go2_ts.py
legged_gym/envs/go2/go2_ts/go2_ts_config.py
legged_gym/envs/go2/go2_ts_depth/go2_ts_depth.py
legged_gym/envs/go2/go2_ts_depth/go2_ts_depth_config.py
legged_gym/envs/go2/go2_wtw/go2_wtw.py
legged_gym/envs/go2/go2_wtw/go2_wtw_config.py
legged_gym/envs/k1/k1.py
legged_gym/envs/k1/k1_amp/k1_amp.py
legged_gym/envs/k1/k1_amp/k1_amp_config.py
legged_gym/envs/k1/k1_config.py
legged_gym/envs/k1/k1_cts_amp/k1_cts_amp.py
legged_gym/envs/k1/k1_cts_amp/k1_cts_amp_config.py
legged_gym/envs/k1/k1_deepmimic/k1_deepmimic.py
legged_gym/envs/k1/k1_deepmimic/k1_deepmimic_config.py
legged_gym/envs/k1/k1_motion_vis/k1_motion_vis.py
legged_gym/envs/k1/k1_motion_vis/k1_motion_vis_config.py
legged_gym/envs/tron1pf/tron1pf.py
legged_gym/envs/tron1pf/tron1pf_config.py
legged_gym/envs/tron1pf/tron1pf_ee/tron1pf_ee.py
legged_gym/envs/tron1pf/tron1pf_ee/tron1pf_ee_config.py
legged_gym/envs/tron1sf/tron1sf.py
legged_gym/envs/tron1sf/tron1sf_config.py
legged_gym/scripts/constraint/evaluate_violation_cat.py
legged_gym/scripts/constraint/evaluate_violation_ts.py
legged_gym/scripts/constraint/violation_comparison.txt
legged_gym/scripts/joystick.py
legged_gym/scripts/play.py
legged_gym/scripts/process_reference_motion.py
legged_gym/scripts/sysid/run_go2_sysid.py
legged_gym/scripts/train.py
legged_gym/simulator/AGENTS.md
legged_gym/simulator/__init__.py
legged_gym/simulator/genesis_simulator.py
legged_gym/simulator/isaacgym_simulator.py
legged_gym/simulator/isaaclab_simulator.py
legged_gym/simulator/simulator.py
legged_gym/utils/__init__.py
legged_gym/utils/constraint_manager.py
legged_gym/utils/gs_utils.py
legged_gym/utils/helpers.py
legged_gym/utils/logger.py
legged_gym/utils/math_utils.py
legged_gym/utils/motion_loader.py
legged_gym/utils/task_registry.py
legged_gym/utils/terrain.py
legged_gym/utils/terrain_utils.py
legged_gym/utils/viser_viewer.py
legged_gym/warp/warp_cam.py
legged_gym/warp/warp_kernels/warp_camera_kernels.py
pyproject.toml
resources/reference_motion/booster_k1/genesis_run/C11_-_run_turn_left_90_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C12_-_run_turn_left_45_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C13_-_run_turn_left_135_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C14_-_run_turn_right_90_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C15_-_run_turn_right_45_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C16_-_run_turn_right_135_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C17_-_run_change_direction_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C1_-_stand_to_run_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C3_-_run_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C6_-_stand_to_run_backwards_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C7_-_run_backwards_t2_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C8_-_run_backwards_to_stand_stageii_genesis.pkl
resources/reference_motion/booster_k1/genesis_run/C9_-_run_backwards_turn_run_forward_stageii_genesis.pkl
resources/reference_motion/booster_k1/isaacgym_run/B22_-__side_step_left_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/B23_-__side_step_right_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C11_-_run_turn_left_90_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C12_-_run_turn_left_45_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C13_-_run_turn_left_135_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C14_-_run_turn_right_90_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C15_-_run_turn_right_45_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C16_-_run_turn_right_135_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C17_-_run_change_direction_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C1_-_stand_to_run_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C3_-_run_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C6_-_stand_to_run_backwards_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C7_-_run_backwards_t2_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C8_-_run_backwards_to_stand_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaacgym_run/C9_-_run_backwards_turn_run_forward_stageii_isaacgym.pkl
resources/reference_motion/booster_k1/isaaclab_run/C11_-_run_turn_left_90_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C12_-_run_turn_left_45_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C13_-_run_turn_left_135_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C14_-_run_turn_right_90_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C15_-_run_turn_right_45_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C16_-_run_turn_right_135_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C17_-_run_change_direction_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C1_-_stand_to_run_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C3_-_run_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C6_-_stand_to_run_backwards_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C7_-_run_backwards_t2_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C8_-_run_backwards_to_stand_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/isaaclab_run/C9_-_run_backwards_turn_run_forward_stageii_isaaclab.pkl
resources/reference_motion/booster_k1/raw_run/C11_-_run_turn_left_90_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C12_-_run_turn_left_45_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C13_-_run_turn_left_135_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C14_-_run_turn_right_90_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C15_-_run_turn_right_45_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C16_-_run_turn_right_135_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C17_-_run_change_direction_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C1_-_stand_to_run_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C3_-_run_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C6_-_stand_to_run_backwards_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C7_-_run_backwards_t2_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C8_-_run_backwards_to_stand_stageii.pkl
resources/reference_motion/booster_k1/raw_run/C9_-_run_backwards_turn_run_forward_stageii.pkl
resources/reference_motion/unitree_g1/genesis_run/B22_-__side_step_left_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/B23_-__side_step_right_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C11_-_run_turn_left_90_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C12_-_run_turn_left_45_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C13_-_run_turn_left_135_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C14_-_run_turn_right_90_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C15_-_run_turn_right_45_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C16_-_run_turn_right_135_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C17_-_run_change_direction_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C1_-_stand_to_run_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C3_-_run_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C6_-_stand_to_run_backwards_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C7_-_run_backwards_t2_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C8_-_run_backwards_to_stand_stageii_genesis.pkl
resources/reference_motion/unitree_g1/genesis_run/C9_-_run_backwards_turn_run_forward_stageii_genesis.pkl
resources/reference_motion/unitree_g1/isaacgym_run/B22_-__side_step_left_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/B23_-__side_step_right_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C11_-_run_turn_left_90_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C12_-_run_turn_left_45_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C13_-_run_turn_left_135_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C14_-_run_turn_right_90_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C15_-_run_turn_right_45_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C16_-_run_turn_right_135_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C17_-_run_change_direction_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C1_-_stand_to_run_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C3_-_run_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C6_-_stand_to_run_backwards_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C7_-_run_backwards_t2_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C8_-_run_backwards_to_stand_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaacgym_run/C9_-_run_backwards_turn_run_forward_stageii_isaacgym.pkl
resources/reference_motion/unitree_g1/isaaclab_run/B22_-__side_step_left_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/B23_-__side_step_right_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C11_-_run_turn_left_90_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C12_-_run_turn_left_45_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C13_-_run_turn_left_135_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C14_-_run_turn_right_90_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C15_-_run_turn_right_45_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C16_-_run_turn_right_135_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C17_-_run_change_direction_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C1_-_stand_to_run_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C3_-_run_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C6_-_stand_to_run_backwards_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C7_-_run_backwards_t2_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C8_-_run_backwards_to_stand_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/isaaclab_run/C9_-_run_backwards_turn_run_forward_stageii_isaaclab.pkl
resources/reference_motion/unitree_g1/raw_run/B22_-__side_step_left_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/B23_-__side_step_right_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C11_-_run_turn_left_90_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C12_-_run_turn_left_45_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C13_-_run_turn_left_135_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C14_-_run_turn_right_90_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C15_-_run_turn_right_45_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C16_-_run_turn_right_135_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C17_-_run_change_direction_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C1_-_stand_to_run_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C3_-_run_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C6_-_stand_to_run_backwards_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C7_-_run_backwards_t2_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C8_-_run_backwards_to_stand_stageii.pkl
resources/reference_motion/unitree_g1/raw_run/C9_-_run_backwards_turn_run_forward_stageii.pkl
resources/robots/bipedal_walker/urdf/walker3d_hip3d.urdf
resources/robots/booster_robotics/K1/K1_22dof-ZED.urdf
resources/robots/booster_robotics/K1/K1_22dof.urdf
resources/robots/booster_robotics/K1/K1_22dof.xml
resources/robots/booster_robotics/K1/K1_locomotion.urdf
resources/robots/booster_robotics/K1/k1_lab_cfg.py
resources/robots/limx_dynamics/PF_TRON1A/urdf/robot.urdf
resources/robots/limx_dynamics/PF_TRON1A/xml/robot.xml
resources/robots/limx_dynamics/SF_TRON1A/urdf/robot.urdf
resources/robots/limx_dynamics/SF_TRON1A/xml/robot.xml
resources/robots/unitree_robotics/g1_description/README.md
resources/robots/unitree_robotics/g1_description/g1_12dof.urdf
resources/robots/unitree_robotics/g1_description/g1_12dof.xml
resources/robots/unitree_robotics/g1_description/g1_23dof.urdf
resources/robots/unitree_robotics/g1_description/g1_23dof.xml
resources/robots/unitree_robotics/g1_description/g1_23dof_rev_1_0.urdf
resources/robots/unitree_robotics/g1_description/g1_23dof_rev_1_0.xml
resources/robots/unitree_robotics/g1_description/g1_29dof.urdf
resources/robots/unitree_robotics/g1_description/g1_29dof.xml
resources/robots/unitree_robotics/g1_description/g1_29dof_lock_waist.urdf
resources/robots/unitree_robotics/g1_description/g1_29dof_lock_waist.xml
resources/robots/unitree_robotics/g1_description/g1_29dof_lock_waist_rev_1_0.urdf
resources/robots/unitree_robotics/g1_description/g1_29dof_lock_waist_rev_1_0.xml
resources/robots/unitree_robotics/g1_description/g1_29dof_rev_1_0.urdf
resources/robots/unitree_robotics/g1_description/g1_29dof_rev_1_0.xml
resources/robots/unitree_robotics/g1_description/g1_29dof_with_hand.urdf
resources/robots/unitree_robotics/g1_description/g1_29dof_with_hand.xml
resources/robots/unitree_robotics/g1_description/g1_29dof_with_hand_rev_1_0.urdf
resources/robots/unitree_robotics/g1_description/g1_29dof_with_hand_rev_1_0.xml
resources/robots/unitree_robotics/g1_description/g1_dual_arm.urdf
resources/robots/unitree_robotics/g1_description/g1_dual_arm.xml
resources/robots/unitree_robotics/g1_description/g1_lab_cfg.py
resources/robots/unitree_robotics/g1_description/scene.xml
resources/robots/unitree_robotics/go2/go2.xml
resources/robots/unitree_robotics/go2/go2_lab_cfg.py
resources/robots/unitree_robotics/go2/urdf/.asset_hash
resources/robots/unitree_robotics/go2/urdf/go2.urdf
resources/sysid/20250617_motor_response_real_200Hz.csv
resources/terrains/plane.urdf
rsl_rl/AGENTS.md
rsl_rl/__init__.py
rsl_rl/algorithms/__init__.py
rsl_rl/algorithms/base_algorithm.py
rsl_rl/algorithms/ppo.py
rsl_rl/algorithms/ppo_amp.py
rsl_rl/algorithms/ppo_cts.py
rsl_rl/algorithms/ppo_cts_amp.py
rsl_rl/algorithms/ppo_dreamwaq.py
rsl_rl/algorithms/ppo_ee.py
rsl_rl/algorithms/ppo_ts.py
rsl_rl/algorithms/ppo_ts_depth.py
rsl_rl/env/__init__.py
rsl_rl/env/vec_env.py
rsl_rl/modules/__init__.py
rsl_rl/modules/actor_critic.py
rsl_rl/modules/actor_critic_cts.py
rsl_rl/modules/actor_critic_dreamwaq.py
rsl_rl/modules/actor_critic_ee.py
rsl_rl/modules/actor_critic_recurrent.py
rsl_rl/modules/actor_critic_ts.py
rsl_rl/modules/actor_critic_ts_depth.py
rsl_rl/modules/amp_discriminator.py
rsl_rl/modules/depth_history_encoder.py
rsl_rl/modules/vae.py
rsl_rl/runners/__init__.py
rsl_rl/runners/amp_runner.py
rsl_rl/runners/cts_amp_runner.py
rsl_rl/runners/cts_runner.py
rsl_rl/runners/dreamwaq_runner.py
rsl_rl/runners/ee_runner.py
rsl_rl/runners/on_policy_runner.py
rsl_rl/runners/ts_depth_runner.py
rsl_rl/runners/ts_runner.py
rsl_rl/storage/__init__.py
rsl_rl/storage/replay_buffer.py
rsl_rl/storage/rollout_storage.py
rsl_rl/storage/rollout_storage_cts.py
rsl_rl/storage/rollout_storage_dreamwaq.py
rsl_rl/storage/rollout_storage_ee.py
rsl_rl/storage/rollout_storage_ts.py
rsl_rl/storage/rollout_storage_ts_depth.py
rsl_rl/utils/__init__.py
rsl_rl/utils/runner_registry.py
rsl_rl/utils/symmetry.py
rsl_rl/utils/symmetry_cts.py
rsl_rl/utils/utils.py
switch_simulator.sh
tests/_test_single_task.py
tests/test_all_simulators.sh
tests/test_all_tasks.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.torch_extensions/gymtorch` | 2 | 3.3 MB | [`.torch_extensions/gymtorch/_OMITTED.md`](./.torch_extensions/gymtorch/_OMITTED.md) |
| `legged_gym/scripts` | 1 | 232 KB | [`legged_gym/scripts/_OMITTED.md`](./legged_gym/scripts/_OMITTED.md) |
| `resources/robots/booster_robotics/K1/meshes` | 52 | 20.6 MB | [`resources/robots/booster_robotics/K1/meshes/_OMITTED.md`](./resources/robots/booster_robotics/K1/meshes/_OMITTED.md) |
| `resources/robots/limx_dynamics/PF_TRON1A/meshes` | 9 | 17.1 MB | [`resources/robots/limx_dynamics/PF_TRON1A/meshes/_OMITTED.md`](./resources/robots/limx_dynamics/PF_TRON1A/meshes/_OMITTED.md) |
| `resources/robots/limx_dynamics/SF_TRON1A/meshes` | 9 | 18.6 MB | [`resources/robots/limx_dynamics/SF_TRON1A/meshes/_OMITTED.md`](./resources/robots/limx_dynamics/SF_TRON1A/meshes/_OMITTED.md) |
| `resources/robots/unitree_robotics/g1_description/images` | 4 | 3.5 MB | [`resources/robots/unitree_robotics/g1_description/images/_OMITTED.md`](./resources/robots/unitree_robotics/g1_description/images/_OMITTED.md) |
| `resources/robots/unitree_robotics/g1_description/meshes` | 64 | 51.8 MB | [`resources/robots/unitree_robotics/g1_description/meshes/_OMITTED.md`](./resources/robots/unitree_robotics/g1_description/meshes/_OMITTED.md) |
| `resources/robots/unitree_robotics/go2/meshes` | 7 | 987 KB | [`resources/robots/unitree_robotics/go2/meshes/_OMITTED.md`](./resources/robots/unitree_robotics/go2/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
