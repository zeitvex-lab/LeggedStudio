# matrix_zsibot — 参考资源

> **来源**：`00_open/matrix_zsibot/`　｜　**类型**：仿真平台参考（场景 / 感知 / 资产流水线）
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_g1（宇树 G1 人形）
> **定位**：ZsiBot MATRiX 仿真平台源码快照的实现类子集（UE5 + MuJoCo + CARLA）：传感器声明、自定义/拼接场景、多机器人端口、相机与渲染协议、实景扫描 3DGS→PLY→MuJoCo proxy 流水线、G1 材质桥
> **收录**：46 个文件 / 770 KB（其中推理策略/模型文件 0 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（8 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（6 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（1 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **评测与测试**（8 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（23 个）：文档、说明、许可与零散脚本

## 目录构成

```text
config/  （5 个文件）
    (直接文件)/
    materials/
docs/  （9 个文件）
    (直接文件)/
research/  （3 个文件）
    overworld_v1/
    sonic_integration/
    urban_v1/
rviz/  （1 个文件）
    (直接文件)/
scene/  （4 个文件）
    (直接文件)/
scripts/  （15 个文件）
    (直接文件)/
src/  （1 个文件）
    ue_shims/
tests/  （8 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 20 |
| `.json` | 12 |
| `.md` | 9 |
| `.sh` | 3 |
| `.rviz` | 1 |
| `.c` | 1 |

## 文件索引（项目内相对路径）

```text
config/config.json
config/materials/aue_g1_v1.json
config/materials/g1_skins.json
config/materials/matrix_g1_stock_v1.json
config/materials/matrix_g1_v2.json
docs/Custom_Robot_Tutorial.md
docs/Custom_Scene_Tutorial.md
docs/Custom_Scene_Tutorial_CN.md
docs/MATRIX_THIRD_PERSON_CAMERA_BRIDGE_CN.md
docs/Multi_Robot_Tutorial.md
docs/RoamerX_Lite_Integration.md
docs/Robots_and_Maps.md
docs/Sensor_Config_Tutorial.md
docs/pixelstreaming_tutorial.md
research/overworld_v1/layout.json
research/sonic_integration/native_scenes.json
research/urban_v1/scene.json
rviz/matrix.rviz
scene/scene.json
scene/scene_example_1.json
scene/scene_example_2.json
scene/scene_example_3.json
scripts/apply_urdf_visual_materials.py
scripts/build_realscan_mujoco_proxy.py
scripts/compose_custom_scene.py
scripts/compose_overworld_scene.py
scripts/convert_nurec_to_matrix_ply.py
scripts/create_realscan_scene_receipt.py
scripts/install_realscan_scene.py
scripts/matrix_moon_dynamic_ground.py
scripts/matrix_render_protocol.py
scripts/matrix_third_person_camera.py
scripts/matrix_ue_camera_probe.py
scripts/run_custom_urdf.sh
scripts/run_matrix_sonic.sh
scripts/run_sim.sh
scripts/validate_native_scene_inventory.py
src/ue_shims/matrix_ue_material_fix.c
tests/test_apply_urdf_visual_materials.py
tests/test_compose_custom_scene.py
tests/test_compose_overworld_scene.py
tests/test_matrix_moon_dynamic_ground.py
tests/test_matrix_render_protocol.py
tests/test_matrix_third_person_camera.py
tests/test_matrix_ue_camera_probe.py
tests/test_native_scene_inventory.py
```

## 导入边界（人工补充，重新同步时需重做）

- **源仓**：GitHub `amithyst/matrix`（ZsiBot MATRiX **0.1.2** 线的集成源码仓，BSD-3-Clause © ZsiBot）。
  本地只读克隆在 `amithyst-matrix/`（已 `.gitignore`）；本目录是其**白名单子集**，同步源路径写作 `00_open/matrix_zsibot/`。
- **只收「实现类」内容**：场景组合与拼接、传感器声明、多机器人端口、相机/渲染协议、实景扫描（3DGS/NuRec→PLY→MuJoCo proxy）流水线、G1 材质桥，
  以及覆盖它们的纯 Python 回归用例（**93 例**，本目录内零依赖可跑：`python -m unittest discover -s tests`）。
- **刻意不收**（上游存在但与本项目无关或含内部信息）：
  - 发布/部署/运维链路：`scripts/release_manager/`、`docs/runbook.md`、`docs/CHUNK_PACKAGES_GUIDE*.md`、`docs/Release_Automation.md`、上游 `README.md`、`config/hosts/*.env`、`config/runtime/matrix-sonic.lock.json`；
  - 私有运行时及其清单：`gear_sonic` / `GR00T-WholeBodyControl` 相关脚本与 lock（含私有 GitLab 地址）；
  - 媒体与归档：`demo_gif/`（131 MB）、`deps/*.deb`（47 MB）、`src/UeSim/` 与 `src/robot_mujoco/` 的占位/二进制。
  → 已核验：本目录**不含内网 Artifactory 地址与私有仓/私有主机引用**。
- **分类计数说明**：README 里「RL 训练工程 N 个」来自 `tools/sync_resources.py:classify()` 的**路径启发式**（`config` / `cfg` 等关键字），
  **不代表本目录含训练源码**——本目录没有任何训练工程（无 env_cfg / reward / curriculum / runner），也没有策略与模型（加密件在上游发行包里，未导入）。
- **与已有资源的互补**：本目录与 `00_resources/zsi_rl/matrix`（同版本线，文档为主）互补——那边是说明文档，这边是可运行的实现参考。
