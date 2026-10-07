"""**离线模仿工具链**（N1，`00_know/06` §16.2）—— 动作/模仿的"实链路"落点。

## 为什么是它

竞品取证（§12.3）里 LainLab 的 `toolchain/{bc,dagger}.py` 是本仓**唯一缺的实链路**：
数据进来 → 校准 → 离线模仿训练 → 导出。本包先落**前两段**（数据层），因为它们是
**控制面可验证**的纯数据工作，而且挡的是最贵的一类错 —— 关节列错位不会报错，只会训出
一个"看着像、其实错位"的策略。

## 两半的分工（诚实边界）

* **已落**（本包，`motion_io`）：CSV/NPZ 动作导入 + **关节列校验**（对标 LainLab
  `calibrate.py` 的口径：列名必须与契约 `action.joint_order` 同名同序）；
* **未落（env-gated）**：BC / DAgger 训练档与 ONNX 导出 —— 需要训练栈（隔离 venv / GPU）。
  它们的挂载点（`registry/plugins/skill/imitation_offline.json`）与 `verify` 声明留到那一步，
  避免现在放一份"声明了却没人能跑"的清单。

依赖纪律：本包**只依赖 numpy + stdlib**（不 import mjlab / torch），所以能在无训练栈的
控制面环境里被 CI 直接跑（回归锁 `backend/test_toolchain_motion_io.py`）。
"""
