# MATRiX v1.0.13 价值评估与提取记录

> **来源**：GitHub `zsibot/matrix` release `v1.0.13`（Linux 运行时发行包，三分卷 4,251,475,324 B）
> **许可**：文档/源码仓 `00_resources/zsi_rl/matrix` 为 BSD-3-Clause (ZsiBot)；**发行包内二进制、模型、地图 DLC 与第三方组件许可另行声明，再分发前必须逐项核实**
> **本地位置**：`matrix-v1.0.13/`（已加入 `.gitignore`，不入库）
> **核对日期**：2026-09-12　**核对方式**：解压实物 + MuJoCo 加载实测 + 容器分帧实测

---

## 1. 它是什么

MATRiX 是「UE5 渲染 + MuJoCo 物理 + Zenoh 数据传输」的高保真机器人仿真平台。本次拿到的是 **Linux 运行时发行包**（非源码）：

```text
MATRiX_v1.0.13/
├── UeSim.sh                     # 启动脚本，exec UeSim/Binaries/Linux/UeSim UeSim "$@"
├── UeSim/                       # 4.7G
│   ├── Binaries/Linux/          # UeSim 主程序 + libmujoco.so.3.3.0 / libzenohc.so / libonnxruntime.so.1
│   ├── Content/Paks/            # 1.5G（pakchunk0-Linux.pak 1.29G）
│   ├── Content/model/           # 485M：9 族机器人 MJCF + config/（传感器与主配置）
│   └── Plugins/                 # MatrixMotionControl / RobotSensorSimulation / MujocoSceneImporter
├── Engine/                      # UE5 引擎
├── Tools/                       # 10 个 Python 工具，5582 行
├── docs/                        # 15 篇文档，116KB
└── demo_gif/                    # 90M 演示素材
```

默认配置（`UeSim/Content/model/config/config.json`）：`mujoco_model=model/xgb/xgb.xml`、`inside_mc=true`（内置运控）、`network_mode=standalone`、`zenoh_router=tcp/0.0.0.0:7447`、`state_port=mujoco/state`、`cmd_port=mujoco/cmd`、`main_body=base_link`。

## 2. 实测结论

### 2.1 MJCF 模型：全部可用（实测通过）

用 `mujoco 3.11.0`（`/tmp/mjlab_cpu_venv`）逐个加载 + 200 步零力矩步进，14 个入口全部通过：

| 模型 | nq / nv / nu | nbody | 备注 |
|---|---|---:|---|
| `go2`（含 scene / auto_scene） | 19 / 18 / 12 | 18 | 与项目已有 Go2 资产重叠，可交叉校验 |
| `go2w` | 23 / 22 / 16 | 18 | 轮足 |
| `xgb`（发行默认，`<mujoco model="DOG">`） | 19 / 18 / 12 | 14 | 自研四足，ABAD/HIP/KNEE ×4 |
| `xg2` | 19 / 18 / 12 | 14 | 四足 |
| `xgw` / `xgw2` | 23 / 22 / 16 | 18 / 19 | 轮足 |
| `zgwt`（含 auto_scene） | 23 / 22 / 16 | 18 | 轮足 |
| `zgws` | 23 / 22 / 16 | 18 | 轮足，含月面地形变体 |
| `zgwsarm` | 29 / 28 / 22 | 24 | 轮足 + 6 轴机械臂（`ROBOT_ARM_JOINT1..6`） |

- `<compiler angle="radian" meshdir="assets/">` + STL 相对路径 → **整目录可搬迁**，可直接落进 `assets/`。
- MJCF 内 `<sensor>` 只有 `<jointpos>`（关节位置）；IMU / 相机 / 雷达全部由 UE 侧 `RobotSensorSimulation` 插件产生，**MuJoCo 只负责物理**。这与本项目「MJCF 物理 + 浏览器渲染」的分工不同。

### 2.2 UeSim 本体：本容器/CI 跑不起来

```text
$ ./UeSim.sh -windowed -ResX=640 -ResY=480
Refusing to run with the root privileges.
libc++abi: __cxa_guard_acquire detected recursive initialization
exit=134（核心转储）
```

环境侧事实：无 `/dev/dri`、无 `nvidia-smi`、无 `vulkaninfo`。**结论：必须 GPU 物理机/工作站，云开发容器与 CI 均不可运行**，因此它不能进入项目的自动验收链路。

### 2.3 内置运控模型：加密，不可复用

`UeSim/Plugins/MatrixMotionControl/Source/ThirdParty/MatrixMC/models/`：**165 个文件 / 952MB**，覆盖 7 族（xg 46、zg_wheels 40、xg_wheel 24、xg_wheel2 24、xg2 21、zgws_arm 5、xxg 4）。命名即动作库：

```text
crawl  stair  climb  jump  backflip  flipover  frontflip  sideflip  handstand
tuoluo  skwalk  snow  dsb  hload  slim  moonwalk  mimic        （policy_* / odom_* 成对）
```

但**全部加密**，三条证据：

1. 165 个文件只有 6 种 8 字节魔数（如 `3c1f706db84416e3` 占 102 个），**不是 ONNX protobuf**（ONNX 以 `\x08` 开头）；
2. 实测 `sha256` 与同目录 `models.json` 记录的 `plaintext_source_sha256` **不一致**（`xg/policy_mix_walk` 实测 `fd4b66cd…` vs 记录明文 `bdb332b6…`）；
3. 该 json 自带 `"encrypted_model_counts"` 与 `source_repository: GENISOM-AI/MATRiX_Robot_MC`（发布包不含独立运控）。

⇒ 按项目**规则 S**（无训练源码的策略不登记部署），这批模型**不入策略库**，仅作能力与命名参考。

### 2.4 传感器语料：容器可验证，载荷未解码

`UeSim/Plugins/RobotSensorSimulation/Data/` 两份录制数据：

| 文件 | 大小 | 魔数 | 版本 | 帧大小 | 正体偏移 | 帧数 | 时长@10Hz |
|---|---:|---|---:|---:|---:|---:|---:|
| `Airy_2026-07-03_frame0225.airybin` | 63,652,192 | `ARY1` | 1 | 1,720,320 | 352 | 37 | 3.7 s |
| `Mid360_2025-11-28_2s_valid.mid360bin` | 12,717,276 | `M3D1` | 2 | 264,936 | 348 | 48 | 4.8 s |

- 分帧自洽：`body_offset + frames × frame_size == file_size`（352+37×1720320=63652192；348+48×264936=12717276）。
- **载荷未解码**：把正体按 float32 列统计，两文件均以非有限/非规格化值为主（Airy 仅 77.8% 有限、Mid360 97.1%），说明记录内**整型与浮点字段混排**，而发行包未给出布局文档 → 不写猜测性解析器，只固化可验证的容器事实。

## 3. 资产清单（可评估项）

| 类别 | 内容 | 数量/体量 |
|---|---|---|
| 机器人模型 | go2、go2w、xgb、xg2、xgw、xgw2、zgws、zgwsarm、zgwt | 9 族，485M |
| 传感器声明 | `config/config.json` + `config/sensors/*.json` | 9 套预设 |
| 传感器语料 | Airy / Mid360 录制帧 | 2 份，76M |
| 传感器预设参数 | `config/jszr_params/lidar_process_params.yaml` 等 | — |
| 地图机制 | `Content/model/MapDataTable.json`（空表）+ `Saved/DLCs/*.pak` + UPDATE LIST 目录 | 基础包为空目录 |
| 感知工具 | `visualize_lidar_camera_projection.py`(1825 行)、`zenoh_sensor_receiver.py`(1048 行)、`visualize_zenoh_bbox*.py`、`zenoh_topic_monitor.py`、云台 UDP 工具 | 10 个，5582 行 |
| 文档 | USAGE / MOTION_CONTROL / LidarCameraProjection / MAP_DLC / ZenohBBox2D / RoamerX_Lite 集成 / PixelStreaming | 15 篇，116KB |
| 传输与远端渲染 | Zenoh router(7447) + Pixel Streaming 2 WebServer 脚本 | — |
| 运控 | 内置 MC（加密模型 + `libonnxruntime.so.1`）+ `matrix_mc_udp_test.py` + 云台 JSON 协议(44KB) | 952M（加密） |

## 4. 对项目的价值映射

### 4.1 高级仿真（重点）

现状（改动前）：`web/advanced_sim.html` 用**文案**描述「外部传感器（深度相机 / 雷达 / 点云）」，机读词汇只有 `backend/perception_observations.py` 的 4 个派生源（`proprio / foot_contact / heightfield / depth_camera`）、策略侧靠 `sim_surface=advanced` 过滤。**缺：传感器清单契约、多传感器语料、点云→观测的对齐基准。**

| # | MATRiX 资产 | 对高级仿真的价值 | 落地 |
|---|---|---|---|
| 1 | `config.json` + `sensors/*.json` | 声明式传感器 schema（类型/挂载体/外参/频率/话题/内参）→ 把「外部传感器」从文案变成契约 | **本次已落地**（`backend/sensor_suite.py` + `/api/sensors/*` + 高级仿真页面板） |
| 2 | Airy / Mid360 录制帧 | 无需 GPU 的离线语料：点云解析与「雷达高度扫描 ↔ heightfield 逐格对齐」回归的样本源 | **本次已登记**（`tools/matrix_sensor_corpus.py` 固化容器事实 + 自检） |
| 3 | `visualize_lidar_camera_projection.py`（1825 行）+ 投影文档 | 现成的雷达→相机投影实现：XCDR1 订阅、内外参、`sensor_sync_mode` 配对、坐标约定、标定 JSON | 待接入（本次只登记契约字段） |
| 4 | `visualize_zenoh_bbox.py`/`_2d.py` + ZenohBBox2D 文档 | 目标级感知可视化与判定（3D/2D bbox）→ 对应高级仿真「目标判定」 | 待接入 |
| 5 | `zenoh_sensor_receiver.py` + 主题监控 | 传感器数据的实际编码与频率（IMU 500Hz、odom/GPS 100Hz、相机与雷达 10Hz）→ 写 obs 契约时的权威默认值 | **本次已落地**（套件频率即采用该口径） |
| 6 | 动作库命名（stair/climb/flipover/handstand/mimic…）与 `policy_*`/`odom_*` 分离 | 目标驱动任务分类法与「估计器网络独立于策略」的路线参照（与 HIMLoco 一致） | 参考（不导入加密模型） |
| 7 | `MapDataTable.json` + DLC pak 增量分发 | 大场景按需下载、不进仓的清单式分发思路 | 参考（对照 `backend/scenario_maps.py`） |
| 8 | Pixel Streaming 2 | 远端渲染补位：浏览器 WASM 跑不动的高保真场景可放服务器推流 | 远期 |

### 4.2 高级仿真之外

| 资产 | 价值 | 约束 |
|---|---|---|
| 9 族 MJCF | `go2`/`go2w` 交叉校验；`xgb/xg2/xgw/xgw2/zgws/zgwsarm/zgwt` 为新机型候选；`scene_terrain_moon_dynamic.xml` 为低重力地形素材 | 新机型须过规则 T（有训练源）才可入库 |
| M20 之外的轮足/机械臂形态 | `zgwsarm`（4 足 + 6 轴臂）与项目现有形态互补 | 同上 |
| 内置运控 UDP 协议 + 云台 JSON 协议 | 真机/外部运控接口参考 | 许可需核实 |

## 5. 本次落地的提取（代码改动）

| 文件 | 改动 | 作用 |
|---|---|---|
| `backend/sensor_suite.py`（新增） | 8 套预设 / 17 条传感器声明 + `/api/sensors/kinds`、`/api/sensors/presets`、`/api/sensors/presets/{name}` | 把 MATRiX 的传感器声明变成控制面契约；每 kind 标注 `proprioceptive` / `exteroceptive` |
| `backend/api_complete.py` | 注册 `sensor_suite_router` | 端点生效 |
| `backend/perception_observations.py` | 新增 `lidar_height_scan`（width=180，`align_with=heightfield`）；`sensor` 注释补 `lidar` | 雷达点云→高度扫描的观测入口，网格与内置 heightfield 同规格，便于逐格对齐回归 |
| `tools/matrix_sensor_corpus.py`（新增） | 容器探测（魔数/版本/帧大小/正体偏移/帧数/时长）+ `--selftest` + `--json`，退出码 0/1/2 | 语料可验证、缺失可降级；不写猜测性载荷解析 |
| `web/advanced_sim.html` | 新增「外部传感器套件」面板，读 `/api/sensors/presets(+/default)` | 高级仿真页从文案升级为数据驱动 |
| `backend/test_perception_observations.py` | 新增 `MatrixSensorSuiteTests` / `MatrixSensorCorpusTests` / `SensorKindCoverageTests`（模块共 19 例） | 该测试模块已在 `.cnb.yml` 的 unit-tests 清单中，改动即被 CI 覆盖 |
| `.gitignore` | 新增 `matrix-v1.0.13/` | 9.5G 下载物永不入库 |

## 6. 未提取 / 不建议

1. **不导入加密运控模型**（165 件）——违反规则 S，且无法校验输入输出维度。
2. **不随项目分发 `UeSim` 二进制、`Engine/`、`Content/Paks/`**——许可未核实且体量 4.7G。
3. **不写点云载荷解析器**——载荷布局无文档且实测为非纯 float 排布（见 2.4），猜测实现会污染 obs 契约。
4. **不把 UeSim 纳入自动验收**——需 GPU + 非 root，容器与 CI 均不满足（见 2.2）。

## 7. 复现命令

```bash
# 1) 校验分卷
cd matrix-v1.0.13 && sha256sum -c SHA256SUMS

# 2) 解压
cat MATRiX_v1.0.13.tar.gz.part-* | tar -xzf - -C extracted

# 3) 语料容器探测（含合成自检，不需要发行包）
python3 tools/matrix_sensor_corpus.py --selftest
python3 tools/matrix_sensor_corpus.py --json

# 4) MJCF 加载实测（需要 mujoco）
/tmp/mjlab_cpu_venv/bin/python - <<'EOF'
import os, mujoco
base = "matrix-v1.0.13/extracted/MATRiX_v1.0.13/UeSim/Content/model"
for rel in ("xgb/xgb.xml", "go2/go2.xml", "zgwsarm/zgwsarm.xml"):
    os.chdir(os.path.join(base, os.path.dirname(rel)))
    m = mujoco.MjModel.from_xml_path(os.path.basename(rel)); d = mujoco.MjData(m)
    for _ in range(200): mujoco.mj_step(m, d)
    print(rel, "nq=", m.nq, "nu=", m.nu)
EOF

# 5) 契约与测试
curl -s localhost:8765/api/sensors/presets | head -c 400
python -m unittest backend.test_perception_observations
```

## 8. 结论

MATRiX v1.0.13 对项目的**可迁移价值是「声明与语料」，不是「运行时」**：传感器 schema 与语料容器事实已抽取落地，模型可作交叉校验与新机型来源，而 UE5 运行时、加密策略、点云载荷三块不可复用或不该复用。高级仿真的下一步是把 §4.1 的 #3/#4（投影与 bbox）接进页面，并用 §4.1 #2 的语料做 `lidar_height_scan ↔ heightfield` 的逐格对齐回归。
