"""族级 Imitation（动作模仿 / AMP）技能。

来源：`go2_skills/amp_dreamwaq/{config,mdp,motion,rl}.py`（2026-09-24 上移）。
除下列去机型化改动外**逐字一致**：

* 判别器状态的关节序：模块常量 `JOINT_NAMES` → 观测项/算法参数 `joint_order`
  （由调用方的契约绑定传入，见 `binding.QuadrupedSkillBinding.joint_order`）；
* 后腿髋限位：写死的 `RL/RR_hip_joint` → 由绑定按**族角色**派生的关节名
  （`binding.joint_names(role="hip_abduction", legs=binding.rear_legs)`）；
* 动作加载器：`Path(__file__).parents[3]/assets/motions/go2_amp` → `motion_root`
  参数 + 关节数/腿数（帧布局由族声明派生，见 `motion.py`）；
* AMP 超参与机型身份：由 `profile.AmpProfile` 携带。

**族级口径**：本层不认识任何机型 —— 判别器状态维（`2×关节数+7`）、后腿髋关节名、
专家数据目录都来自契约/MJCF/调用方；AMP 的奖励整形与判别器更新是**唯一实现**，
宿主可以是任何速度跟踪任务（go2 用 DreamWaQ 宿主；go1 用它的 rough velocity 宿主）。
"""
