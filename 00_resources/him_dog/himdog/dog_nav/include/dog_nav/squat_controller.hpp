// ========================================================================================
// squat_controller.hpp — 蹲下/起立姿态控制器（header-only，纯逻辑，不依赖 ROS）
// ========================================================================================
//
// 封装「挂起 RL → 蹲下 → 保持 → 站起 → 恢复 RL」的完整时序，用于取箱/放箱。
// 与 dog_policy_test_13 的 /policy_mode 信号联动：
//   挂起期间 policy 停止发 /joint_states，nav 成为唯一发布者。
//
// 设计：控制器只算「每帧该发什么姿态 / 何时切换 policy_mode」，不做 ROS 发布。
//      Update() 返回一个 Frame，nav 据此调自己的 ROS 发布器。这样控制器可单测、可复用。
//
// 时序（StartSquat 启动，Update 每帧推进）:
//   phase 0  站→蹲线性插值          等 interp_sec
//   phase 1  保持蹲下姿态            等 hold_sec   ← ★ 上层在此期间做吸盘动作
//   phase 2  蹲→站线性插值          等 interp_sec
//   phase 3  完成（Update 末尾返回 policy_mode=false 恢复 RL）
//
// policy_mode 信号时机:
//   - StartSquat 返回的 Frame 带 policy_mode=true（挂起）
//   - phase 2 结束时返回的 Frame 带 policy_mode=false（恢复）
//
// 用法（nav 侧）:
//   SquatController sc;
//   sc.SetStandPose(stand); sc.SetSquatPose(squat);
//   sc.SetInterpSec(1.0); sc.SetHoldSec(7.0);   // hold 要 ≥ 吸盘全程时间
//
//   // 启动（取/放通用）
//   auto f0 = sc.StartSquat(now);
//   ApplyFrame(f0);                              // 发 policy_mode + 初始站立姿态
//
//   while (sc.IsActive()) {
//     auto f = sc.Update(now);
//     ApplyFrame(f);
//     if (sc.IsInHoldPhase() && !sucker_started) {
//       sucker_.StartPick(dir, now); sucker_started = true;   // 保持期触发吸盘
//     }
//     if (sucker_.IsActive()) sucker_.Update(now);
//   }
//
// 关节顺序（js_pos 空间，12 维）:
//   FL_hip, FL_thigh, FL_calf, FR_hip, FR_thigh, FR_calf,
//   RL_hip, RL_thigh, RL_calf, RR_hip, RR_thigh, RR_calf
//
#ifndef DOG_NAV_SQUAT_CONTROLLER_HPP_
#define DOG_NAV_SQUAT_CONTROLLER_HPP_

#include <array>
#include <algorithm>
#include <optional>
#include <cstdio>
#include <cstdarg>

namespace dog_nav
{

// ========================================================================================
// SquatController — 蹲下/起立姿态控制器
// ========================================================================================
class SquatController
{
public:
  static constexpr int kNumDofs = 12;

  // --------------------------------------------------------------------------------------
  // Frame — Update/StartSquat 的返回值，描述本帧 nav 该做什么
  // --------------------------------------------------------------------------------------
  struct Frame
  {
    bool has_pose{false};                          // 是否要发 /joint_states
    std::array<double, kNumDofs> pose{};           // 要发的姿态（js_pos 空间）
    std::optional<bool> policy_mode;               // 是否要发 /policy_mode（true=挂起,false=恢复）
  };

  SquatController() = default;

  // ========================================================================================
  // 配置（站姿/蹲姿 12 维 js_pos，插值/保持时间 秒）
  // ========================================================================================
  void SetStandPose(const std::array<double, kNumDofs> & p) { stand_pose_ = p; }
  void SetSquatPose(const std::array<double, kNumDofs> & p) { squat_pose_ = p; }
  void SetInterpSec(double s) { interp_sec_ = std::max(0.01, s); }
  void SetHoldSec(double s) { hold_sec_ = std::max(0.0, s); }

  const std::array<double, kNumDofs> & StandPose() const { return stand_pose_; }
  const std::array<double, kNumDofs> & SquatPose() const { return squat_pose_; }
  double InterpSec() const { return interp_sec_; }
  double HoldSec() const { return hold_sec_; }

  // ========================================================================================
  // StartSquat — 启动蹲下动作（取/放通用），返回首帧（含 policy_mode=true + 初始站立姿态）
  // ========================================================================================
  Frame StartSquat(double now_sec)
  {
    active_ = true;
    phase_ = 0;
    phase_start_ = now_sec;
    Frame f;
    f.has_pose = true;
    f.pose = stand_pose_;        // 插值起点 = 站立姿态
    f.policy_mode = true;        // 挂起 policy
    Log("★ 蹲下启动: 挂起RL + 站→蹲插值 (%.1fs)", interp_sec_);
    return f;
  }

  // ========================================================================================
  // Update — 每帧推进，返回本帧该发什么（姿态 + 可能的 policy_mode 切换）
  // ========================================================================================
  Frame Update(double now_sec)
  {
    Frame f;
    if (!active_) return f;

    double elapsed = now_sec - phase_start_;

    if (phase_ == 0) {
      // 站→蹲插值
      double t = std::clamp(elapsed / interp_sec_, 0.0, 1.0);
      f.has_pose = true;
      f.pose = Interpolate(stand_pose_, squat_pose_, t);
      if (elapsed >= interp_sec_) {
        phase_ = 1;
        phase_start_ = now_sec;
        Log("★ 已蹲下, 保持 %.1fs（吸盘动作期间）", hold_sec_);
      }
    } else if (phase_ == 1) {
      // 保持蹲下姿态（持续发，确保 policy 恢复瞬间不跳变）
      f.has_pose = true;
      f.pose = squat_pose_;
      if (elapsed >= hold_sec_) {
        phase_ = 2;
        phase_start_ = now_sec;
        Log("★ 蹲→站插值 (%.1fs)", interp_sec_);
      }
    } else if (phase_ == 2) {
      // 蹲→站插值
      double t = std::clamp(elapsed / interp_sec_, 0.0, 1.0);
      f.has_pose = true;
      f.pose = Interpolate(squat_pose_, stand_pose_, t);
      if (elapsed >= interp_sec_) {
        phase_ = 3;
        phase_start_ = now_sec;
        f.policy_mode = false;       // 恢复 policy
        f.pose = stand_pose_;        // 最后一帧站立兜底
        active_ = false;
        Log("★ 蹲下完成: 已站起 + 恢复RL");
      }
    }
    return f;
  }

  // ========================================================================================
  // 状态查询
  // ========================================================================================
  bool IsActive() const { return active_; }

  // 是否在保持期（phase 1）—— 上层据此触发吸盘动作
  bool IsInHoldPhase() const { return active_ && phase_ == 1; }

  int Phase() const { return phase_; }

private:
  // 线性插值两姿态（t=0→a, t=1→b）
  static std::array<double, kNumDofs> Interpolate(
    const std::array<double, kNumDofs> & a,
    const std::array<double, kNumDofs> & b, double t)
  {
    std::array<double, kNumDofs> out;
    for (int i = 0; i < kNumDofs; ++i) out[i] = a[i] + (b[i] - a[i]) * t;
    return out;
  }

  // 简单日志（printf；接 ROS 日志请替换此函数体为 RCLCPP_INFO）
  void Log(const char * fmt, ...) const
  {
    std::printf("[Squat] ");
    va_list ap;
    va_start(ap, fmt);
    std::vprintf(fmt, ap);
    va_end(ap);
    std::printf("\n");
    std::fflush(stdout);
  }

  // ========================================================================================
  // 成员
  // ========================================================================================
  std::array<double, kNumDofs> stand_pose_{};   // 站立姿态（默认全零 = 默认站姿）
  std::array<double, kNumDofs> squat_pose_{};   // 蹲下姿态（实测标定）
  double interp_sec_{1.0};                      // 站↔蹲插值时间（秒）
  double hold_sec_{1.0};                        // 蹲下保持时间（≥ 吸盘全程）

  bool active_{false};
  int phase_{0};                                // 0=站→蹲, 1=保持, 2=蹲→站, 3=完成
  double phase_start_{0.0};
};

}  // namespace dog_nav

#endif  // DOG_NAV_SQUAT_CONTROLLER_HPP_
