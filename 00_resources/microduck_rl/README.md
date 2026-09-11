# microduck_rl — 参考资源

> **来源**：`00_open/microduck_rl/`　｜　**类型**：参考项目
> **关联机型**：microduck（MicroDuck 双足）
> **定位**：MicroDuck RL 训练
> **收录**：176 个文件 / 1.8 MB（其中推理策略/模型文件 0 个）
> **已省略**：55 个文件 / 23.5 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（62 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（25 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（6 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（1 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（33 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（48 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （6 个文件）
docs/  （16 个文件）
    (直接文件)/
    superpowers/
scripts/  （12 个文件）
    (直接文件)/
    hf/
src/  （122 个文件）
    mjlab_microduck/
tests/  （20 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 67 |
| `.part` | 54 |
| `.xml` | 24 |
| `.md` | 20 |
| `.json` | 8 |
| `(无扩展名)` | 2 |
| `.toml` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
AGENTS.md
CLAUDE.md
LICENSE
README.md
docs/roller_standup_policy_summary.md
docs/superpowers/plans/2026-07-17-roller-crouch-glide.md
docs/superpowers/plans/2026-07-22-roller-slope.md
docs/superpowers/plans/2026-07-24-ground-pick-pose-following.md
docs/superpowers/plans/2026-07-24-shoot-pose-following.md
docs/superpowers/plans/2026-07-27-swizzle-head-control.md
docs/superpowers/plans/2026-08-04-roller-standup.md
docs/superpowers/plans/2026-08-04-spin-env.md
docs/superpowers/specs/2026-07-17-roller-crouch-glide-design.md
docs/superpowers/specs/2026-07-22-roller-slope-design.md
docs/superpowers/specs/2026-07-23-swizzle-env-design.md
docs/superpowers/specs/2026-07-24-ground-pick-pose-following-design.md
docs/superpowers/specs/2026-07-24-shoot-pose-following-design.md
docs/superpowers/specs/2026-07-27-swizzle-head-control-design.md
docs/superpowers/specs/2026-08-04-roller-standup-design.md
docs/superpowers/specs/2026-08-04-spin-env-design.md
pyproject.toml
scripts/crouch_pose_editor.py
scripts/export.py
scripts/hf/README.md
scripts/hf/train_hf.py
scripts/hf/uploader.py
scripts/infer_policy.py
scripts/play_latest.py
scripts/plot_observations_comparison_plotly.py
scripts/testbench_sim2real.py
scripts/validate_bam_testbench.py
scripts/view_slope_terrain.py
scripts/wandb_utils.py
src/mjlab_microduck/__init__.py
src/mjlab_microduck/actuator/__init__.py
src/mjlab_microduck/actuator/friction_dr_bam.py
src/mjlab_microduck/export.py
src/mjlab_microduck/hf_jobs.py
src/mjlab_microduck/publish/__init__.py
src/mjlab_microduck/publish/cli.py
src/mjlab_microduck/publish/manifest.py
src/mjlab_microduck/robot/__init__.py
src/mjlab_microduck/robot/microduck/add_backlash.py
src/mjlab_microduck/robot/microduck/additional.xml
src/mjlab_microduck/robot/microduck/allcollisions_contacts.xml
src/mjlab_microduck/robot/microduck/apartment.xml
src/mjlab_microduck/robot/microduck/assets/ankle_l_v1.part
src/mjlab_microduck/robot/microduck/assets/ankle_left.part
src/mjlab_microduck/robot/microduck/assets/ankle_r_v1.part
src/mjlab_microduck/robot/microduck/assets/ankle_right.part
src/mjlab_microduck/robot/microduck/assets/banana_pcb_locker.part
src/mjlab_microduck/robot/microduck/assets/bearing_roll.part
src/mjlab_microduck/robot/microduck/assets/bottom_head_shell.part
src/mjlab_microduck/robot/microduck/assets/elec_rpi_robot_hat_pcb.part
src/mjlab_microduck/robot/microduck/assets/face_part.part
src/mjlab_microduck/robot/microduck/assets/foot_left.part
src/mjlab_microduck/robot/microduck/assets/foot_right.part
src/mjlab_microduck/robot/microduck/assets/hip_l.part
src/mjlab_microduck/robot/microduck/assets/jaw.part
src/mjlab_microduck/robot/microduck/assets/jaw_soft.part
src/mjlab_microduck/robot/microduck/assets/left_shell.part
src/mjlab_microduck/robot/microduck/assets/leg.part
src/mjlab_microduck/robot/microduck/assets/lens.part
src/mjlab_microduck/robot/microduck/assets/m12_lens_holder.part
src/mjlab_microduck/robot/microduck/assets/motor_support.part
src/mjlab_microduck/robot/microduck/assets/neck.part
src/mjlab_microduck/robot/microduck/assets/neck_pitch.part
src/mjlab_microduck/robot/microduck/assets/noenoeil.part
src/mjlab_microduck/robot/microduck/assets/np_f970.part
src/mjlab_microduck/robot/microduck/assets/pcb__raspberry_pi_zero_2_w.part
src/mjlab_microduck/robot/microduck/assets/power_support.part
src/mjlab_microduck/robot/microduck/assets/right_shell.part
src/mjlab_microduck/robot/microduck/assets/rim.part
src/mjlab_microduck/robot/microduck/assets/roller_blade.part
src/mjlab_microduck/robot/microduck/assets/seeed_bearing__configuration__22x16x4.part
src/mjlab_microduck/robot/microduck/assets/seeed_bearing__configuration_default.part
src/mjlab_microduck/robot/microduck/assets/soft_mouth_top.part
src/mjlab_microduck/robot/microduck/assets/sole_left.part
src/mjlab_microduck/robot/microduck/assets/sole_right.part
src/mjlab_microduck/robot/microduck/assets/speaker.part
src/mjlab_microduck/robot/microduck/assets/tire.part
src/mjlab_microduck/robot/microduck/assets/top_head_shell.part
src/mjlab_microduck/robot/microduck/assets/trunk_base.part
src/mjlab_microduck/robot/microduck/assets/upper_leg_left.part
src/mjlab_microduck/robot/microduck/assets/upper_leg_right.part
src/mjlab_microduck/robot/microduck/assets/upper_leg_rigidity_plate.part
src/mjlab_microduck/robot/microduck/assets/xl330.part
src/mjlab_microduck/robot/microduck/assets/yaw2roll.part
src/mjlab_microduck/robot/microduck/assets/yaw_roll_motion.part
src/mjlab_microduck/robot/microduck/ball.xml
src/mjlab_microduck/robot/microduck/config_mjcf_allcollisions.json
src/mjlab_microduck/robot/microduck/config_mjcf_groundcontact.json
src/mjlab_microduck/robot/microduck/config_mjcf_groundcontact_backlash.json
src/mjlab_microduck/robot/microduck/config_mjcf_groundcontact_rollers.json
src/mjlab_microduck/robot/microduck/config_mjcf_groundcontact_rollers_backlash.json
src/mjlab_microduck/robot/microduck/config_mjcf_walk.json
src/mjlab_microduck/robot/microduck/config_mjcf_walk_backlash.json
src/mjlab_microduck/robot/microduck/joints_properties.xml
src/mjlab_microduck/robot/microduck/robot_allcollisions.xml
src/mjlab_microduck/robot/microduck/robot_groundcontact.xml
src/mjlab_microduck/robot/microduck/robot_groundcontact_backlash.xml
src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml
src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers_backlash.xml
src/mjlab_microduck/robot/microduck/robot_walk.xml
src/mjlab_microduck/robot/microduck/robot_walk_backlash.xml
src/mjlab_microduck/robot/microduck/scene.xml
src/mjlab_microduck/robot/microduck/scene_allcollisions.xml
src/mjlab_microduck/robot/microduck/scene_apartment.xml
src/mjlab_microduck/robot/microduck/scene_backlash.xml
src/mjlab_microduck/robot/microduck/scene_ball.xml
src/mjlab_microduck/robot/microduck/scene_rollers.xml
src/mjlab_microduck/robot/microduck/scene_walk.xml
src/mjlab_microduck/robot/microduck/scene_walk_backlash.xml
src/mjlab_microduck/robot/microduck/sensors.xml
src/mjlab_microduck/robot/microduck_constants.py
src/mjlab_microduck/robot/testbench_constants.py
src/mjlab_microduck/robot/xl330_test_bench/assets/arm.part
src/mjlab_microduck/robot/xl330_test_bench/assets/axis.part
src/mjlab_microduck/robot/xl330_test_bench/assets/bench_holder.part
src/mjlab_microduck/robot/xl330_test_bench/assets/part_1.part
src/mjlab_microduck/robot/xl330_test_bench/assets/part_2.part
src/mjlab_microduck/robot/xl330_test_bench/assets/part_3.part
src/mjlab_microduck/robot/xl330_test_bench/assets/part_4.part
src/mjlab_microduck/robot/xl330_test_bench/assets/part_5.part
src/mjlab_microduck/robot/xl330_test_bench/assets/spacer.part
src/mjlab_microduck/robot/xl330_test_bench/assets/weight.part
src/mjlab_microduck/robot/xl330_test_bench/assets/xl330.part
src/mjlab_microduck/robot/xl330_test_bench/config.json
src/mjlab_microduck/robot/xl330_test_bench/joints_properties.xml
src/mjlab_microduck/robot/xl330_test_bench/scene.xml
src/mjlab_microduck/robot/xl330_test_bench/xl330_test_bench.xml
src/mjlab_microduck/sim/__init__.py
src/mjlab_microduck/sim/body_server.py
src/mjlab_microduck/sim/tof.py
src/mjlab_microduck/tasks/__init__.py
src/mjlab_microduck/tasks/backlash.py
src/mjlab_microduck/tasks/mdp.py
src/mjlab_microduck/tasks/microduck_ball_kick_env_cfg.py
src/mjlab_microduck/tasks/microduck_ground_pick_env_cfg.py
src/mjlab_microduck/tasks/microduck_roller_crouch_env_cfg.py
src/mjlab_microduck/tasks/microduck_roller_slope_env_cfg.py
src/mjlab_microduck/tasks/microduck_roller_standup_env_cfg.py
src/mjlab_microduck/tasks/microduck_roulade_env_cfg.py
src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py
src/mjlab_microduck/tasks/microduck_spin_env_cfg.py
src/mjlab_microduck/tasks/microduck_standup_env_cfg.py
src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py
src/mjlab_microduck/tasks/microduck_velocity_rollers_env_cfg.py
src/mjlab_microduck/tasks/microduck_velocity_swizzle_env_cfg.py
src/mjlab_microduck/tasks/microduck_velstand_env_cfg.py
src/mjlab_microduck/tasks/slope_terrain.py
src/mjlab_microduck/tasks/symmetry.py
src/mjlab_microduck/tasks/testbench_env_cfg.py
src/mjlab_microduck/train_cli.py
src/mjlab_microduck/train_hook.py
tests/test_aarch64_cuda_torch.py
tests/test_crouch_glide.py
tests/test_descent_speed.py
tests/test_ground_pick_cfg.py
tests/test_ground_pick_pose.py
tests/test_head_pose_bias.py
tests/test_hf_jobs_flag.py
tests/test_infer_policy_bam.py
tests/test_nan_guard.py
tests/test_obs_nan_guard.py
tests/test_publish_manifest.py
tests/test_roller_crouch_cfg.py
tests/test_roller_slope_cfg.py
tests/test_roller_standup_cfg.py
tests/test_slope_curriculum.py
tests/test_slope_terrain.py
tests/test_spin.py
tests/test_spin_cfg.py
tests/test_swizzle_head_cfg.py
tests/test_wheel_glide.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 238 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `src/mjlab_microduck/robot/microduck/assets` | 43 | 22.5 MB | [`src/mjlab_microduck/robot/microduck/assets/_OMITTED.md`](./src/mjlab_microduck/robot/microduck/assets/_OMITTED.md) |
| `src/mjlab_microduck/robot/xl330_test_bench/assets` | 11 | 756 KB | [`src/mjlab_microduck/robot/xl330_test_bench/assets/_OMITTED.md`](./src/mjlab_microduck/robot/xl330_test_bench/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
