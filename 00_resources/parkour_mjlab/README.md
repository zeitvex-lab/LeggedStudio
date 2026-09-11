# parkour_mjlab — 参考资源

> **来源**：`00_open/parkour_mjlab/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_g1（宇树 G1 人形）
> **定位**：Go2/G1 的 parkour 任务（mjlab）：Go2 PIE 深度跑酷训练 + sim2sim + 发布策略
> **收录**：65 个文件 / 32.6 MB（其中推理策略/模型文件 5 个）
> **已省略**：88 个文件 / 77.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（7 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（12 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（25 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（10 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **文档与其它**（11 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
deploy/  （31 个文件）
    (直接文件)/
    parkour/
    pie/
    stair/
logs/  （3 个文件）
    rsl_rl/
scripts/  （3 个文件）
    (直接文件)/
src/  （25 个文件）
    (直接文件)/
    assets/
    tasks/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 46 |
| `.xml` | 7 |
| `.onnx` | 4 |
| `(无扩展名)` | 3 |
| `.md` | 3 |
| `.pt` | 1 |
| `.txt` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
README.md
deploy/__init__.py
deploy/parkour/sim2sim/__init__.py
deploy/parkour/sim2sim/__main__.py
deploy/parkour/sim2sim/assets/ASSETS.md
deploy/parkour/sim2sim/assets/policies/amp_policy.onnx
deploy/parkour/sim2sim/assets/policies/student_policy_v6_model_10000.onnx
deploy/parkour/sim2sim/assets/scene_parkour.xml
deploy/parkour/sim2sim/assets/unitree_g1/LICENSE
deploy/parkour/sim2sim/assets/unitree_g1/g1_29dof_spherehand.xml
deploy/parkour/sim2sim/course.py
deploy/parkour/sim2sim/policy_runtime.py
deploy/parkour/sim2sim/requirements.txt
deploy/parkour/sim2sim/run_mujoco.py
deploy/parkour/sim2sim/simulator.py
deploy/pie/__init__.py
deploy/pie/sim2sim/__init__.py
deploy/pie/sim2sim/assets/scene_stairs.xml
deploy/pie/sim2sim/contract.py
deploy/pie/sim2sim/gamepad.py
deploy/pie/sim2sim/go2_pie_sim2sim.py
deploy/pie/sim2sim/policy_runtime.py
deploy/stair/__init__.py
deploy/stair/sim2sim/__init__.py
deploy/stair/sim2sim/assets/unitree_g1/ASSET_SOURCE.md
deploy/stair/sim2sim/assets/unitree_g1/LICENSE
deploy/stair/sim2sim/assets/unitree_g1/g1_29dof.xml
deploy/stair/sim2sim/assets/unitree_g1/scene_stair.xml
deploy/stair/sim2sim/g1_stair_unitree_mujoco.py
deploy/stair/sim2sim/policy_runtime.py
deploy/stair/sim2sim/sdk2_depth_codec.py
deploy/stair/sim2sim/unitree_mujoco_stair_server.py
logs/rsl_rl/g1_stair/stair_test/policy.onnx
logs/rsl_rl/go2_pie/model_8000.pt
logs/rsl_rl/go2_pie/policy.onnx
scripts/list_envs.py
scripts/play.py
scripts/train.py
setup.py
src/__init__.py
src/assets/__init__.py
src/assets/robots/__init__.py
src/assets/robots/unitree_go2/__init__.py
src/assets/robots/unitree_go2/go2_constants.py
src/assets/robots/unitree_go2/xmls/go2.xml
src/assets/robots/unitree_go2/xmls/scene_go2.xml
src/tasks/__init__.py
src/tasks/pie/__init__.py
src/tasks/pie/config/__init__.py
src/tasks/pie/config/go2/__init__.py
src/tasks/pie/config/go2/env_cfgs.py
src/tasks/pie/config/go2/rl_cfg.py
src/tasks/pie/mdp/__init__.py
src/tasks/pie/mdp/curriculums.py
src/tasks/pie/mdp/observations.py
src/tasks/pie/mdp/rewards.py
src/tasks/pie/mdp/terminations.py
src/tasks/pie/mdp/velocity_command.py
src/tasks/pie/rl/__init__.py
src/tasks/pie/rl/config.py
src/tasks/pie/rl/pie_model.py
src/tasks/pie/rl/ppo.py
src/tasks/pie/rl/runner.py
src/tasks/pie/terrains.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `deploy/parkour/sim2sim/assets/terrains/climb_15/box_models` | 1 | 431 B | [`deploy/parkour/sim2sim/assets/terrains/climb_15/box_models/_OMITTED.md`](./deploy/parkour/sim2sim/assets/terrains/climb_15/box_models/_OMITTED.md) |
| `deploy/parkour/sim2sim/assets/unitree_g1/assets` | 34 | 18.2 MB | [`deploy/parkour/sim2sim/assets/unitree_g1/assets/_OMITTED.md`](./deploy/parkour/sim2sim/assets/unitree_g1/assets/_OMITTED.md) |
| `deploy/stair/sim2sim/assets/unitree_g1/meshes` | 36 | 17.7 MB | [`deploy/stair/sim2sim/assets/unitree_g1/meshes/_OMITTED.md`](./deploy/stair/sim2sim/assets/unitree_g1/meshes/_OMITTED.md) |
| `docs` | 1 | 14.1 MB | [`docs/_OMITTED.md`](./docs/_OMITTED.md) |
| `src/assets/robots/unitree_go2/xmls/assets` | 16 | 27.1 MB | [`src/assets/robots/unitree_go2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_go2/xmls/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
