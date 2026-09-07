# Open Questions（待决策事项）

遇到无法自动决策的问题记录在这里，不强行实施。

## 1. scene.xml 桌面端编译失败（include + meshdir 双重前缀）

- 现象：`assets/robots/*/simulation/scene.xml`（`<include file="../model/robot.xml"/>` +
  `<compiler meshdir="model/assets"/>`）在桌面 mujoco 3.11 下报
  `Error opening file 'model/assets/assets/robots/<pkg>/model/<mesh>'`——include 机制把
  mesh 的 file 属性改写成了 CWD 相对路径，meshdir 又叠加了一次前缀。
- 影响：仅桌面端直接 `MjModel.from_xml_path(scene.xml)` 受影响；浏览器（虚拟 FS 按包 API
  路径取网格）与服务器端 `ContractMujocoEnv`（用 `contract.urdf.path` 加载模型）均不受影响。
  验收器 `policy_acceptance.py` 也改为直接编译 `model/robot.xml` + MjSpec 追加地板。
- 候选方案：
  1. 服务器端场景统一改走 MjSpec 组装（代码生成地板/障碍，不再依赖 scene.xml include）；
  2. 或生成 scene.xml 时把 mesh 引用写成绝对/包根相对路径（破坏可迁移性）；
  3. 或升级/固定 mujoco 版本后重新验证其 include 路径语义。
- 待决策：选哪条路线；scene.xml 是否保留为"仅文档化声明"。

## 2. G1 浏览器"局部 vx"读数疑似偏差

- 现象：unitree-velocity 策略在浏览器里指令 vx=0.15/0.30 时 HUD"局部 vx"持续 ~0.79；
  而 Python 验收器（policy_acceptance.py，qvel 回退路径测速）同一策略全模式跟踪误差 ≤0.12。
- 怀疑点：浏览器 `readImuSample` 的 cvel 线速度修正路径（绕 subtree COM 换算到 body origin）。
- 下一步：用 `?debug=1` 的 `startFrameLog` 导出 obs 与 qpos 位移对拍，定位是测量问题还是
  策略真实超调。

## 3. 每 checkpoint 导出的产物管理

- 现状：save 钩子每次保存都写 `<checkpoint-dir>/<iter>.onnx` 并盖章；长训练会产生大量
  几百 KB 的 onnx 文件。
- 待决策：是否只保留最新 N 个 onnx（滚动清理），或仅对 `model_final` 保留。

## 4. IsaacLab 第二后端

- robot_lab 的双后端适配层已证明可行，但 legged_studio 训练目前只有 mjlab worker。
  若要加 IsaacLab 后端：contract.json 的中立数据层已经够用（增益/默认角/限位同源），
  需要新增 `adapters/isaaclab` builder + venv；属大版本决策。
