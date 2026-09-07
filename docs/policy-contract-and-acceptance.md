# 策略契约元数据 · 裁剪 · 验收（约定与迁移说明）

> 对应清单条目 ①②③⑤⑥⑦⑧；参考实现：unitree_rl_mjlab `AS2W_REFERENCE_24_40.md`（验收协议）、
> `mjlab/rl/exporter_utils.py`（元数据盖章）、`scripts/evaluate_go2w_*.py`（验收三件套）。

## 1. ONNX 元数据盖章（训练即导出）

训练完成时 worker 自动导出 `exported/policy.onnx` 并把部署契约写进 `metadata_props`
（`adapters/mjlab/native_worker.py::export_runner_policy_onnx`，键名与 mjlab exporter 对齐）：

| 键 | 内容 |
|---|---|
| `joint_names` | 动作槽序（CSV），**训练时策略槽位的真实关节顺序** |
| `joint_stiffness` / `joint_damping` | 逐槽增益（来自 mj_model actuator gainprm/biasprm） |
| `default_joint_pos` | 默认关节角（槽序） |
| `observation_names` / `command_names` | 观测项 / 指令项名单 |
| `action_scale` | 逐槽动作缩放 |
| `clip_actions` | 动作裁剪界（标量），未设置则不写 |
| `source` | 来源说明（手工补盖时使用） |

浏览器 `web/sim2sim/app.js::validatePolicyMetadata` 加载策略时用自带的 protobuf 扫描器
（`readOnnxMetadataBytes`，因 vendored ORT 无 metadata API）读取这些键并与机器人契约比对：

- 无盖章的旧策略：静默跳过
- 一致：控制台输出 `✔ 策略元数据与契约一致`
- 不一致：控制台报错 + 策略状态显示 `已就绪 · 元数据不匹配（槽 i: …）`（不阻断加载）

## 2. 契约字段

- `clip_actions`：数字 / 逐关节 CSV。训练 vec-env wrapper 与浏览器推理端在同一位置
  （scale/offset 之前的原始动作）施加同一界。缺省 = 仅保留 ±100 安全界。
- `action_joint_order`：策略动作槽序。缺省回退 `contract.json → action.joint_order`。
  **跨槽位序的事故（SDK 序 vs isaaclab 序 vs mjlab 实体序）由此字段 + 元数据校验双重兜底。**
- `gait_period_s`：步态相位钟周期（mjlab velocity 系策略），缺省 0.6s。
- 轮关节观测掩码：连续关节位置观测需 wrap ±π（见 `buildGo2wMjlabLegsObservation`），
  新增带轮布局时两处同步：`web/sim2sim/app.js` 构建器 + `adapters/mjlab/policy_acceptance.py` 构建器。

## 3. 验收（acceptance）

- 评估器：`adapters/mjlab/policy_acceptance.py`（适配器 venv 运行，依赖 mujoco+onnxruntime）。
  - 验收模式：`--package <pkg> --policy <onnx> [--modes 0,0,0 0.5,0,0] --seconds 6 --seed 0`
  - 预检模式：`--package <pkg> --probe`（无策略，开环恒定动作扫物理包络，训练前 pre-flight）
- 接口：`POST /api/simulation/policies/acceptance` `{robot_id, policy_id}`。
- 指标落盘：`simulation/policies/<onnx stem>.acceptance.json`，schema `policy-acceptance-1.0`：
  逐指令模式 `{fell, fell_at_s, survival_ratio, vel_track_err, height_min, roll_max_deg, pitch_max_deg, pass}`
  + 汇总 `{passed, total, verdict}`。
- 展示：browser-config 把报告折算为策略健康检查 `{"id":"acceptance", ...}`，
  仿真页"策略检查"面板自动渲染（如 `验收 5/5 模式通过 · 跟踪误差≤0.0~0.12`）。
- 验收协议（P2 教条）：**奖励通过但回放视觉不通过 = 没学会**。仿真页即确定性回放环节。

## 4. 新增观测布局 checklist

1. `web/sim2sim/app.js`：新增 `build<Xxx>Observation()` + `buildObservation()` 分发
2. `adapters/mjlab/policy_acceptance.py`：`ObsBuilder.build` 增加同名分支（两处逐项一致）
3. 机器人包 `simulation/config.json`：策略条目 contract 声明 `observation_kind` / `obs_dim` /
   `action_joint_order` / `default_joint_angles` / `action_scale_by_joint` / `clip_actions`
4. 用验收器跑一遍 + 浏览器加载看元数据校验输出

## 5. 已知待办

- G1 浏览器"局部 vx"读数疑似 `cvel` 线速度测量偏差（指令 0.15 实测显示 ~0.79）；
  可用本验收器做基准二分（Python 链路跟踪误差 ≤0.12，说明策略与契约本身没问题）。
- 每 checkpoint 导出（而非仅训练结束导出）：需在 mjlab runner 子类挂 save 钩子。
- go2 内置基线策略（非包策略）暂无验收接入。
