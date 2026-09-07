# 云深处 Lite3/M20 移植评估与落地记录

> 来源项目（均为 BSD-3-Clause 或含 BSD 声明，可商用，需保留署名链）：
> `rl_training`（官方训练库）、`m20_rl_isaacsim`（社区定制训练库 + 导航部署栈）、
> `Dreamwaq`（个人 DreamWaQ 轮足实现）、`sdk_deploy`（官方 ROS2 部署库）。
> 评估日期：2026-09-08。

## 已落地（本轮）

### deeprobotics_m20（第 14 包）

- **模型**：官方 `deep_robotics_model/M20/M20_mjcf/M20.xml` + 17 STL（12MB），场景元素
  （floor/light/MatPlane）已剥离到 scene.xml，meshdir 修正为包内 `assets/`。
  nq=23 nu=16，34.5kg，轮半径 0.09m。
- **部署基准**：`exported/m20_new_policy.onnx`（官方导出，元数据内嵌：关节序/PD/默认角/scale），
  obs57 → act16（12 腿位置 + 4 轮速度），observation_kind = `go2w_rl_sdk_57`（复用，轮位置清零逻辑同构）。
- **训练任务**：`m20_velocity`（go2w_velocity 模式移植）：腿 Kp80/Kd2/effort76.4/armature0、
  轮 Kp0/Kd0.6/effort21.6/armature0.00243、默认姿态前腿 hipy −0.6 knee +1.0 / 后腿 +0.6/−1.0、站高 0.52。
- **契约要点**：模型执行器序为每腿交错（hipx,hipy,knee,wheel ×4），策略序为 12 腿+4 轮，
  以 `contract.joint_ids_map = [0,1,2,4,5,6,8,9,10,12,13,14,3,7,11,15]` 桥接。

### deeprobotics_x30（第 15 包）

- 官方 `X30_mjcf/X30.xml`（nq=12 nu=0，55.8kg，新一代四足）+ STL 网格（meshdir `.`）。
- 训练任务 `x30_velocity`（lite3 模板移植，HipX effort 150 / HipY·Knee 84）。
- **策略待训练后回填**（simulation/config.json 的 policies 为空数组）。

### deeprobotics_lite3 官方部署档案

- `simulation/config.json` 新增 `lite3-official-sdk-45` 策略条目：himloco 权重 + 官方
  sdk_deploy 部署参数（PD 30/1、default [0,−0.8,1.6]、action_scale 0.125/0.25/0.25、
  站高 0.30、连杆长、限位、键盘命令缩放）。
- `contract.official_sdk` 段记录完整部署真值（含"PostureUnsafeCheck 官方注释禁用，实机须重新启用"警示）。

### dreamwaq live_batch 损失掩码

- `go2_skills/dreamwaq/mdp/rl.py::DreamWaQPPO.update` 回移植源实现的
  `live_batch = 1 - dones` 掩码：跨 reset 边界的 history 样本不再污染 VAE
  估计器训练（velocity/recon 按存活样本加权）。

### 新工具

- `tools/urdf_to_mjcf.py`：URDF→MJCF 通用转换器（MjSpec 编译，碰撞 primitive 化，
  惯性保留，无 mesh 依赖）——Lite3/A1/X30 的模型均经此路径生成。

## 待办候选（未落地）

| 项目 | 内容 | 来源 | 备注 |
| --- | --- | --- | --- |
| DeepFollow 任务 | M20 位置跟随（5531 行，CE-Net actor-critic） | rl_training commit `172b5fb`（已 revert，`git show 172b5fb:<path>` 可恢复） | 中工作量，需 CENet 结构移植 |
| M20 DreamWaQ 轮足任务 | 已实机部署的轮足 DreamWaQ（`policy_dwaq.onnx` + `model_18000.pt`） | Dreamwaq `legged_gym/envs/M20` + `logs/M20` | M20 包已就绪，移植训练配置+导出即可 |
| VAE+actor 融合导出 | `PolicyExporterDWAQ`（单网络 obs_history→action） | Dreamwaq `helpers.py` | 需按 go2 的 45 维 obs 去魔数化 |
| DR02 人形 AMP | 21 DoF 人形 + 判别器 + CE-Net + 动捕数据集 | rl_training `rl_training/rsl_rl` + AMP 数据 | 高成本；G1 AMP 已覆盖同类能力 |
| Lite3 实机链路 | `Lite3_MotionSDK` UDP（1kHz 重发/急停码）/仅 Venture 版 | sdk_deploy `lite3_transfer` | 硬件相关，实机联调阶段处理 |
| G1 带手 MJCF | `g1_29dof_with_hand.xml` | rl_sar_zoo g1_description | 带手版本模型来源 |

## 关键参数真值（M20/Lite3，sim2sim 必备）

### M20（轮足，16 DoF）

- 关节序（模型交错）：`{fl,fr,hl,hr}_{hipx,hipy,knee,wheel}_joint`；策略序：12 腿+4 轮。
- 默认姿态：hipx=0；前腿 hipy −0.6 / knee +1.0；后腿 hipy +0.6 / knee −1.0；轮 0；站高 0.52。
- 执行器：腿 Kp80/Kd2/effort76.4/vel22.4；轮 Kp0/Kd0.6/effort21.6/vel79.3/armature0.00243。
- 轮驱动：`v_cmd = action×5.0`，`τ = 0.6×(v_cmd − v)`。
- obs57：`ang_vel×0.25 + gravity + cmd + (dof_pos−default)×1.0【16 维轮置零】+ dof_vel×0.05 + action`。
- 命令：vx ±2、vy ±1、wz ±1；防遗忘固定比例采样（零速 0.2/纯转向 0.2/纯 y 0.02/纯 x 0.02）。
- 力矩限幅在固件侧；MJCF ctrlrange 腿 ±200/±300、轮 ±20。

### Lite3（四足，12 DoF，官方部署值）

- 关节序：`{FL,FR,HL,HR}_{HipX,HipY,Knee}_joint`；默认 `[0,−0.8,1.6]×4`（HipX FL/HL=−0.1、FR/HR=+0.1）。
- 部署 PD 30/1（站立 100/2.5）；himloco 训练 PD 40/1。
- action_scale 0.125/0.25/0.25；站高 0.30；连杆 0.0985/0.20/0.21。
- obs45：`ang_vel×0.25 + gravity + cmd + (dof_pos−default) + dof_vel×0.05 + action`（单帧）；himloco 为 6 帧堆叠 270。
- 限位（FL）：HipX ±0.53、HipY [−3.5,0.32]、Knee [0.349,2.8]；速度限 30/30/20；力矩限 40/40/65。

## 风险与注意事项

1. **官方数据漂移**：训练 cfg 与 ONNX 元数据的默认姿态存在不一致（Lite3 −0.65/1.3 vs −0.8/1.6；
   M20 ±0.3/±0.6 vs ±0.6/∓1.0）——以训练 cfg 为准，部署前与官方部署仓库核对。
2. **obs 维度陷阱**：M20 joint_pos 是 16 维轮置零（非 12 维裁剪）；`yk_policy.onnx`（72 维）是另一套 obs，勿混用。
3. **checkpoint 格式**：cusrl 风格 `actor_state_dict`（`mlp.` 前缀），标准 rsl_rl 需键重映射（`export_onnx_fast.py` 有实现）。
4. **姿态保护**：sdk_deploy 官方将 `PostureUnsafeCheck` 注释禁用——移植部署状态机必须重新启用。
5. **M20 实机标定**：dir/offset 表 + HipY/Knee ±360° 多圈校正（`m20_interface.hpp`）为实机必需；多圈原点取决于上电姿态。
6. **许可证署名链**：BSD-3/Apache 均可商用；Dreamwaq 无独立 LICENSE（散布 BSD 声明 + ETH/Rudin/Wheel_Legged_Gym 署名链）；
   各厂商 mesh 上游条款逐机型核对后方可对外分发。
7. **行为等价**：内化验证覆盖 env/runner 构建；跨模拟器（PhysX→MuJoCo）接触动力学差异带来的奖励
   尺度漂移（尤其 M20 的 ±1000/+50 强数值项）需一次实际训练 smoke 确认。
