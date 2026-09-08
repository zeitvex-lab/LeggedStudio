# g1_tracking — G1 动作跟踪任务（DeepMimic 风格）

基于 mjlab 1.6 管理式环境实现的 Unitree G1 全身动作跟踪（motion imitation）训练任务。
奖励族、参考动作数据与 RSI 初始化移植自 LeggedGym-Ex 的 `g1_deepmimic` 任务。

## 来源与许可

| 内容 | 来源 | 许可 |
| --- | --- | --- |
| 任务实现（奖励族 / RSI / 帧调度设计） | LeggedGym-Ex `legged_gym/envs/g1/g1_deepmimic/`（重写为 mjlab 管理式环境） | BSD-3-Clause |
| pkl MotionLoader 设计 | LeggedGym-Ex `legged_gym/utils/motion_loader.py`（重写） | BSD-3-Clause |
| 参考动作数据 `assets/motions/g1/tracking/*.pkl`（15 段，1.6 MB，取自 `isaacgym_run` 变体） | LeggedGym-Ex `resources/reference_motion/unitree_g1/isaacgym_run/` | BSD-3-Clause（仓库整体） |
| 机器人模型 / 任务基底 | mjlab 内置 `unitree_g1_flat_env_cfg`（mjlab 1.6，Apache-2.0） | Apache-2.0 |

LeggedGym-Ex 仓库 LICENSE 见其上游；参考动作 retarget 数据随仓库以 BSD-3-Clause 分发。

## 与上游（LeggedGym-Ex DeepMimic）的实现差异

1. **模拟器栈**：Isaac Gym / Isaac Lab → mjlab（MuJoCo + Warp）。
2. **四元数约定**：pkl `root_rot` 为 xyzw，加载时转换为 mjlab/MuJoCo 的 wxyz。
3. **帧调度**：上游每 env 独立帧指针在 `post_physics_step` 递增；本实现由
   `episode_length_buf` 驱动（RSI 时记录起始帧），奖励 / 观测共享同一确定性参考时钟。
4. **多段参考动作**：上游单任务单 pkl；本实现支持目录内全部 pkl（clip 拼接 +
   段内回绕，避免跨段跳变）。
5. **姿态误差**：`tracking_ref_base_pose` 的旋转误差改用带符号对齐的四元数角误差
   （`quat_error_magnitude`），避免 q / -q 双计数（上游为四元数逐分量平方差）。
6. **观测**：非逐位复刻上游 151 维观测；采用 mjlab velocity 风格本体感知 + 5 项
   参考动作特征（ref_dof_pos/vel、ref_base_quat、ref_base_lin/ang_vel_b）。
   actor 161 维、critic 176 维。
7. **RSI 概率**：保留上游 `reference_state_initialization_prob = 0.7`。

## 奖励（权重 = 上游 scale × 2）

| 项 | 权重 | sigma |
| --- | --- | --- |
| tracking_ref_dof_pos | 1.0 | 4.0 |
| tracking_ref_dof_vel | 0.2 | 100.0 |
| tracking_ref_base_pose | 1.0 | 0.2 |
| tracking_ref_base_vel | 0.2 | 1.0 |
| tracking_ref_key_pos | 0.3 | 0.1 |
| dof_pos_limits / action_rate_l2 / self_collisions / ang_vel_xy / joint_acc | -5.0 / -0.01 / -1.0 / -0.05 / -5e-8 | — |

## 关键身体顺序

pkl `key_body_pos_relative_to_base` 的 19 个身体顺序已通过 raw retarget 数据
数值核对（`KEY_BODY_NAMES`），与上游 `asset.key_bodies` 子串展开顺序一致。

## 入口

- env: `src.tasks.tracking.config.g1.env_cfgs:g1_tracking_flat_env_cfg`
- runner: `src.tasks.tracking.config.g1.rl_cfg:g1_tracking_ppo_runner_cfg`（标准 PPO）
- profile: `training/profiles/g1-tracking.json`
