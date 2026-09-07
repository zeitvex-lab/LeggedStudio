# 新机器人接入 Checklist（半天流程）

> 以 A2 接入为参照实例（commit `unitree a2: new robot package...`）。
> 前提：上游有 MJCF + 网格 + 训练任务配置（如 unitree_rl_mjlab 的 `src/assets/robots/<r>/xmls/`）。

## 1. 模型与网格（30 分钟）

- [ ] `assets/robots/<id>/model/robot.xml` ← 上游 MJCF（保留其 `meshdir="assets"` 写法）
- [ ] `assets/robots/<id>/model/assets/` ← 全部网格
- [ ] 记录碰撞精简结论（robot_package.json `notes`）：如 "9 boxes + 4 spheres + 4 wheel cylinders"
- [ ] 验证：`mujoco.MjModel.from_xml_path('model/robot.xml')` 可编译（`nq` 含自由关节 7 + 关节数）

## 2. 契约与配置（30 分钟）

- [ ] `contract.json`（robot-contract-2.0）：`actuated_joints` 顺序 = 上游训练关节序；`default_pose` = 上游 InitialStateCfg
- [ ] `simulation/config.json`：stiffness/damping/torque_limits/**armature**（逐关节，从上游 constants 提取）+ action_scale + command_ranges + `initial_keyframe`
- [ ] `robot_package.json`：capabilities 至少 `["generic_mjlab", "mujoco_sim"]`
- [ ] `training/config.json` + profiles（flat/rough 各一份，command_ranges 从上游 env_cfgs 抄）

## 3. 浏览器仿真（30 分钟）

- [ ] `simulation/scene.xml`（include 模式，参照 go2w/g1；桌面端编译坑见 OPEN_QUESTIONS #1）
- [ ] `backend/simulation_api.py::_configure_browser_actuators`：机器人不在白名单时加分支——
      position/velocity 执行器按契约增益生成（A2 例：`kp/kv/forcerange` 逐关节从 config 表读）
- [ ] 重启后端 → `POST /api/robots/packages/refresh` → `GET /api/simulation/browser-config/<id>` 检查
- [ ] 浏览器 `?robot=<id>&policy=off`：姿态保持站立、无告警

## 4. 验收与元数据（30 分钟）

- [ ] `policy_acceptance.py --package <id> --probe`：verdict pass（默认姿态 + 动作包络）
- [ ] 有策略后：拷入 onnx → policy 条目 contract（observation_kind/obs_dim/action_joint_order/
      default_joint_angles/action_scale_by_joint/clip_actions）→ 跑 acceptance → 5/5 通过
- [ ] 元数据盖章（手工补盖用 `attach_metadata_to_onnx`，参考 go2w/g1 的补盖脚本）

## 5. 提交

- [ ] 一次性提交整个包 + API 改动，commit 信息 `unitree <id>: new robot package with ...`

## 常见坑

- include 场景的 meshdir 双重前缀（OPEN_QUESTIONS #1）——浏览器不受影响；服务端用 MjSpec 组装
- 关节顺序三种流派：SDK 按腿分组（FR,FL,RR,RL）/ isaaclab 按类型分块 / mjlab 实体序——
  一律以**上游训练配置的槽位序**为准写进 `action_joint_order`，元数据校验会兜底
- 上游 XML 无 actuator（执行器在 constants 注入）时，浏览器必须走 `_configure_browser_actuators` 分支
