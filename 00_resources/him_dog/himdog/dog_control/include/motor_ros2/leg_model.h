#pragma once

#include <array>
#include <cstddef>
#include <string>
#include <vector>

namespace motor_ros2 {
namespace leg_model {

constexpr std::size_t kLegCount = 4;
constexpr std::size_t kJointsPerLeg = 3;
constexpr std::size_t kJointCount = kLegCount * kJointsPerLeg;

// ★ 顺序与 IsaacGym 默认 DOF 顺序一致：FL, FR, RL, RR
enum class LegId : std::size_t { FL = 0, FR = 1, RL = 2, RR = 3 };
enum class JointId : std::size_t { J1 = 0, J2 = 1, J3 = 2 };

template<typename T>
struct LegJoints {
  T j1{};
  T j2{};
  T j3{};

  T &at(JointId joint)
  {
    switch (joint) {
      case JointId::J1: return j1;
      case JointId::J2: return j2;
      default: return j3;
    }
  }

  const T &at(JointId joint) const
  {
    switch (joint) {
      case JointId::J1: return j1;
      case JointId::J2: return j2;
      default: return j3;
    }
  }
};

template<typename T>
struct QuadJoints {
  std::array<LegJoints<T>, kLegCount> legs{};

  LegJoints<T> &at(LegId leg)
  {
    return legs[static_cast<std::size_t>(leg)];
  }

  const LegJoints<T> &at(LegId leg) const
  {
    return legs[static_cast<std::size_t>(leg)];
  }
};

struct JointLimit {
  float min_rad;
  float max_rad;
};

struct JointMeta {
  const char *name;
  LegId leg;
  JointId joint;
  std::size_t flat_index;
  JointLimit limit;
};

constexpr std::array<LegId, kLegCount> kLegOrder = {
  LegId::FL, LegId::FR, LegId::RL, LegId::RR
};

constexpr std::size_t flat_index(LegId leg, JointId joint)
{
  return static_cast<std::size_t>(leg) * kJointsPerLeg + static_cast<std::size_t>(joint);
}

// ★ 与 IsaacGym 默认 DOF 顺序一致：FL, FR, RL, RR
constexpr std::array<const char *, kJointCount> kJointNames = {
  "FL_hip", "FL_thigh", "FL_calf",
  "FR_hip", "FR_thigh", "FR_calf",
  "RL_hip", "RL_thigh", "RL_calf",
  "RR_hip", "RR_thigh", "RR_calf"
};

// Joint limits in joint-command space (NOT motor space).
// Left/right legs share identical limits — no sign flipping needed.
// To update: test with manual_joint_pub and fill the value you sent directly.
constexpr std::array<JointLimit, kJointCount> kJointLimits = {
  JointLimit{-1.05f, +1.05f},   // FL_hip
  JointLimit{-1.5f, +1.5f},     // FL_thigh
  JointLimit{-2.4f, +0.6f},     // FL_calf
  JointLimit{-1.05f, +1.05f},   // FR_hip
  JointLimit{-1.5f, +1.5f},     // FR_thigh
  JointLimit{-0.6f, +2.4f},     // FR_calf
  JointLimit{-1.05f, +1.05f},   // RL_hip
  JointLimit{-1.5f, +1.5f},     // RL_thigh
  JointLimit{-2.4f, +0.6f},     // RL_calf
  JointLimit{-1.05f, +1.05f},   // RR_hip
  JointLimit{-1.5f, +1.5f},     // RR_thigh
  JointLimit{-0.6f, +2.4f},     // RR_calf
};

constexpr std::array<JointMeta, kJointCount> kJointMeta = {{
  {kJointNames[0], LegId::FL, JointId::J1, 0,  kJointLimits[0]},
  {kJointNames[1], LegId::FL, JointId::J2, 1,  kJointLimits[1]},
  {kJointNames[2], LegId::FL, JointId::J3, 2,  kJointLimits[2]},
  {kJointNames[3], LegId::FR, JointId::J1, 3,  kJointLimits[3]},
  {kJointNames[4], LegId::FR, JointId::J2, 4,  kJointLimits[4]},
  {kJointNames[5], LegId::FR, JointId::J3, 5,  kJointLimits[5]},
  {kJointNames[6], LegId::RL, JointId::J1, 6,  kJointLimits[6]},
  {kJointNames[7], LegId::RL, JointId::J2, 7,  kJointLimits[7]},
  {kJointNames[8], LegId::RL, JointId::J3, 8,  kJointLimits[8]},
  {kJointNames[9], LegId::RR, JointId::J1, 9,  kJointLimits[9]},
  {kJointNames[10], LegId::RR, JointId::J2, 10, kJointLimits[10]},
  {kJointNames[11], LegId::RR, JointId::J3, 11, kJointLimits[11]}
}};

template<typename T>
inline std::array<T, kJointCount> flatten(const QuadJoints<T> &quad)
{
  std::array<T, kJointCount> out{};
  for (std::size_t li = 0; li < kLegCount; ++li) {
    const LegId leg = static_cast<LegId>(li);
    const LegJoints<T> &src = quad.at(leg);
    out[flat_index(leg, JointId::J1)] = src.j1;
    out[flat_index(leg, JointId::J2)] = src.j2;
    out[flat_index(leg, JointId::J3)] = src.j3;
  }
  return out;
}

template<typename T>
inline QuadJoints<T> unflatten(const std::array<T, kJointCount> &flat)
{
  QuadJoints<T> out{};
  for (std::size_t li = 0; li < kLegCount; ++li) {
    const LegId leg = static_cast<LegId>(li);
    LegJoints<T> &dst = out.at(leg);
    dst.j1 = flat[flat_index(leg, JointId::J1)];
    dst.j2 = flat[flat_index(leg, JointId::J2)];
    dst.j3 = flat[flat_index(leg, JointId::J3)];
  }
  return out;
}

template<typename T>
inline std::vector<T> flatten_to_vector(const QuadJoints<T> &quad)
{
  const auto flat = flatten(quad);
  return std::vector<T>(flat.begin(), flat.end());
}

inline std::vector<std::string> joint_names_vector()
{
  return std::vector<std::string>(kJointNames.begin(), kJointNames.end());
}

inline bool has_canonical_joint_order(const std::vector<std::string> &names)
{
  if (names.size() != kJointCount) return false;
  for (std::size_t i = 0; i < kJointCount; ++i) {
    if (names[i] != kJointNames[i]) return false;
  }
  return true;
}

// 启动偏移量：电机启动后先到达的位置（joint-command 空间，相对于电机零位）
// ★ 顺序与 kJointNames 一致：FL, FR, RL, RR
// ★ 这些值 = 训练代码中的 default_joint_angles（站立姿态）
// ★ 启动偏移量：电机从0位 ramp 到的目标位置（joint-command 空间）
//   hip/thigh: 直接等于 URDF 默认角度
//   calf:      包含 2:1 减速比的实际电机空间角度（站立时电机编码器读数）
constexpr std::array<float, kJointCount> kStartupOffset = {
  -0.1f, -0.8f,  2.6f,     // FL_hip, FL_thigh, FL_calf
   0.1f,  0.8f, -2.6f,     // FR_hip, FR_thigh, FR_calf
   0.1f, -1.0f,  2.6f,     // RL_hip, RL_thigh, RL_calf
  -0.1f,  1.0f, -2.6f      // RR_hip, RR_thigh, RR_calf
};

static_assert(kJointCount == 12, "Joint count must remain 12.");
static_assert(kJointCount == kLegCount * kJointsPerLeg, "Invalid leg/joint dimensions.");
static_assert(flat_index(LegId::FL, JointId::J1) == 0, "FL_J1 index mismatch");
static_assert(flat_index(LegId::FR, JointId::J1) == 3, "FR_J1 index mismatch");
static_assert(flat_index(LegId::RL, JointId::J1) == 6, "RL_J1 index mismatch");
static_assert(flat_index(LegId::RR, JointId::J1) == 9, "RR_J1 index mismatch");

}  // namespace leg_model
}  // namespace motor_ros2