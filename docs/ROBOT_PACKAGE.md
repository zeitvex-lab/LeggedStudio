# 机器人包工程手册（Robot Package Handbook）

一个机器人包从建包、训练、到策略验收的全部约定。参考实现：unitree_rl_mjlab 的 deploy 三级布局与碰撞精简做法、robot_lab 的自描述 motion NPZ schema 与框架无关常量模块。

适用范围：`assets/robots/<robot_id>/` 与工作区导入的包（`workspace/packages/`）。前提：上游有 MJCF + 网格 + 训练任务配置（如 unitree_rl_mjlab 的 `src/assets/robots/<r>/xmls/`）。

## 1. 目录布局

```
<robot_id>/
  contract.json              # RobotContractV2（尺寸/关节/观测/动作/控制契约，schema robot-contract-2.0）
  robot_package.json         # 包清单（schema robot-package-1.0）
  model/
    robot.xml                # MJCF 最终产物（visual/collision 双 class 分层；碰撞用原始体）
    assets/                  # 网格（记录精简结论：如 "9 boxes + 4 spheres + 4 wheel cylinders"）
  simulation/
    config.json              # schema simulation-config-1.0（增益/decimation/策略条目）
    scene.xml                # 平地场景（include 机器人；桌面端 include+meshdir 有已知坑，见 §6）
    flat.xml / *.xml         # 浏览器可选场景
    policies/
      <name>.onnx            # 导出策略（建议含 metadata_props 盖章，见 §4）
      <name>.acceptance.json # 验收指标（schema policy-acceptance-1.0，与 onnx 同名）
  training/
    config.json              # 训练入口配置
    profiles/*.json          # 训练 profile（training-profile-1.0）
    source/                  # 包内训练源码（特殊任务实现）
  motions/                   # （预留）参考动作
    <name>.csv               # 原始重定向数据（可追溯源文件）
    <name>.npz               # 自描述 NPZ：fps/dof_names/body_names/dof_positions/
                             #   body_rotations(wxyz)/body_*_velocities
  acceptance/                # （预留）验收参考档案：参考 episode 录制 + 通过阈值
```

## 2. capabilities（robot_package.json）

能力声明用于枚举门控（robot_lab register/detect 模式）：

| capability | 含义 | 谁消费 |
|---|---|
| `generic_mjlab` | 可被通用 mjlab 任务训练 | 训练配置页 / worker |
| `mjlab_source_profiles` | 包内带 mjlab 源码 profile | 训练配置页 |
| `mujoco_sim` | 可进浏览器 MuJoCo 仿真 | `browser-config` 422 门控 |
| `package_extension` | 带扩展任务源 | worker 扩展加载 |

新增能力时：robot_package.json 声明 → `backend/robot_packages.py` 枚举透传（已支持）→ 消费端按需门控。

## 3. 训练 profile（training-profile-1.0）

所有带源码的训练 profile 使用同一套机器人中立字段——Web UI 与 native worker 永远不按机器人 id 分支：

| 字段 | 用途 |
|---|---|
| `source_root` | 持久化包内的导入根目录 |
| `entrypoints.env` | MJLab 环境工厂（`module:callable`） |
| `entrypoints.runner` | 算法 runner-config 工厂 |
| `entrypoints.runner_class` | 可选自定义 runner 类 |
| `entrypoints.configure` | 可选的包级钩子（机器人字段映射） |
| `runner` | UI 可编辑的算法默认值 |
| `command_ranges` | UI 可编辑的统一 `lin_vel_x`/`lin_vel_y`/`ang_vel_z` 范围 |

需要特殊关节映射、传感器、奖励、地形或指令语义的包，把实现放在 `training/source/` 之下并通过上述 entrypoints 暴露。项目 ZIP 导入/导出复制完整包树，profile 与其源码模块在持久化后仍然可用。

### 扩展入口（package_extension）

Go2 的 LLoco 实现使用所有机器人共享的包扩展契约：`extension_entrypoint` 把包资产工厂注册到 MJLab 的规范 asset-zoo 路径。后端不导入也不依赖 `unitree_rl_mjlab`；机器人专属的 XML、执行器、观测、奖励和地形逻辑全部留在机器人包 profile 内部。

### LLoco 桥接（external source_root 模式）

`training/source_lloco/lloco_bridge/` 是外部训练源仓库（`lain_job/LLoco`，mjlab==1.6.0，Apache-2.0）的薄桥：把 LLoco 的 `src` 加入 sys.path，并把带参工厂（`make_flat_env_cfg(profile)`）适配成 worker 契约的无参 `module:factory`。

- profile：`training/profiles/lloco-go2-flat.json`（entrypoints 指向 bridge）
- 冒烟已验证：env 构建 / reset / step / reward 全通；worker `_load_profile_bundle` 加载通过
- **注意**：运行时读取的是 `workspace/packages/<id>/` 副本——assets 与 workspace 两边都要放（capabilities、profiles、bridge 同步），改包后需 `POST /api/robots/packages/refresh`
- 扩展：给其他机器人加 LLoco 任务只需在 bridge 的 `_PROFILE_BY_KEY` 加一行

## 4. 策略契约与 ONNX 元数据盖章

训练完成时 worker 自动导出 `exported/policy.onnx` 并把部署契约写进 `metadata_props`（`adapters/mjlab/native_worker.py::export_runner_policy_onnx`，键名与 mjlab exporter 对齐）：

| 键 | 内容 |
|---|---|
| `joint_names` | 动作槽序（CSV），**训练时策略槽位的真实关节顺序** |
| `joint_stiffness` / `joint_damping` | 逐槽增益（来自 mj_model actuator gainprm/biasprm） |
| `default_joint_pos` | 默认关节角（槽序） |
| `observation_names` / `command_names` | 观测项 / 指令项名单 |
| `action_scale` | 逐槽动作缩放 |
| `clip_actions` | 动作裁剪界（标量），未设置则不写 |
| `source` | 来源说明（手工补盖时使用） |

浏览器 `web/sim2sim/app.js::validatePolicyMetadata` 加载策略时读取这些键并与机器人契约比对：无盖章的旧策略静默跳过；一致输出确认；不一致显示"已就绪 · 元数据不匹配（槽 i: …）"但不阻断加载。

策略契约关键字段：

- `clip_actions`：数字 / 逐关节 CSV。训练 vec-env wrapper 与浏览器推理端在同一位置（scale/offset 之前的原始动作）施加同一界。缺省 = 仅保留 ±100 安全界。
- `action_joint_order`：策略动作槽序。缺省回退 `contract.json → action.joint_order`。**跨槽位序的事故（SDK 序 vs isaaclab 序 vs mjlab 实体序）由此字段 + 元数据校验双重兜底。**
- `gait_period_s`：步态相位钟周期（mjlab velocity 系策略），缺省 0.6s。
- 轮关节观测掩码：连续关节位置观测需 wrap ±π（见 `buildGo2wMjlabLegsObservation`），新增带轮布局时两处同步：`web/sim2sim/app.js` 构建器 + `adapters/mjlab/policy_acceptance.py` 构建器。

## 5. 验收（acceptance）

- 评估器：`adapters/mjlab/policy_acceptance.py`（适配器 venv 运行，依赖 mujoco+onnxruntime）。
  - 验收模式：`--package <pkg> --policy <onnx> [--modes 0,0,0 0.5,0,0] --seconds 6 --seed 0`
  - 预检模式：`--package <pkg> --probe`（无策略，开环恒定动作扫物理包络，训练前 pre-flight）
- 接口：`POST /api/simulation/policies/acceptance` `{robot_id, policy_id}`。
- 指标落盘：`simulation/policies/<onnx stem>.acceptance.json`，schema `policy-acceptance-1.0`：逐指令模式 `{fell, fell_at_s, survival_ratio, vel_track_err, height_min, roll_max_deg, pitch_max_deg, pass}` + 汇总 `{passed, total, verdict}`。
- 展示：browser-config 把报告折算为策略健康检查 `{"id":"acceptance", ...}`，仿真页"策略检查"面板自动渲染。
- 验收协议（P2 教条）：**奖励通过但回放视觉不通过 = 没学会**。仿真页即确定性回放环节。

### 新增观测布局 checklist

1. `web/sim2sim/app.js`：新增 `build<Xxx>Observation()` + `buildObservation()` 分发
2. `adapters/mjlab/policy_acceptance.py`：`ObsBuilder.build` 增加同名分支（两处逐项一致）
3. 机器人包 `simulation/config.json`：策略条目 contract 声明 `observation_kind` / `obs_dim` / `action_joint_order` / `default_joint_angles` / `action_scale_by_joint` / `clip_actions`
4. 用验收器跑一遍 + 浏览器加载看元数据校验输出

## 6. 新机器人接入（半天流程）

以 A2 接入为参照实例（commit `unitree a2: new robot package...`）。

### 第 1 步：模型与网格（30 分钟）

- [ ] `assets/robots/<id>/model/robot.xml` ← 上游 MJCF（保留其 `meshdir="assets"` 写法）
- [ ] `assets/robots/<id>/model/assets/` ← 全部网格
- [ ] 记录碰撞精简结论（robot_package.json `notes`）：如 "9 boxes + 4 spheres + 4 wheel cylinders"
- [ ] 验证：`mujoco.MjModel.from_xml_path('model/robot.xml')` 可编译（`nq` 含自由关节 7 + 关节数）

### 第 2 步：契约与配置（30 分钟）

- [ ] `contract.json`（robot-contract-2.0）：`actuated_joints` 顺序 = 上游训练关节序；`default_pose` = 上游 InitialStateCfg
- [ ] `simulation/config.json`：stiffness/damping/torque_limits/**armature**（逐关节，从上游 constants 提取）+ action_scale + command_ranges + `initial_keyframe`
- [ ] `robot_package.json`：capabilities 至少 `["generic_mjlab", "mujoco_sim"]`
- [ ] `training/config.json` + profiles（flat/rough 各一份，command_ranges 从上游 env_cfgs 抄）

### 第 3 步：浏览器仿真（30 分钟）

- [ ] `simulation/scene.xml`（include 模式，参照 go2w/g1；桌面端 include+meshdir 有双重前缀坑，见下）
- [ ] `backend/simulation_api.py::_configure_browser_actuators`：机器人不在白名单时加分支——position/velocity 执行器按契约增益生成（A2 例：`kp/kv/forcerange` 逐关节从 config 表读）
- [ ] 重启后端 → `POST /api/robots/packages/refresh` → `GET /api/simulation/browser-config/<id>` 检查
- [ ] 浏览器 `?robot=<id>&policy=off`：姿态保持站立、无告警

### 第 4 步：验收与元数据（30 分钟）

- [ ] `policy_acceptance.py --package <id> --probe`：verdict pass（默认姿态 + 动作包络）
- [ ] 有策略后：拷入 onnx → policy 条目 contract（observation_kind/obs_dim/action_joint_order/default_joint_angles/action_scale_by_joint/clip_actions）→ 跑 acceptance → 5/5 通过
- [ ] 元数据盖章（手工补盖用 `attach_metadata_to_onnx`，参考 go2w/g1 的补盖脚本）

### 第 5 步：提交

- [ ] 一次性提交整个包 + API 改动，commit 信息 `unitree <id>: new robot package with ...`

### 常见坑

- include 场景的 meshdir 双重前缀——浏览器（虚拟 FS）不受影响；桌面端统一用 MjSpec 组装（`adapters/mjlab/scene_builder.py`）
- 关节顺序三种流派：SDK 按腿分组（FR,FL,RR,RL）/ isaaclab 按类型分块 / mjlab 实体序——一律以**上游训练配置的槽位序**为准写进 `action_joint_order`，元数据校验会兜底
- 上游 XML 无 actuator（执行器在 constants 注入）时，浏览器必须走 `_configure_browser_actuators` 分支

## 7. 命名与校验规则

- 验收指标文件名 = `<onnx stem>.acceptance.json`，与策略同目录；`browser-config` 自动折算为策略健康检查 `acceptance`。
- 策略元数据盖章键名见 §4；浏览器加载时自动校验 `joint_names` 顺序与契约 `action_joint_order` 一致。
- motions NPZ 的 `dof_names` 必须与 `contract.json → joints.actuated_joints` 一致（导入时可校验）。
- 部署参数（若单独成文件）数组长度必须等于 `action.dimension` / `observation.dimension`。
