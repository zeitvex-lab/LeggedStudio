#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include "dog_control/msg/motor_feedback.hpp"


// ros2 run dog_policy_test dog_policy_test_5 --ros-args --params-file ./src/dog_policy_test/config/policy_params.yaml

#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>
#include <memory>
#include <thread>
#include <atomic>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>

#include <onnxruntime_cxx_api.h>


// ========================================================================================
// 数据流全景（dog_control ↔ dog_policy_test）
// ========================================================================================
//
// 1. dog_control/main.cpp 发布 /motor_feedback（200Hz）
//    - msg.position[i] = wrap_to_pi(motor_encoder * sign - offset)
//      即已在 joint-command 空间中减去了 kFixedJointCmdOffsets，站立时接近0
//    - msg.velocity[i] = 原始电机编码器速度
//    - 电机反馈顺序: FL, FR, RL, RR（与 IsaacGym DOF 顺序一致）
//
// 2. 本节点(dog_policy_test) 接收 /motor_feedback:
//    - 发布顺序(FL,FR,RL,RR) 与 IsaacGym 模型顺序一致，无需重排
//    - msg.position 已减去offset，直接就是模型偏差角（hip/thigh）
//        hip/thigh: 模型偏差角 = msg.position（直接使用）
//        calf:      模型偏差角 = msg.position / 2    （2:1减速比）
//    - 角速度同理:
//        hip/thigh: 模型角速度 = 原始速度
//        calf:      模型角速度 = 原始速度 / 2
//


// ★★★ 关键理解：机械零位 vs URDF零位 ★★★
//
// 关系：机械零位(encoder=0) = URDF零位(joint_angle=0) + default_dof_pos
//
// 站立时（机械零位）：
//   encoder = 0
//   URDF_angle = default_dof_pos  (因为机械零位偏移了 default_dof_pos)
//   (dof_pos - default_dof_pos) = 0  ← 这就是模型输入！
//
// 训练代码 (legged_robot.py):
//   obs_dof = (dof_pos - default_dof_pos) * scale
//   dof_pos 是基于 URDF 的角度，所以 (dof_pos - default_dof_pos) 就是"偏离 default 的偏差"
//
// dog_control 发布的 msg.position:
//   因为机械零位 = URDF零位 + default_dof_pos
//   所以 encoder = URDF_angle - default_dof_pos = (dof_pos - default_dof_pos)
//   也就是说 msg.position 直接就是模型偏差角！
//
// 结论：msg.position 直接就是 (dof_pos - default_dof_pos)，无需加减 offset

// default_joint_angles = { # = target angles [rad] when action = 0.0
//     'FL_hip_joint': -0.1,   # [rad]
//     'RL_hip_joint': 0.1,    # [rad]
//     'FR_hip_joint': 0.1,    # [rad]
//     'RR_hip_joint': -0.1,   # [rad]
//     'FL_thigh_joint': -0.8, # [rad]
//     'RL_thigh_joint': -1.,  # [rad]
//     'FR_thigh_joint': 0.8,  # [rad]
//     'RR_thigh_joint': 1.,   # [rad]
//     'FL_calf_joint': -1.5,  # [rad]
//     'RL_calf_joint': -1.5,  # [rad]
//     'FR_calf_joint': 1.5,   # [rad]
//     'RR_hip_joint': 1.5,    # [rad]
// }


//
// 3. 本节点 推理后发布 /joint_states:
//        hip/thigh: js_pos = 模型偏差角
//        calf:      js_pos = 2 × 模型偏差角
//
// 4. dog_control/main.cpp 接收 /joint_states:
//    - motor_target = js_pos + kFixedJointCmdOffsets[idx]   (compute_motor_cmd_target)
//    - 然后发送给电机执行
//
// ========================================================================================
// DOF 顺序说明
// ========================================================================================
//
// ★ 统一使用 IsaacGym 默认 DOF 顺序：FL, FR, RL, RR
//   FL_hip, FL_thigh, FL_calf   索引 0,1,2
//   FR_hip, FR_thigh, FR_calf   索引 3,4,5
//   RL_hip, RL_thigh, RL_calf   索引 6,7,8
//   RR_hip, RR_thigh, RR_calf   索引 9,10,11
//
// ★ dog_control (leg_model.h) 和本节点均使用此顺序，无需重排！
//
// ========================================================================================
// 减速比说明
// ========================================================================================
// hip, thigh: 无减速比，电机方向=URDF方向
// calf:       2:1 减速比，因此 calf 的编码器值需要除以2

// ========================================================================================
// 架构说明（三节奏）
// ========================================================================================
//
// 1. 传感器回调（~200Hz）：
//    - ImuCallback: 只更新 latest_imu_raw_，尽快返回
//    - MotorFeedbackCallback: 只更新 latest_motor_raw_，尽快返回
//    - 回调内只做短暂加锁 + 数据拷贝，不做任何计算
//
// 2. policy_timer_（50Hz / 20ms）：
//    - 拷贝最新传感器状态
//    - 滤波（IMU gyro 低通+去零飘，电机位置低通，电机速度低通+去零飘）
//    - 构造 observation
//    - ONNX 推理
//    - action 后处理
//    - 更新 last_motor_cmd_
//
// 3. publish_timer_（200Hz / 5ms）：
//    - 拷贝 last_motor_cmd_
//    - 200Hz 低通平滑
//    - 发布 /joint_states
//
// 等待模式（未按 y）：publish_timer 发布全零 /joint_states
//


namespace
{
// =========================
// 1. 常量定义区
// =========================

// 机器人自由度数量（12 个关节）
constexpr std::size_t kNumDofs = 12;

// 动作维度（一般和关节数一致）
constexpr std::size_t kNumActions = 12;

// 指令维度：vx, vy, wz
constexpr std::size_t kNumCommands = 3;

// IMU 角速度维度
constexpr std::size_t kImuDim = 3;

// 重力投影向量维度
constexpr std::size_t kGravityDim = 3;

// 高度指令维度
constexpr std::size_t kHeightCommandDim = 1;

// 46 维模式：含 height command
constexpr std::size_t kOneStepObsDim46 =
  kNumCommands + kImuDim + kGravityDim + kNumDofs + kNumDofs + kNumActions + kHeightCommandDim;  // = 46

// 45 维模式：不含 height command
constexpr std::size_t kOneStepObsDim45 =
  kNumCommands + kImuDim + kGravityDim + kNumDofs + kNumDofs + kNumActions;  // = 45

// 历史帧数：legged_gym 里常见为 6 帧
constexpr std::size_t kObsHistoryLength = 6;

// 历史拼接后的总维度
constexpr std::size_t kHistoryObsDim46 = kObsHistoryLength * kOneStepObsDim46;  // 6 × 46 = 276
constexpr std::size_t kHistoryObsDim45 = kObsHistoryLength * kOneStepObsDim45;  // 6 × 45 = 270

// 高度指令归一化参数
constexpr double kBaseHeightTarget = 0.25;
constexpr double kHeightObsScale = 0.1;

// observation 裁剪范围，防止数值过大
constexpr float kClipObs = 100.0f;

// 这里是command的缩放
constexpr std::array<float, kNumCommands> kCommandScale{2.0f, 2.0f, 0.25f};

// 关节名称到索引的固定映射
// ★ 按 IsaacGym 默认 DOF 顺序：FL, FR, RL, RR（RL 在 RR 前面）
constexpr std::array<const char *, kNumDofs> kJointNames{
  "FL_hip", "FL_thigh", "FL_calf",    // FL → 0,1,2
  "FR_hip", "FR_thigh", "FR_calf",    // FR → 3,4,5
  "RL_hip", "RL_thigh", "RL_calf",    // RL → 6,7,8
  "RR_hip", "RR_thigh", "RR_calf"     // RR → 9,10,11
};

// ----- Action 后处理参数 -----
// 以下参数均从 YAML 读取（类成员变量）：
//   kActionDeltaMax, kActionScale

// ----- 输入滤波参数 -----
// 以下参数均从 YAML 读取（类成员变量）：
//   kImuGyroLpfAlpha, kImuGyroBiasAlpha, kMotorPosLpfAlpha,
//   kMotorVelLpfAlpha, kMotorVelBiasAlpha

// ----- 静止死区参数 -----
// 以下参数均从 YAML 读取（类成员变量）：
//   kStandstillThreshold, kStandstillDecay, kStandstillActionThreshold

// ----- 200Hz 输出端低通滤波 -----
// 以下参数从 YAML 读取（类成员变量）：
//   kPublishLowPassAlpha

// =========================
// 2. 数据结构定义区
// =========================

// observation 各部分的缩放参数
struct ObsScales
{
  double ang_vel{0.25};   // 角速度缩放
  double dof_pos{1.0};    // 关节位置缩放
  double dof_vel{0.05};   // 关节速度缩放
  double lin_vel{2.0};    // 线速度缩放（当前代码暂未使用）
  double commands{1.0};   // 指令缩放（当前代码使用 kCommandScale）
};

// IMU 状态
struct ImuState
{
  // 四元数格式：[w, x, y, z]
  std::array<double, 4> quaternion{{1.0, 0.0, 0.0, 0.0}};

  // 角速度 [wx, wy, wz]
  std::array<double, 3> gyroscope{{0.0, 0.0, 0.0}};
};

// 电机状态
struct MotorState
{
  // 关节位置
  std::array<double, kNumDofs> q{};

  // 关节速度
  std::array<double, kNumDofs> dq{};

  // 估计力矩
  std::array<double, kNumDofs> tau_est{};
};

// 机器人整体状态
struct RobotState
{
  ImuState imu;
  MotorState motor_state;

  // 命令输入 [vx, vy, wz]
  std::array<double, 3> commands{};

  // 基座线速度（当前代码未实际使用）
  std::array<double, 3> base_lin_vel{};

  // 世界坐标系重力向量投影到机体坐标系的结果
  std::array<double, 3> projected_gravity{{0.0, 0.0, -1.0}};

  // 外部扰动（当前代码未使用）
  std::array<double, 3> disturbance{};

  // 高度指令（默认 0.25，对应 base_height_target）
  double height_command{0.25};
};

// =========================
// 3. 工具函数区
// =========================

/**
 * @brief 判断某个关节索引是否为 calf（减速比 2:1）
 */
inline bool IsCalfJoint(std::size_t joint_idx)
{
  return (joint_idx % 3) == 2;
}

/**
 * @brief 将 msg.position 转换为模型偏差角（用于观测输入）
 */
inline double MsgPosToModelDeviation(double raw_motor_pos, std::size_t joint_idx)
{
  if (IsCalfJoint(joint_idx)) {
    return raw_motor_pos / 2.0;
  }
  return raw_motor_pos;
}

/**
 * @brief 将电机编码器速度转换为模型角速度（用于观测输入）
 */
inline double MsgVelToModelVel(double raw_motor_vel, std::size_t joint_idx)
{
  if (IsCalfJoint(joint_idx)) {
    return raw_motor_vel / 2.0;
  }
  return raw_motor_vel;
}

/**
 * @brief 将模型偏差角转换为 /joint_states 位置（用于指令输出）
 */
inline double ModelDeviationToJsPos(double model_deviation, std::size_t joint_idx)
{
  if (IsCalfJoint(joint_idx)) {
    return 2.0 * model_deviation;
  }
  return model_deviation;
}

/**
 * @brief 将世界坐标系下的向量旋转到机体坐标系
 */
std::array<double, 3> RotateWorldToBody(
  const std::array<double, 4> & quat_wxyz,
  const std::array<double, 3> & vec_world)
{
  const double w = quat_wxyz[0];
  const double x = quat_wxyz[1];
  const double y = quat_wxyz[2];
  const double z = quat_wxyz[3];

  const double r00 = 1.0 - 2.0 * (y * y + z * z);
  const double r01 = 2.0 * (x * y - z * w);
  const double r02 = 2.0 * (x * z + y * w);
  const double r10 = 2.0 * (x * y + z * w);
  const double r11 = 1.0 - 2.0 * (x * x + z * z);
  const double r12 = 2.0 * (y * z - x * w);
  const double r20 = 2.0 * (x * z - y * w);
  const double r21 = 2.0 * (y * z + x * w);
  const double r22 = 1.0 - 2.0 * (x * x + y * y);

  return {
    r00 * vec_world[0] + r01 * vec_world[1] + r02 * vec_world[2],
    r10 * vec_world[0] + r11 * vec_world[1] + r12 * vec_world[2],
    r20 * vec_world[0] + r21 * vec_world[1] + r22 * vec_world[2]};
}

/**
 * @brief 构造单步 observation（45 或 46 维）
 *
 * 拼接顺序（与 IsaacGym compute_observations 一致）：
 * 1) commands (3): vx, vy, wz
 * 2) imu gyro (3)
 * 3) projected gravity (3)
 * 4) joint pos relative to default (12)
 * 5) joint vel (12)
 * 6) previous action (12)
 * 7) height command (1): (height_cmd - 0.25) / 0.1   [仅 46 维模式]
 */
std::vector<float> BuildOneStepObservation(
  const RobotState & state,
  const ObsScales & obs_scales,
  const std::array<float, kNumActions> & last_actions,
  bool include_height_command)
{
  const std::size_t dim = include_height_command ? kOneStepObsDim46 : kOneStepObsDim45;
  std::vector<float> obs;
  obs.reserve(dim);

  // 1) commands: vx, vy, wz
  for (std::size_t i = 0; i < kNumCommands; ++i) {
    obs.push_back(static_cast<float>(state.commands[i] * kCommandScale[i]));
  }

  // 2) imu gyro
  for (double ang_vel : state.imu.gyroscope) {
    obs.push_back(static_cast<float>(ang_vel * obs_scales.ang_vel));
  }

  // 3) projected gravity
  for (double g : state.projected_gravity) {
    obs.push_back(static_cast<float>(g));
  }

  // 4) joint pos（基于 URDF 的偏差角）
  for (std::size_t i = 0; i < kNumDofs; ++i) {
    obs.push_back(static_cast<float>(state.motor_state.q[i] * obs_scales.dof_pos));
  }

  // 5) joint vel
  for (double dq : state.motor_state.dq) {
    obs.push_back(static_cast<float>(dq * obs_scales.dof_vel));
  }

  // 6) previous action
  for (float a : last_actions) {
    obs.push_back(a);
  }

  // 7) height command: (height_cmd - 0.25) / 0.1   [仅 46 维模式]
  if (include_height_command) {
    obs.push_back(static_cast<float>(
      (state.height_command - kBaseHeightTarget) / kHeightObsScale));
  }

  // 数值裁剪
  for (float & v : obs) {
    v = std::clamp(v, -kClipObs, kClipObs);
  }

  return obs;
}

/**
 * @brief 更新历史 observation 缓冲区
 */
void UpdateObservationHistory(
  const std::vector<float> & new_obs,
  std::vector<float> & history_obs,
  std::size_t one_step_dim,
  std::size_t history_dim)
{
  if (new_obs.size() != one_step_dim) {
    return;
  }

  if (history_obs.size() != history_dim) {
    history_obs.assign(history_dim, 0.0f);
  }

  for (std::size_t i = history_dim; i-- > one_step_dim;) {
    history_obs[i] = history_obs[i - one_step_dim];
  }

  std::copy(new_obs.begin(), new_obs.end(), history_obs.begin());
}

// VecToString 保留供调试使用
[[maybe_unused]]
static std::string VecToString(const std::vector<float> & vec, std::size_t max_items = 20)
{
  std::ostringstream oss;
  oss << std::fixed << std::setprecision(4) << "[";
  const std::size_t n = std::min(vec.size(), max_items);
  for (std::size_t i = 0; i < n; ++i) {
    if (i > 0) oss << ", ";
    oss << vec[i];
  }
  if (vec.size() > max_items) oss << ", ...";
  oss << "]";
  return oss.str();
}

}  // namespace

class DogPolicyTestNode : public rclcpp::Node
{
public:
  DogPolicyTestNode()
  : Node("dog_policy_test_node")
  {
    // =========================
    // 0. 声明并读取 one_obs_dim 参数
    // =========================
    this->declare_parameter("one_obs_dim", 46);
    const int one_obs_dim_param = this->get_parameter("one_obs_dim").as_int();

    if (one_obs_dim_param == 46) {
      one_step_obs_dim_ = kOneStepObsDim46;
      history_obs_dim_ = kHistoryObsDim46;
    } else if (one_obs_dim_param == 45) {
      one_step_obs_dim_ = kOneStepObsDim45;
      history_obs_dim_ = kHistoryObsDim45;
    } else {
      RCLCPP_ERROR(
        this->get_logger(),
        "不支持的 one_obs_dim = %d，只支持 45 或 46！节点退出。",
        one_obs_dim_param);
      rclcpp::shutdown();
      return;
    }

    // 初始化历史缓冲区为"站立"状态
    FillStandingHistory();

    // =========================
    // 1. 加载 ONNX 模型
    // =========================
    this->declare_parameter("model_path", std::string(""));
    const std::string model_path = this->get_parameter("model_path").as_string();

    if (model_path.empty()) {
      RCLCPP_ERROR(
        this->get_logger(),
        "model_path 参数为空！请通过 --params-file 指定 YAML 配置文件，"
        "或在 launch 中设置 model_path 参数。节点退出。");
      rclcpp::shutdown();
      return;
    }

    ort_env_ = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "dog_policy");

    Ort::SessionOptions session_options;
    session_options.SetIntraOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    ort_session_ = std::make_unique<Ort::Session>(
      *ort_env_, model_path.c_str(), session_options);

    // 获取输入/输出节点信息
    Ort::AllocatorWithDefaultOptions allocator;
    auto input_name_alloc = ort_session_->GetInputNameAllocated(0, allocator);
    input_name_ = input_name_alloc.get();

    auto output_name_alloc = ort_session_->GetOutputNameAllocated(0, allocator);
    output_name_ = output_name_alloc.get();

    // 缓存 ONNX 推理对象（避免每次推理时重复创建）
    memory_info_ = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    input_shape_ = {1, static_cast<int64_t>(history_obs_dim_)};

    // 打印模型信息
      RCLCPP_INFO(this->get_logger(),
      "ONNX model loaded: %s, input=[1,%zu], output=[1,%zu], obs_dim=%zu",
      model_path.c_str(), history_obs_dim_, kNumActions, one_step_obs_dim_);

    // =========================
    // 1.5 读取键盘控制速度参数（可通过 YAML 热修改）
    // =========================
    this->declare_parameter("kb_forward_speed", 0.5);
    this->declare_parameter("kb_backward_speed", -0.5);
    this->declare_parameter("kb_left_speed", 0.5);
    this->declare_parameter("kb_right_speed", -0.5);
    this->declare_parameter("kb_turn_left_speed", -1.0);
    this->declare_parameter("kb_turn_right_speed", 1.0);
    kb_forward_speed_ = this->get_parameter("kb_forward_speed").as_double();
    kb_backward_speed_ = this->get_parameter("kb_backward_speed").as_double();
    kb_left_speed_ = this->get_parameter("kb_left_speed").as_double();
    kb_right_speed_ = this->get_parameter("kb_right_speed").as_double();
    kb_turn_left_speed_ = this->get_parameter("kb_turn_left_speed").as_double();
    kb_turn_right_speed_ = this->get_parameter("kb_turn_right_speed").as_double();

    // =========================
    // 1.6 读取滤波/Action/静止死区/输出滤波参数（可通过 YAML 配置）
    // =========================
    this->declare_parameter("action_delta_max", 0.2);
    this->declare_parameter("action_scale", 0.25);
    this->declare_parameter("imu_gyro_lpf_alpha", 0.4);
    this->declare_parameter("imu_gyro_bias_alpha", 0.001);
    this->declare_parameter("motor_pos_lpf_alpha", 0.5);
    this->declare_parameter("motor_vel_lpf_alpha", 0.25);
    this->declare_parameter("motor_vel_bias_alpha", 0.001);
    this->declare_parameter("standstill_threshold", 0.05);
    this->declare_parameter("standstill_decay", 0.85);
    this->declare_parameter("standstill_action_threshold", 0.15);
    this->declare_parameter("publish_low_pass_alpha", 0.4);
    kActionDeltaMax = static_cast<float>(this->get_parameter("action_delta_max").as_double());
    kActionScale = static_cast<float>(this->get_parameter("action_scale").as_double());
    kImuGyroLpfAlpha = this->get_parameter("imu_gyro_lpf_alpha").as_double();
    kImuGyroBiasAlpha = this->get_parameter("imu_gyro_bias_alpha").as_double();
    kMotorPosLpfAlpha = this->get_parameter("motor_pos_lpf_alpha").as_double();
    kMotorVelLpfAlpha = this->get_parameter("motor_vel_lpf_alpha").as_double();
    kMotorVelBiasAlpha = this->get_parameter("motor_vel_bias_alpha").as_double();
    kStandstillThreshold = this->get_parameter("standstill_threshold").as_double();
    kStandstillDecay = static_cast<float>(this->get_parameter("standstill_decay").as_double());
    kStandstillActionThreshold = static_cast<float>(this->get_parameter("standstill_action_threshold").as_double());
    kPublishLowPassAlpha = this->get_parameter("publish_low_pass_alpha").as_double();

    // =========================
    // 2. 键盘控制线程
    // =========================
    StartKeyboardThread();

    // =========================
    // 3. 传感器订阅（回调只做数据拷贝，尽快返回）
    // =========================
    imu_sub_ = this->create_subscription<sensor_msgs::msg::Imu>(
      "/imu/data", 10,
      std::bind(&DogPolicyTestNode::ImuCallback, this, std::placeholders::_1));

    motor_feedback_sub_ = this->create_subscription<dog_control::msg::MotorFeedback>(
      "/motor_feedback", 10,
      std::bind(&DogPolicyTestNode::MotorFeedbackCallback, this, std::placeholders::_1));

    // =========================
    // 4. 发布 /joint_states
    // =========================
    joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>(
      "/joint_states", 10);

    // =========================
    // 5. policy_timer（50Hz）：读取传感器 → 滤波 → 推理 → 更新 motor_cmd
    // =========================
    policy_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(20),
      std::bind(&DogPolicyTestNode::PolicyTimerCallback, this));

    // =========================
    // 6. publish_timer（200Hz）：发布最近的 motor_cmd
    // =========================
    publish_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(5),
      std::bind(&DogPolicyTestNode::PublishTimerCallback, this));

    // =========================
    // 7. 定时打印状态
    // =========================
    print_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(500),
      std::bind(&DogPolicyTestNode::PrintStatus, this));

    RCLCPP_INFO(
      this->get_logger(),
      "dog_policy_test_node started — 三节奏架构: sensor回调(~200Hz), policy(50Hz), publish(200Hz)");
  }

  ~DogPolicyTestNode()
  {
    StopKeyboardThread();
  }

  bool IsKeyboardRunning() const { return keyboard_running_.load(); }

private:
  // ========================================================================================
  // 传感器回调：只更新 latest raw state，尽快返回
  // ========================================================================================

  void ImuCallback(const sensor_msgs::msg::Imu::SharedPtr msg)
  {
    if (!msg) return;
    std::lock_guard<std::mutex> lock(imu_mutex_);
    latest_imu_raw_.quaternion = {
      msg->orientation.w,
      msg->orientation.x,
      msg->orientation.y,
      msg->orientation.z};
    latest_imu_raw_.gyroscope = {
      msg->angular_velocity.x,
      msg->angular_velocity.y,
      msg->angular_velocity.z};
    has_imu_ = true;
  }

  void MotorFeedbackCallback(const dog_control::msg::MotorFeedback::SharedPtr msg)
  {
    if (!msg) return;
    std::lock_guard<std::mutex> lock(motor_mutex_);

    const std::size_t n = std::min({
      msg->name.size(),
      msg->position.size(),
      msg->velocity.size(),
      msg->torque.size()});

    for (std::size_t i = 0; i < n && i < kNumDofs; ++i) {
      latest_motor_raw_.position[i] = msg->position[i];
      latest_motor_raw_.velocity[i] = msg->velocity[i];
      latest_motor_raw_.torque[i] = msg->torque[i];
    }
    has_motor_feedback_ = true;
  }

  // ========================================================================================
  // PolicyTimerCallback（50Hz）：传感器滤波 → 构造 obs → ONNX 推理 → 更新 motor_cmd
  // ========================================================================================

  void PolicyTimerCallback()
  {
    // ----- 0. 等待模式：未按 y 确认前，不做推理 -----
    if (!rl_active_) {
      return;
    }

    // ----- 1. 拷贝最新传感器状态（短暂加锁） -----
    ImuState imu_snapshot;
    MotorRaw motor_snapshot;
    {
      std::lock_guard<std::mutex> lock(imu_mutex_);
      imu_snapshot = latest_imu_raw_;
    }
    {
      std::lock_guard<std::mutex> lock(motor_mutex_);
      motor_snapshot = latest_motor_raw_;
    }

    // ----- 2. IMU 滤波：零飘估计 + 低通 -----
    {
      std::lock_guard<std::mutex> lock(filter_mutex_);
      for (int i = 0; i < 3; ++i) {
        // 零飘估计（仅在未启动 RL 时估计）
        // ★ 注意：这里用 rl_active_==true 进入，所以 bias 不再更新
        // bias 已在等待阶段积累完毕
        double corrected = imu_snapshot.gyroscope[i] - imu_gyro_bias_[i];
        if (filter_initialized_) {
          imu_gyro_lpf_prev_[i] =
            kImuGyroLpfAlpha * corrected + (1.0 - kImuGyroLpfAlpha) * imu_gyro_lpf_prev_[i];
        } else {
          imu_gyro_lpf_prev_[i] = corrected;
        }
        robot_state_.imu.gyroscope[i] = imu_gyro_lpf_prev_[i];
      }
    }
    robot_state_.imu.quaternion = imu_snapshot.quaternion;
    robot_state_.projected_gravity =
      RotateWorldToBody(robot_state_.imu.quaternion, {0.0, 0.0, -1.0});

    // ----- 3. 电机滤波：位置只低通（不做零飘估计），速度低通+去零飘 -----
    {
      std::lock_guard<std::mutex> lock(filter_mutex_);
      for (std::size_t i = 0; i < kNumDofs; ++i) {
        const double raw_pos = motor_snapshot.position[i];
        const double raw_vel = motor_snapshot.velocity[i];

        // --- 电机位置：只低通，不做 bias 估计 ---
        // ★ 电机位置不是"静止时应该为 0 的传感器"，它是真实姿态
        //   做 bias 估计会把真实偏差当成零飘减掉，导致 RL 启动时观测错误
        if (filter_initialized_) {
          motor_pos_lpf_prev_[i] =
            kMotorPosLpfAlpha * raw_pos + (1.0 - kMotorPosLpfAlpha) * motor_pos_lpf_prev_[i];
        } else {
          motor_pos_lpf_prev_[i] = raw_pos;
        }

        // --- 电机速度：零飘估计 + 低通 ---
        // ★ 速度 bias 也要谨慎，编码器差分静止时可能有小噪声
        if (!rl_active_) {
          motor_vel_bias_[i] += kMotorVelBiasAlpha * (raw_vel - motor_vel_bias_[i]);
        }
        double vel_corrected = raw_vel - motor_vel_bias_[i];
        if (filter_initialized_) {
          motor_vel_lpf_prev_[i] =
            kMotorVelLpfAlpha * vel_corrected + (1.0 - kMotorVelLpfAlpha) * motor_vel_lpf_prev_[i];
        } else {
          motor_vel_lpf_prev_[i] = vel_corrected;
        }
      }

      filter_initialized_ = true;

      // 转换到模型空间（减速比）
      for (std::size_t i = 0; i < kNumDofs; ++i) {
        robot_state_.motor_state.q[i] = MsgPosToModelDeviation(motor_pos_lpf_prev_[i], i);
        robot_state_.motor_state.dq[i] = MsgVelToModelVel(motor_vel_lpf_prev_[i], i);
      }
    }

    robot_state_.motor_state.tau_est = motor_snapshot.torque;

    // ----- 4. 更新命令 -----
    {
      std::lock_guard<std::mutex> lock(data_mutex_);
      robot_state_.commands = {kb_vx_, kb_vy_, kb_wz_};
      robot_state_.height_command = kb_height_;
    }

    const double cmd_norm =
      std::abs(robot_state_.commands[0]) +
      std::abs(robot_state_.commands[1]) +
      std::abs(robot_state_.commands[2]);
    const bool is_standstill = (cmd_norm < kStandstillThreshold);

    // ----- 5. 构造单步 observation -----
    latest_one_step_obs_ = BuildOneStepObservation(
      robot_state_,
      obs_scales_,
      latest_actions_,
      one_step_obs_dim_ == kOneStepObsDim46);

    // ----- 6. 更新历史 observation（带预热） -----
    if (!history_warmed_up_) {
      std::copy(
        latest_one_step_obs_.begin(),
        latest_one_step_obs_.end(),
        obs_history_.begin());
      history_warmed_up_ = true;
    } else {
      UpdateObservationHistory(latest_one_step_obs_, obs_history_,
                               one_step_obs_dim_, history_obs_dim_);
    }

    // ----- 7. ONNX 推理 -----
    try {
      // 使用缓存的 memory_info_ 和 input_shape_
      Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
        memory_info_, obs_history_.data(), history_obs_dim_,
        input_shape_.data(), input_shape_.size());

      const char * input_names[] = {input_name_.c_str()};
      const char * output_names[] = {output_name_.c_str()};
      auto output_tensors = ort_session_->Run(
        Ort::RunOptions{nullptr},
        input_names, &input_tensor, 1,
        output_names, 1);

      float * raw_output = output_tensors[0].GetTensorMutableData<float>();

      // Step 1: 裁剪原始输出
      std::array<float, kNumActions> isaac_actions{};
      for (std::size_t i = 0; i < kNumActions; ++i) {
        isaac_actions[i] = std::clamp(raw_output[i], -10.0f, 10.0f);
      }

      // Step 2: Action 变化率限制
      for (std::size_t i = 0; i < kNumActions; ++i) {
        float delta = isaac_actions[i] - latest_actions_[i];
        delta = std::clamp(delta, -kActionDeltaMax, kActionDeltaMax);
        isaac_actions[i] = latest_actions_[i] + delta;
      }

      // Step 2.5: 静止死区：只在小输出时压制，保留支撑调节
      if (is_standstill) {
        for (std::size_t i = 0; i < kNumActions; ++i) {
          if (std::abs(isaac_actions[i]) < kStandstillActionThreshold) {
            isaac_actions[i] *= kStandstillDecay;
          }
        }
      }

      // 保存为 last_action
      latest_actions_ = isaac_actions;

      // action → 缩放 → 减速比 → js_pos
      std::array<double, kNumDofs> deviation{};
      for (std::size_t i = 0; i < kNumActions; ++i) {
        deviation[i] = static_cast<double>(isaac_actions[i] * kActionScale);
      }

      std::array<double, kNumDofs> new_motor_cmd{};
      for (std::size_t i = 0; i < kNumDofs; ++i) {
        new_motor_cmd[i] = ModelDeviationToJsPos(deviation[i], i);
      }

      // 更新 last_motor_cmd_（供 publish_timer 读取）
      {
        std::lock_guard<std::mutex> lock(cmd_mutex_);
        last_motor_cmd_ = new_motor_cmd;
      }

      inference_done_ = true;

      // 打印推理输出（每 25 次 ≈ 每 0.5s）
      static int inference_count = 0;
      if (++inference_count % 25 == 0) {
        printf("  [policy 50Hz] actions:");
        for (std::size_t i = 0; i < kNumActions; ++i) {
          printf(" %.4f", isaac_actions[i]);
        }
        printf("  deviation:");
        for (std::size_t i = 0; i < kNumDofs; ++i) {
          printf(" %.4f", deviation[i]);
        }
        printf("\n");
      }

    } catch (const Ort::Exception & e) {
      RCLCPP_ERROR(this->get_logger(), "ONNX inference failed: %s", e.what());
    }
  }

  // ========================================================================================
  // PublishTimerCallback（200Hz）：发布 /joint_states
  // ========================================================================================

  void PublishTimerCallback()
  {
    sensor_msgs::msg::JointState js_msg;
    js_msg.header.stamp = this->now();
    js_msg.header.frame_id = "base_link";
    js_msg.name = {
      "FL_hip", "FL_thigh", "FL_calf",
      "FR_hip", "FR_thigh", "FR_calf",
      "RL_hip", "RL_thigh", "RL_calf",
      "RR_hip", "RR_thigh", "RR_calf"
    };

    if (!rl_active_ || !inference_done_) {
      // 等待模式：发布全零 /joint_states
      // dog_control 收到后切换到 ACTIVE_FOLLOW，motor_target = 0 + offset = 站立位姿
      js_msg.position.resize(kNumDofs, 0.0);
      joint_state_pub_->publish(js_msg);
      return;
    }

    // RL 已激活：发布上一次推理的 motor_cmd，保持电机 200Hz PD 控制
    std::array<double, kNumDofs> cmd_snapshot;
    {
      std::lock_guard<std::mutex> lock(cmd_mutex_);
      cmd_snapshot = last_motor_cmd_;
    }

    // 200Hz 输出端低通滤波：抹平 50Hz 阶梯
    js_msg.position.resize(kNumDofs);
    {
      std::lock_guard<std::mutex> lock(filter_mutex_);
      for (std::size_t i = 0; i < kNumDofs; ++i) {
        publish_lpf_prev_[i] =
          kPublishLowPassAlpha * cmd_snapshot[i] +
          (1.0 - kPublishLowPassAlpha) * publish_lpf_prev_[i];
        js_msg.position[i] = publish_lpf_prev_[i];
      }
    }

    joint_state_pub_->publish(js_msg);
  }

  // ========================================================================================
  // 填充站立历史
  // ========================================================================================

  void FillStandingHistory()
  {
    obs_history_.assign(history_obs_dim_, 0.0f);
    const std::size_t gravity_offset = kNumCommands + kImuDim;  // = 6
    for (std::size_t frame = 0; frame < kObsHistoryLength; ++frame) {
      const std::size_t base = frame * one_step_obs_dim_;
      obs_history_[base + gravity_offset + 0] = 0.0f;
      obs_history_[base + gravity_offset + 1] = 0.0f;
      obs_history_[base + gravity_offset + 2] = -1.0f;
    }
  }

  // ========================================================================================
  // 键盘控制相关方法
  // ========================================================================================

  void StartKeyboardThread()
  {
    keyboard_running_ = true;
    keyboard_thread_ = std::thread(&DogPolicyTestNode::KeyboardLoop, this);

    printf("\n");
    printf("╔══════════════════════════════════════════╗\n");
    printf("║          键盘控制说明                     ║\n");
    printf("╠══════════════════════════════════════════╣\n");
    printf("║  y   : ★ 确认启动 RL 接管 ★             ║\n");
    printf("║  w/s : 前进/后退   (YAML 配置)           ║\n");
    printf("║  a/d : 左移/右移   (YAML 配置)           ║\n");
    printf("║  q/e : 左转/右转   (YAML 配置)           ║\n");
    printf("║  r   : 蹲下（height - 0.02）             ║\n");
    printf("║  f   : 站起（height + 0.02）             ║\n");
    printf("║  z   : 重置高度（0.25）                   ║\n");
    printf("║  p   : 重置机器人（清零历史）             ║\n");
    printf("║  Esc : 退出程序                          ║\n");
    printf("╚══════════════════════════════════════════╝\n");
    printf("\n");
  }

  void StopKeyboardThread()
  {
    keyboard_running_ = false;
    if (keyboard_thread_.joinable()) {
      keyboard_thread_.join();
    }
  }

  void KeyboardLoop()
  {
    struct termios orig_termios;
    tcgetattr(STDIN_FILENO, &orig_termios);

    struct termios raw = orig_termios;
    raw.c_lflag &= ~(ECHO | ICANON);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &raw);

    auto last_key_time = std::chrono::steady_clock::now();
    constexpr int kReleaseTimeoutMs = 200;

    while (keyboard_running_) {
      char ch = 0;
      int nread = read(STDIN_FILENO, &ch, 1);

      if (nread <= 0) {
        auto now = std::chrono::steady_clock::now();
        int elapsed_ms = static_cast<int>(
          std::chrono::duration_cast<std::chrono::milliseconds>(now - last_key_time).count());
        if (elapsed_ms > kReleaseTimeoutMs) {
          std::lock_guard<std::mutex> lock(data_mutex_);
          kb_vx_ = 0.0;
          kb_vy_ = 0.0;
          kb_wz_ = 0.0;
        }
        usleep(10000);
        continue;
      }

      last_key_time = std::chrono::steady_clock::now();

      if (ch == 27) {
        char seq[2] = {0};
        int n1 = read(STDIN_FILENO, &seq[0], 1);
        if (n1 <= 0) {
          printf("\n  [键盘] Esc 按下，正在退出...\n");
          keyboard_running_ = false;
          rclcpp::shutdown();  // 通知 rclcpp::spin 退出
          break;
        } else {
          (void)read(STDIN_FILENO, &seq[1], 1);
        }
        continue;
      }

      {
        std::lock_guard<std::mutex> lock(data_mutex_);

        switch (ch) {
          case 'w': kb_vx_ = kb_forward_speed_; break;
          case 's': kb_vx_ = kb_backward_speed_; break;
          case 'a': kb_vy_ = kb_left_speed_; break;
          case 'd': kb_vy_ = kb_right_speed_; break;
          case 'q': kb_wz_ = kb_turn_left_speed_; break;
          case 'e': kb_wz_ = kb_turn_right_speed_; break;
          case 'r':
            kb_height_ = std::max(0.20, kb_height_ - 0.02);
            printf("  [键盘] height = %.2f\n", kb_height_);
            break;
          case 'f':
            kb_height_ = std::min(0.30, kb_height_ + 0.02);
            printf("  [键盘] height = %.2f\n", kb_height_);
            break;
          case 'z':
            kb_height_ = 0.25;
            printf("  [键盘] height 重置为 0.25\n");
            break;
          case 'y':
            if (!rl_active_) {
              rl_active_ = true;
              history_warmed_up_ = false;
              inference_done_ = false;
              FillStandingHistory();
              latest_actions_.fill(0.0f);
              last_motor_cmd_.fill(0.0);
              publish_lpf_prev_.fill(0.0);
              // 在等待阶段已经积累了 IMU gyro bias 和 motor vel bias
              // RL 激活后 bias 不再更新
              printf("\n  ★★★ RL 已接管！（%zu 维）★★★\n\n", one_step_obs_dim_);
            } else {
              printf("  [键盘] RL 已经在运行中\n");
            }
            break;
          case 'p':
            FillStandingHistory();
            latest_actions_.fill(0.0f);
            last_motor_cmd_.fill(0.0);
            publish_lpf_prev_.fill(0.0);
            inference_done_ = false;
            history_warmed_up_ = false;
            printf("  [键盘] 重置机器人（history、actions 清零）\n");
            break;
          default:
            break;
        }
      }
    }

    tcsetattr(STDIN_FILENO, TCSANOW, &orig_termios);
  }

  // ========================================================================================
  // 打印状态
  // ========================================================================================

  void PrintStatus()
  {
    if (rl_active_) {
      return;
    }

    if (!has_imu_ || !has_motor_feedback_) {
      RCLCPP_WARN(
        this->get_logger(),
        "waiting for /imu/data and /motor_feedback ...");
      return;
    }

    std::lock_guard<std::mutex> lock(filter_mutex_);

    std::ostringstream oss;
    oss << std::fixed << std::setprecision(4)
        << "\n========== dog_policy_test ==========\n"
        << "mode: " << (rl_active_ ? "★★★ RL 推理 ★★★" : "等待中（按 y 启动 RL）") << "\n"
        << "has_imu: " << (has_imu_ ? "true" : "false") << "\n"
        << "has_motor: " << (has_motor_feedback_ ? "true" : "false") << "\n"
        << "commands: ["
        << kb_vx_ << ", " << kb_vy_ << ", " << kb_wz_ << "]\n"
        << "重力投影: ["
        << robot_state_.projected_gravity[0] << ", "
        << robot_state_.projected_gravity[1] << ", "
        << robot_state_.projected_gravity[2] << "]\n"
        << "obs_mode: " << one_step_obs_dim_ << " 维\n"
        << "imu_gyro_bias: ["
        << imu_gyro_bias_[0] << ", "
        << imu_gyro_bias_[1] << ", "
        << imu_gyro_bias_[2] << "]\n"
        << "====================================";

    RCLCPP_INFO(this->get_logger(), "%s", oss.str().c_str());
  }

private:
  // =========================
  // ROS 订阅器 / 定时器 / 发布器
  // =========================
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<dog_control::msg::MotorFeedback>::SharedPtr motor_feedback_sub_;
  rclcpp::TimerBase::SharedPtr policy_timer_;
  rclcpp::TimerBase::SharedPtr publish_timer_;
  rclcpp::TimerBase::SharedPtr print_timer_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;

  // =========================
  // 互斥锁（细粒度，减少锁竞争）
  // =========================
  std::mutex imu_mutex_;       // 保护 latest_imu_raw_
  std::mutex motor_mutex_;     // 保护 latest_motor_raw_
  std::mutex cmd_mutex_;       // 保护 last_motor_cmd_
  std::mutex filter_mutex_;    // 保护滤波状态 + robot_state_
  std::mutex data_mutex_;      // 保护键盘指令

  // =========================
  // 传感器原始数据（回调写入，policy_timer 读取）
  // =========================
  ImuState latest_imu_raw_;
  struct MotorRaw {
    std::array<double, kNumDofs> position{};
    std::array<double, kNumDofs> velocity{};
    std::array<double, kNumDofs> torque{};
  } latest_motor_raw_;

  bool has_imu_{false};
  bool has_motor_feedback_{false};

  // =========================
  // 运行时状态
  // =========================
  bool rl_active_{false};
  bool inference_done_{false};
  bool history_warmed_up_{false};
  bool filter_initialized_{false};

  // 上一次推理的电机指令缓存（50Hz 更新，200Hz 发布）
  std::array<double, kNumDofs> last_motor_cmd_{};
  // 200Hz 发布端低通滤波上一帧值
  std::array<double, kNumDofs> publish_lpf_prev_{};

  // ----- 输入滤波状态 -----
  std::array<double, 3> imu_gyro_lpf_prev_{};
  std::array<double, 3> imu_gyro_bias_{};
  std::array<double, kNumDofs> motor_pos_lpf_prev_{};
  std::array<double, kNumDofs> motor_vel_lpf_prev_{};
  std::array<double, kNumDofs> motor_vel_bias_{};
  // ★ 已删除 motor_pos_bias_：电机位置不做零飘估计

  RobotState robot_state_;
  ObsScales obs_scales_;
  std::array<float, kNumActions> latest_actions_{};

  // 单步 observation
  std::vector<float> latest_one_step_obs_;
  // 历史 observation
  std::vector<float> obs_history_;

  std::size_t one_step_obs_dim_{kOneStepObsDim46};
  std::size_t history_obs_dim_{kHistoryObsDim46};

  // =========================
  // 键盘控制
  // =========================
  std::atomic<bool> keyboard_running_{false};
  std::thread keyboard_thread_;
  double kb_vx_{0.0};
  double kb_vy_{0.0};
  double kb_wz_{0.0};
  double kb_height_{0.25};

  // 键盘速度参数（从 YAML 读取）
  double kb_forward_speed_{0.5};
  double kb_backward_speed_{-0.5};
  double kb_left_speed_{0.5};
  double kb_right_speed_{-0.5};
  double kb_turn_left_speed_{-1.0};
  double kb_turn_right_speed_{1.0};

  // ----- 从 YAML 读取的参数 -----
  float kActionDeltaMax{0.2f};
  float kActionScale{0.25f};
  double kImuGyroLpfAlpha{0.4};
  double kImuGyroBiasAlpha{0.001};
  double kMotorPosLpfAlpha{0.5};
  double kMotorVelLpfAlpha{0.25};
  double kMotorVelBiasAlpha{0.001};
  double kStandstillThreshold{0.05};
  float kStandstillDecay{0.85f};
  float kStandstillActionThreshold{0.15f};
  double kPublishLowPassAlpha{0.4};

  // =========================
  // ONNX Runtime（缓存对象避免重复创建）
  // =========================
  std::unique_ptr<Ort::Env> ort_env_;
  std::unique_ptr<Ort::Session> ort_session_;
  std::string input_name_;
  std::string output_name_;
  Ort::MemoryInfo memory_info_{nullptr};  // 构造函数中初始化
  std::array<int64_t, 2> input_shape_{1, 0};  // 构造函数中初始化
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<DogPolicyTestNode>();

  // ★ 使用 rclcpp::spin 替代 spin_some + sleep(10ms)
  // 键盘线程 Esc 时调用 rclcpp::shutdown() 退出 spin
  rclcpp::spin(node);

  rclcpp::shutdown();
  return 0;
}