# humanoid-motion-planning — 参考资源

> **来源**：`00_open/humanoid-motion-planning/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：人形运动规划算法
> **收录**：50 个文件 / 460 KB（其中推理策略/模型文件 0 个）
> **已省略**：48 个文件 / 27.5 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（1 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **部署与推理**（1 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（16 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（1 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（30 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （6 个文件）
results/  （2 个文件）
    (直接文件)/
src/  （42 个文件）
    (直接文件)/
    locomotion/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 44 |
| `.md` | 3 |
| `(无扩展名)` | 1 |
| `.txt` | 1 |
| `.json` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
MUJOCO_LOG.TXT
README.md
RESULTS.md
advanced_demo.py
demo.py
results/FINAL_SUMMARY.md
results/results.json
src/__init__.py
src/autonomous_demo.py
src/collision_checker.py
src/dramatic_demo.py
src/dynamic_zmp.py
src/final_demo.py
src/footstep_planner.py
src/full_demo.py
src/full_visualization.py
src/g1_model.py
src/integrated_demo.py
src/inverse_kinematics.py
src/live_demo.py
src/locomotion/continue_training.py
src/locomotion/eval_rl.py
src/locomotion/g1_analysis.py
src/locomotion/g1_config.py
src/locomotion/g1_controller.py
src/locomotion/g1_walker.py
src/locomotion/main_walk.py
src/locomotion/run_unitree_policy.py
src/locomotion/simple_walker.py
src/locomotion/train_fresh.py
src/locomotion/train_rl_walking.py
src/locomotion/train_walking.py
src/locomotion/walking_controller.py
src/manipulation_scene.py
src/motion_planner.py
src/mpc_balance.py
src/perception.py
src/showcase_demo.py
src/test_zmp_benefit.py
src/trajectory_optimizer.py
src/video_recorder.py
src/visualizer.py
src/walk_and_reach.py
src/walking_controller.py
src/walking_stability_demo.py
src/whole_body_motion_planner.py
src/working_demo.py
src/zmp_calculator.py
src/zmp_preview_control.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 34 | 6.8 MB | [`_OMITTED.md`](./_OMITTED.md) |
| `models` | 1 | 489 KB | [`models/_OMITTED.md`](./models/_OMITTED.md) |
| `results` | 13 | 20.3 MB | [`results/_OMITTED.md`](./results/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
