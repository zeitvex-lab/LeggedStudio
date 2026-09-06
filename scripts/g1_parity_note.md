# G1 浏览器 / 桌面 Sim2Sim 一致性（parity）验证方案

> 状态：脚手架（未实现）。本文档记录「用固定动作序列对比浏览器与桌面 obs/action」的
> 验证方案，供后续实现 parity 测试时参考。

## 目标

浏览器查看器（`web/sim2sim/app.js`，mujoco-wasm + onnxruntime-web）与桌面复现环
（Python，`mujoco` + `onnxruntime`）在同一初始状态、同一固定动作序列下，逐步产出的
`obs` 与 `action` 数值一致（或误差在容差内），用于确认观测构造、动作映射、PD 控制
没有在浏览器移植时走样。

## 原则

1. **绕开策略**：不对比策略输出对物理的影响，而是固定动作序列（例如 200 步
   `sin` 扫频或录制的 ONNX 输出回放），分别喂给两边的 `mj_step` 前处理链。
2. **固定随机性**：关掉随机延迟（motor/imu delay）、随机初始姿态；固定 settle 步数。
3. **同一份资产**：用同一个 MJCF 与同一个 ONNX/契约（`policy.contract`）。
4. **逐步快照**：每个控制步（`sim_dt * decimation`）记录
   `{ t, obs[...], action[...], qpos[...], ctrl[...] }`。

## 浏览器侧采集（已具备的钩子）

- `?debug=1`（或 `qa`）会暴露 `window.__sim2simDebug`：
  - `startFrameLog()` / `stopFrameLog()`：记录最多 300 个控制步的
    `{ t, obs, action, ctrlBefore, targetsPos, targetsVel }`。
  - `reset()`：确定性重置。
- 另有 `window.__probe`（每帧）与 `#__sim2simDebugState`（JSON 调试节点）。
- 建议新增一个 `__sim2simDebug.playActionClip(clip, {decimation})` 钩子：
  停用策略（`setPolicyEnabled(false)`），按控制周期把 `clip[step]` 写入
  `sim.action / sim.appliedAction / sim.filteredAction`，其余链路
  （`buildObservation` → `pushHistory` → PD → `mj_step`）不变。

## 桌面侧采集

复用现有 `scripts/g1_amp_sim2sim_check.py` 的骨架：

1. 加载同一 MJCF / 同一初始 keyframe，`mj_resetData`；
2. 对每个控制步：以 `clip[step]` 作为策略输出走同一套动作映射与 PD
   （对照 `app.js` 中 `stepSimulation` 的 torque / position_target 分支），
   按 `build*Observation` 的分段顺序拼 `obs`；
3. 输出 `parity_desktop.json`（结构同浏览器 `frameLog`）。

## 对比脚本（建议实现为 `scripts/g1_parity_check.py`）

```text
差异指标：
  per-step  max|obs_b - obs_d| 、max|action_b - action_d|
  分段报告：命令段 / 关节位置段 / 关节速度段 / 上一动作段 / IMU 段
判定阈值（经验值）：
  obs   ≤ 1e-4（float32 求值顺序差异通常 ~1e-6）
  action ≤ 1e-4
失败时打印第一个超差步号 + 误差最大的观测分量索引，
对照 observation 布局表定位是哪一段（IMU 轴序 / 重力符号 / reindex / scale）。
```

运行方式（设想）：

```bash
# 浏览器：legged_studio 起服务后，用 Playwright 打开 /web/sim2sim/?debug=1
node scripts/g1_parity_capture.mjs --out artifacts/parity_browser.json
# 桌面：
python scripts/g1_amp_sim2sim_check.py --clip artifacts/action_clip.json --out artifacts/parity_desktop.json
python scripts/g1_parity_check.py artifacts/parity_browser.json artifacts/parity_desktop.json
```

## 常见不一致来源（排查清单）

- IMU 轴向符号（`imuAxisSigns`）与桌面 `projected_gravity` 取负约定（mjlab 系）；
- `dofReindex / actionReindex` 只在浏览器侧按契约应用，桌面侧需同样置换；
- `CONFIG.angVelScale / dofVelScale / cmdScale` 与训练 scale 不一致；
- PD 的 `position_target`（原生执行器）与浏览器侧二次 PD 混用；
- 历史栈布局（term-major vs frame-major，`history_layout` 契约）；
- `settleSteps` 与初始 keyframe 差异。
