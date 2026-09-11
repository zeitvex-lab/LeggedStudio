// ========================================================================================
// pick_place_actor.hpp — 蹲下+吸盘 单次取/放动作编排器（header-only，不依赖 ROS）
// ========================================================================================
//
// 抽自 navigation_dog / dog_nav_fallback 的 PICKUP / PLACE_BOX 状态体。
// 这两个宿主里「蹲下启动 → 保持期触发吸盘 → 蹲下完成 → 推进」的逐 tick 编排
// 逐字节相同，本类把它收口为一个不依赖 ROS 的纯逻辑驱动器：
//
//   - 宿主拿到 BoxInfo 后调 StartPickup/StartPlace（传方向），得到首帧（含 policy_mode=true）
//   - 之后每 tick 调 Tick(now)，把返回 frame 落到自己的 ROS 发布器上
//   - Tick 返回 action_done=true 时，本次取/放动作全部完成，宿主调自己的轮次推进逻辑
//
// 内部拥有 SquatController + SuckerController + 取放时序 flags，flags 在动作完成时自动复位，
// 宿主无需（也不应）再手动重置它们。
//
// 时序契约（与原 PICKUP/PLACE_BOX body 严格一致）:
//   首帧: StartPickup/StartPlace 返回  policy_mode=true + 站立姿态（蹲下插值起点）
//   Tick: 蹲下IsActive → 发 squat.Update 帧；进入保持期(phase1) → 触发 sucker.StartPick/StartPlace
//         蹲下完成(!IsActive) && 吸盘完成(!IsActive) → action_done=true，内部复位
//
// ★ 首帧不再调 Tick：宿主调完 StartXxx 当帧必须 break，下一帧起才 Tick，
//    否则蹲下插值会少推进一帧（与原「首次进入块执行完即 break」语义一致）。
//
#ifndef DOG_NAV_PICK_PLACE_ACTOR_HPP_
#define DOG_NAV_PICK_PLACE_ACTOR_HPP_

#include <string>
#include <optional>
#include <array>

#include "dog_nav/squat_controller.hpp"
#include "dog_nav/sucker_controller.hpp"

namespace dog_nav
{

// ========================================================================================
// PickPlaceActor — 蹲下+吸盘 单次取/放动作编排器
// ========================================================================================
class PickPlaceActor
{
public:
  // 复用 SquatController 的 Frame（has_pose + pose + 可选 policy_mode），避免重复定义
  using Frame = SquatController::Frame;

  // Tick 的返回：本帧该发什么 + 本次动作是否全部完成
  struct TickResult
  {
    Frame frame;               // 本帧该发的（ Idle / 完成帧 返回空 frame）
    bool action_done{false};   // 取/放动作全部完成（蹲下+吸盘都结束）
  };

  PickPlaceActor() = default;

  // ========================================================================================
  // 配置（透传给内部 squat_ctrl_ / sucker_）
  // ========================================================================================
  void ConfigureSquat(const std::array<double, SquatController::kNumDofs> & stand,
                      const std::array<double, SquatController::kNumDofs> & squat,
                      double interp_sec, double hold_sec)
  {
    squat_ctrl_.SetStandPose(stand);
    squat_ctrl_.SetSquatPose(squat);
    squat_ctrl_.SetInterpSec(interp_sec);
    squat_ctrl_.SetHoldSec(hold_sec);
  }

  void ConfigureSucker(double move_sec, double hold_sec)
  {
    sucker_.SetMoveSec(move_sec);
    sucker_.SetHoldSec(hold_sec);
  }

  bool OpenSucker(const std::string & port, int baudrate) { return sucker_.Open(port, baudrate); }
  void HomeSucker() { sucker_.Home(); }   // 可选：归位到存储位、泵 OFF

  // ========================================================================================
  // StartPickup — 启动一次取箱动作，返回首帧
  // ========================================================================================
  // direction: "left"/"right"，决定保持期内 sucker_.StartPick 的吸盘侧
  // 首帧含 policy_mode=true（挂起 RL）+ 站立姿态（蹲下插值起点）
  //
  Frame StartPickup(const std::string & direction, double now_sec)
  {
    mode_ = Mode::Pick;
    pickup_executed_ = true;
    pickup_suck_started_ = false;
    sucker_direction_ = direction;
    direction_ = direction;
    return squat_ctrl_.StartSquat(now_sec);
  }

  // ========================================================================================
  // StartPlace — 启动一次放箱动作，返回首帧
  // ========================================================================================
  // 进入放箱时箱应已吸在存储位（泵 ON），由 squat 保持期内的 sucker_.StartPlace 释放
  //
  Frame StartPlace(const std::string & direction, double now_sec)
  {
    mode_ = Mode::Place;
    place_executed_ = true;
    place_suck_started_ = false;
    sucker_direction_ = direction;
    direction_ = direction;
    return squat_ctrl_.StartSquat(now_sec);
  }

  // ========================================================================================
  // Tick — 每帧推进（首帧除外）
  // ========================================================================================
  // 顺序镜像原 PICKUP/PLACE_BOX body:
  //   1) 完成判定 !squat.IsActive && *_executed && *_suck_started && !sucker.IsActive
  //      → 复位 flags + mode_=Idle，action_done=true
  //   2) 蹲下进行中 → 发 squat.Update 帧；进保持期触发吸盘；吸盘进行中则同步推进
  //   3) 其它（蹲下已结束但吸盘未完成，或异常配置）→ 空 frame
  //
  TickResult Tick(double now_sec)
  {
    TickResult tr;
    if (mode_ == Mode::Idle) return tr;

    const bool pick = (mode_ == Mode::Pick);
    const bool executed = pick ? pickup_executed_ : place_executed_;
    const bool suck_started = pick ? pickup_suck_started_ : place_suck_started_;

    // 1) 完成判定
    if (!squat_ctrl_.IsActive() && executed && suck_started && !sucker_.IsActive()) {
      Reset();
      tr.action_done = true;
      return tr;
    }

    // 2) 蹲下进行中
    if (squat_ctrl_.IsActive()) {
      tr.frame = squat_ctrl_.Update(now_sec);
      // 进入保持期且吸盘未启动 → 触发吸盘动作
      if (squat_ctrl_.IsInHoldPhase() && !suck_started && sucker_direction_.has_value()) {
        if (pick) {
          sucker_.StartPick(*sucker_direction_, now_sec);
          pickup_suck_started_ = true;
        } else {
          sucker_.StartPlace(*sucker_direction_, now_sec);
          place_suck_started_ = true;
        }
      }
      // 吸盘进行中 → 同步推进（蹲下保持期会持续发蹲下姿态）
      if (sucker_.IsActive()) sucker_.Update(now_sec);
    }
    return tr;
  }

  // ========================================================================================
  // 状态查询
  // ========================================================================================
  bool IsIdle() const { return mode_ == Mode::Idle; }
  bool IsRunning() const { return mode_ != Mode::Idle; }
  const std::string & Direction() const { return direction_; }

  // 供宿主/测试查询内部控制器状态（如 IsHolding、Phase、Sucker 模式）
  const SquatController & Squat() const { return squat_ctrl_; }
  const SuckerController & Sucker() const { return sucker_; }

private:
  // 动作完成时复位全部 flags —— 替代原宿主第 2 层散落的 *=false 重置
  void Reset()
  {
    mode_ = Mode::Idle;
    pickup_executed_ = false;
    pickup_suck_started_ = false;
    place_executed_ = false;
    place_suck_started_ = false;
    sucker_direction_.reset();
    direction_.clear();
  }

  enum class Mode { Idle, Pick, Place };

  Mode mode_{Mode::Idle};
  bool pickup_executed_{false};
  bool pickup_suck_started_{false};
  bool place_executed_{false};
  bool place_suck_started_{false};
  std::optional<std::string> sucker_direction_;
  std::string direction_;

  SquatController squat_ctrl_;
  SuckerController sucker_;
};

}  // namespace dog_nav

#endif  // DOG_NAV_PICK_PLACE_ACTOR_HPP_
