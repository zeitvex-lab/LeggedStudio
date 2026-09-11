   // ========================================================================================
// dog_policy_test_9.cpp — 基于 test_8 的架构改进版
// ========================================================================================
//
// ★ 与 test_8 的区别：
//   1. dt 自适应：测量实际推理间隔，不再硬编码 0.02
//   2. 传感器同步读取：scoped_lock 同时获取 IMU + Motor 数据，消除时间差
//   3. 推理独立线程：ONNX 推理从 ROS executor 分离，publish_timer 永不被阻塞
//
// 架构说明（四线程 + 倾倒保护 + 命令渐变）
// ========================================================================================
//
// ┌─────────────────────┐    ┌──────────────────────────┐
// │  ROS Executor 线程   │    │  Inference 线程 (50Hz)    │
// │  ├─ ImuCallback      │───→│  ├─ scoped_lock 同步读取   │
// │  ├─ MotorCallback    │    │  ├─ 滤波                  │
// │  ├─ publish_timer    │←───│  ├─ obs 构建              │
// │  └─ print_timer      │    │  ├─ ONNX 推理             │
// └─────────────────────┘    │  └─ → motor_cmd            │
//        G:\zhy\himdog\src\dog_control                    └──────────────────────────┘
//
// ★ 推理线程用 sleep_until 精确控制节拍，不受 ROS executor 影响
// ★ publish_timer（200Hz）永远不被推理阻塞
//
// 运行命令：
// ros2 run dog_policy_test dog_policy_test_9 --ros-args --params-file ./src/dog_policy_test/config/policy_params.yaml

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include "dog_control/msg/motor_feedback.hpp"

#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <thread>
#include <atomic>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>

#include <onnxruntime_cxx_api.h>


namespace
{
// =========================
// 1. 常量定义区
// =========================

constexpr std::size_t kNumDofs = 12;
constexpr std::size_t kNumActions = 12;
constexpr std::size_t kNumCommands = 3;
constexpr std::size_t kImuDim = 3;
constexpr std::size_t kGravityDim = 3;
constexpr std::size_t kHeightCommandDim = 1;

constexpr std::size_t kOneStepObsDim46 =
  kNumCommands + kImuDim + kGravityDim + kNumDofs + kNumDofs + kNumActions + kHeightCommandDim;  // = 46

constexpr std::size_t kOneStepObsDim45 =
  kNumCommands + kImuDim + kGravityDim + kNumDofs + kNumDofs + kNumActions;  // = 45

constexpr std::size_t kObsHistoryLength = 6;

constexpr std::size_t kHistoryObsDim46 = kObsHistoryLength * kOneStepObsDim46;  // 6 × 46 = 276
constexpr std::size_t kHistoryObsDim45 = kObsHistoryLength * kOneStepObsDim45;  // 6 × 45 = 270

constexpr double kBaseHeightTarget = 0.25;
constexpr double kHeightObsScale = 0.1;

constexpr float kClipObs = 100.0f;

constexpr std::array<float, kNumCommands> kCommandScale{2.0f, 2.0f, 0.25f};

// ----- 倾倒保护参数 -----
constexpr int kTipoverRecoveryFrames = 50;

// =========================
// 2. 数据结构定义区
// =========================

struct ObsScales
{
  double ang_vel{0.25};
  double dof_pos{1.0};
  double dof_vel{0.05};
};

struct ImuState
{
  std::array<double, 4> quaternion{{1.0, 0.0, 0.0, 0.0}};
  std::array<double, 3> gyroscope{{0.0, 0.0, 0.0}};
};

struct MotorState
{
  std::array<double, kNumDofs> q{};
  std::array<double, kNumDofs> dq{};
};

struct RobotState
{
  ImuState imu;
  MotorState motor_state;
  std::array<double, 3> commands{};
  std::array<double, 3> projected_gravity{{0.0, 0.0, -1.0}};
  double height_command{0.25};
};

// =========================
// 3. 工具函数区
// =========================

inline bool IsCalfJoint(std::size_t joint_idx)
{
  return (joint_idx % 3) == 2;
}

inline double MsgPosToModelDeviation(double raw_motor_pos, std::size_t joint_idx)
{
  if (IsCalfJoint(joint_idx)) {
    return raw_motor_pos / 2.0;
  }
  return raw_motor_pos;
}

inline double MsgVelToModelVel(double raw_motor_vel, std::size_t joint_idx)
{
  if (IsCalfJoint(joint_idx)) {
    return raw_motor_vel / 2.0;
  }
  return raw_motor_vel;
}

inline double ModelDeviationToJsPos(double model_deviation, std::size_t joint_idx)
{
  if (IsCalfJoint(joint_idx)) {
    return 2.0 * model_deviation;
  }
  return model_deviation;
}

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

// ★ 栈上构建 obs（零堆分配）
template <std::size_t MaxDim>
std::size_t BuildOneStepObservationStack(
  const RobotState & state,
  const ObsScales & obs_scales,
  const std::array<float, kNumActions> & last_actions,
  bool include_height_command,
  std::array<float, MaxDim> & out_obs)
{
  std::size_t idx = 0;

  for (std::size_t i = 0; i < kNumCommands; ++i) {
    out_obs[idx++] = static_cast<float>(state.commands[i] * kCommandScale[i]);
  }
  for (double ang_vel : state.imu.gyroscope) {
    out_obs[idx++] = static_cast<float>(ang_vel * obs_scales.ang_vel);
  }
  for (double g : state.projected_gravity) {
    out_obs[idx++] = static_cast<float>(g);
  }
  for (std::size_t i = 0; i < kNumDofs; ++i) {
    out_obs[idx++] = static_cast<float>(state.motor_state.q[i] * obs_scales.dof_pos);
  }
  for (double dq : state.motor_state.dq) {
    out_obs[idx++] = static_cast<float>(dq * obs_scales.dof_vel);
  }
  for (float a : last_actions) {
    out_obs[idx++] = a;
  }
  if (include_height_command) {
    out_obs[idx++] = static_cast<float>(
      (state.height_command - kBaseHeightTarget) / kHeightObsScale);
  }

  for (std::size_t i = 0; i < idx; ++i) {
    out_obs[i] = std::clamp(out_obs[i], -kClipObs, kClipObs);
  }

  return idx;
}

void UpdateObservationHistory(
  const std::array<float, 46> & new_obs,
  std::size_t one_step_dim,
  std::vector<float> & history_obs,
  std::size_t history_dim)
{
  if (history_obs.size() != history_dim) {
    history_obs.assign(history_dim, 0.0f);
  }
  for (std::size_t i = history_dim; i-- > one_step_dim;) {
    history_obs[i] = history_obs[i - one_step_dim];
  }
  std::copy(new_obs.begin(), new_obs.begin() + one_step_dim, history_obs.begin());
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
      RCLCPP_ERROR(this->get_logger(),
        "不支持的 one_obs_dim = %d，只支持 45 或 46！节点退出。", one_obs_dim_param);
      rclcpp::shutdown();
      return;
    }

    FillStandingHistory();

    // =========================
    // 1. 加载 ONNX 模型
    // =========================
    this->declare_parameter("model_path", std::string(""));
    const std::string model_path = this->get_parameter("model_path").as_string();

    if (model_path.empty()) {
      RCLCPP_ERROR(this->get_logger(),
        "model_path 参数为空！请通过 --params-file 指定 YAML 配置文件。节点退出。");
      rclcpp::shutdown();
      return;
    }

    ort_env_ = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "dog_policy");

    Ort::SessionOptions session_options;
    session_options.SetIntraOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    ort_session_ = std::make_unique<Ort::Session>(*ort_env_, model_path.c_str(), session_options);

    Ort::AllocatorWithDefaultOptions allocator;
    auto input_name_alloc = ort_session_->GetInputNameAllocated(0, allocator);
    input_name_ = input_name_alloc.get();
    auto output_name_alloc = ort_session_->GetOutputNameAllocated(0, allocator);
    output_name_ = output_name_alloc.get();

    memory_info_ = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    input_shape_ = {1, static_cast<int64_t>(history_obs_dim_)};

    RCLCPP_INFO(this->get_logger(),
      "ONNX model loaded: %s, input=[1,%zu], output=[1,%zu], obs_dim=%zu",
      model_path.c_str(), history_obs_dim_, kNumActions, one_step_obs_dim_);

    // =========================
    // 1.5 读取键盘控制速度参数
    // =========================
    this->declare_parameter("kb_forward_speed", 0.5);
    this->declare_parameter("kb_backward_speed", -0.5);
    this->declare_parameter("kb_left_speed", 0.5);
    this->declare_parameter("kb_right_speed", -0.5);
    this->declare_parameter("kb_turn_left_speed", -0.5);
    this->declare_parameter("kb_turn_right_speed", 0.5);
    kb_forward_speed_ = this->get_parameter("kb_forward_speed").as_double();
    kb_backward_speed_ = this->get_parameter("kb_backward_speed").as_double();
    kb_left_speed_ = this->get_parameter("kb_left_speed").as_double();
    kb_right_speed_ = this->get_parameter("kb_right_speed").as_double();
    kb_turn_left_speed_ = this->get_parameter("kb_turn_left_speed").as_double();
    kb_turn_right_speed_ = this->get_parameter("kb_turn_right_speed").as_double();

    // =========================
    // 1.7 读取命令渐变参数
    // =========================
    this->declare_parameter("command_ramp_rate", 1.0);
    command_ramp_rate_ = this->get_parameter("command_ramp_rate").as_double();

    // =========================
    // 1.8 读取输出平滑 / Action 限制参数
    // =========================
    this->declare_parameter("output_lpf_alpha", 1.0);
    this->declare_parameter("action_delta_max", 100.0);
    output_lpf_alpha_ = this->get_parameter("output_lpf_alpha").as_double();
    action_delta_max_ = static_cast<float>(this->get_parameter("action_delta_max").as_double());

    // =========================
    // 1.6 读取滤波/Action/倾倒保护参数
    // =========================
    this->declare_parameter("action_scale", 0.25);
    this->declare_parameter("imu_gyro_lpf_alpha", 1.0);
    this->declare_parameter("imu_gyro_bias_alpha", 0.001);
    this->declare_parameter("motor_pos_lpf_alpha", 1.0);
    this->declare_parameter("motor_vel_lpf_alpha", 1.0);
    this->declare_parameter("motor_vel_bias_alpha", 0.001);
    this->declare_parameter("tipover_threshold", -0.3);

    action_scale_ = static_cast<float>(this->get_parameter("action_scale").as_double());
    imu_gyro_lpf_alpha_ = this->get_parameter("imu_gyro_lpf_alpha").as_double();
    imu_gyro_bias_alpha_ = this->get_parameter("imu_gyro_bias_alpha").as_double();
    motor_pos_lpf_alpha_ = this->get_parameter("motor_pos_lpf_alpha").as_double();
    motor_vel_lpf_alpha_ = this->get_parameter("motor_vel_lpf_alpha").as_double();
    motor_vel_bias_alpha_ = this->get_parameter("motor_vel_bias_alpha").as_double();
    tipover_threshold_ = this->get_parameter("tipover_threshold").as_double();

    // =========================
    // 2. 键盘控制线程
    // =========================
    StartKeyboardThread();

    // =========================
    // 3. 传感器订阅
    // =========================
    imu_sub_ = this->create_subscription<sensor_msgs::msg::Imu>(
      "/imu/data", 10,
      std::bind(&DogPolicyTestNode::ImuCallback, this, std::placeholders::_1));

    motor_feedback_sub_ = this->create_subscription<dog_control::msg::MotorFeedback>(
      "/motor_feedback", 10,
      std::bind(&DogPolicyTestNode::MotorFeedbackCallback, this, std::placeholders::_1));

    // =========================
    // 4. 发布 /joint_states + /dog_state
    // =========================
    joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);
    emergency_stop_pub_ = this->create_publisher<std_msgs::msg::Bool>("/emergency_stop", 10);
    dog_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/dog_state", 10);

    // =========================
    // 5. ★ 推理独立线程（替代 policy_timer）
    // =========================
    inference_running_ = true;
    last_inference_time_ = std::chrono::steady_clock::now();
    inference_thread_ = std::thread(&DogPolicyTestNode::InferenceLoop, this);

    // =========================
    // 6. publish_timer（200Hz）— 仅负责发布 + 松手检测
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

    RCLCPP_INFO(this->get_logger(),
      "dog_policy_test_9 started — 独立推理线程+dt自适应+传感器同步: tipover=%.2f, ramp=%.2f, out_lpf=%.2f",
      tipover_threshold_, command_ramp_rate_, output_lpf_alpha_);
  }

  ~DogPolicyTestNode()
  {
    StopInferenceThread();
    StopKeyboardThread();
  }

  bool IsKeyboardRunning() const { return keyboard_running_.load(); }

private:
  // ========================================================================================
  // ★ ImuCallback：拷贝数据 + 倾倒检测 + 缓存 projected_gravity
  // ========================================================================================

  void ImuCallback(const sensor_msgs::msg::Imu::SharedPtr msg)
  {
    if (!msg) return;

    // --- 1. 拷贝 IMU 数据 ---
    std::array<double, 4> quat_copy;
    {
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
      quat_copy = latest_imu_raw_.quaternion;
      has_imu_ = true;
    }

    // --- 2. 缓存 projected_gravity ---
    const auto grav = RotateWorldToBody(quat_copy, {0.0, 0.0, -1.0});
    {
      std::lock_guard<std::mutex> lock(gravity_mutex_);
      cached_projected_gravity_ = grav;
    }

    // --- 3. 倾倒检测 ---
    const double g_z = grav[2];

    if (g_z > tipover_threshold_) {
      if (!tipped_over_.load()) {
        tipped_over_.store(true);
        tipover_recovery_count_.store(0);

        std_msgs::msg::Bool estop_msg;
        estop_msg.data = true;
        emergency_stop_pub_->publish(estop_msg);

        printf("\n");
        printf("╔══════════════════════════════════════════════════╗\n");
        printf("║  ⚠️  倾倒保护触发！                              ║\n");
        printf("║  projected_gravity[2] = %.3f > threshold %.3f    ║\n", g_z, tipover_threshold_);
        printf("║  已发送 EMERGENCY STOP，所有电机已失能             ║\n");
        printf("╚══════════════════════════════════════════════════╝\n");
        printf("\n");

        // ★ 延迟 shutdown（不在回调中直接调用）
        shutdown_requested_.store(true);
      }
    } else {
      if (tipped_over_.load()) {
        int count = tipover_recovery_count_.fetch_add(1) + 1;
        if (count >= kTipoverRecoveryFrames) {
          tipped_over_.store(false);
          tipover_recovery_count_.store(0);
          printf("  [倾倒保护] 机器人已恢复正常姿态，保护解除。按 y 重新启动 RL。\n");
        }
      }
    }
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
    }
    has_motor_feedback_ = true;
  }

  // ========================================================================================
  // ★ InferenceLoop — 独立推理线程（50Hz，sleep_until 精确节拍）
  // ========================================================================================

  void InferenceLoop()
  {
    const auto inference_period = std::chrono::milliseconds(20);  // 50Hz
    auto next_tick = std::chrono::steady_clock::now() + inference_period;

    while (inference_running_) {
      // ★ sleep_until 精确控制节拍（比 wall_timer 更精确）
      std::this_thread::sleep_until(next_tick);
      auto now = std::chrono::steady_clock::now();
      next_tick += inference_period;

      // 防止长时间阻塞后"追赶"（跳过积压的 tick）
      if (now > next_tick + inference_period) {
        next_tick = now + inference_period;
      }

      // ----- ★ 1. dt 自适应 -----
      const double dt = std::chrono::duration<double>(now - last_inference_time_).count();
      last_inference_time_ = now;
      const double dt_clamped = std::clamp(dt, 0.01, 0.05);  // 防止异常值

      // ----- 2. 等待模式 / 倾倒保护 -----
      if (!rl_active_.load()) continue;

      if (tipped_over_.load()) {
        RunFilteringOnly();
        continue;
      }

      // ----- ★ 3. 传感器同步读取（scoped_lock 同时获取 IMU + Motor）-----
      ImuState imu_snapshot;
      MotorRaw motor_snapshot;
      {
        std::scoped_lock lock(imu_mutex_, motor_mutex_);
        imu_snapshot = latest_imu_raw_;
        motor_snapshot = latest_motor_raw_;
      }

      // ----- 4. IMU 滤波 -----
      {
        std::lock_guard<std::mutex> lock(filter_mutex_);
        for (int i = 0; i < 3; ++i) {
          double corrected = imu_snapshot.gyroscope[i] - imu_gyro_bias_[i];
          if (filter_initialized_) {
            imu_gyro_lpf_prev_[i] =
              imu_gyro_lpf_alpha_ * corrected + (1.0 - imu_gyro_lpf_alpha_) * imu_gyro_lpf_prev_[i];
          } else {
            imu_gyro_lpf_prev_[i] = corrected;
          }
          robot_state_.imu.gyroscope[i] = imu_gyro_lpf_prev_[i];
        }
      }
      robot_state_.imu.quaternion = imu_snapshot.quaternion;

      // 使用缓存的 projected_gravity
      {
        std::lock_guard<std::mutex> lock(gravity_mutex_);
        robot_state_.projected_gravity = cached_projected_gravity_;
      }

      // ----- 5. 电机滤波 -----
      {
        std::lock_guard<std::mutex> lock(filter_mutex_);
        for (std::size_t i = 0; i < kNumDofs; ++i) {
          const double raw_pos = motor_snapshot.position[i];
          const double raw_vel = motor_snapshot.velocity[i];

          if (filter_initialized_) {
            motor_pos_lpf_prev_[i] =
              motor_pos_lpf_alpha_ * raw_pos + (1.0 - motor_pos_lpf_alpha_) * motor_pos_lpf_prev_[i];
          } else {
            motor_pos_lpf_prev_[i] = raw_pos;
          }

          if (!rl_active_.load()) {
            motor_vel_bias_[i] += motor_vel_bias_alpha_ * (raw_vel - motor_vel_bias_[i]);
          }
          double vel_corrected = raw_vel - motor_vel_bias_[i];
          if (filter_initialized_) {
            motor_vel_lpf_prev_[i] =
              motor_vel_lpf_alpha_ * vel_corrected + (1.0 - motor_vel_lpf_alpha_) * motor_vel_lpf_prev_[i];
          } else {
            motor_vel_lpf_prev_[i] = vel_corrected;
          }
        }

        filter_initialized_ = true;

        for (std::size_t i = 0; i < kNumDofs; ++i) {
          robot_state_.motor_state.q[i] = MsgPosToModelDeviation(motor_pos_lpf_prev_[i], i);
          robot_state_.motor_state.dq[i] = MsgVelToModelVel(motor_vel_lpf_prev_[i], i);
        }
      }

      // ----- ★ 6. 命令渐变（使用自适应 dt）-----
      {
        std::lock_guard<std::mutex> lock(data_mutex_);
        const double max_delta = command_ramp_rate_ * dt_clamped;
        kb_vx_ += std::clamp(kb_vx_target_ - kb_vx_, -max_delta, max_delta);
        kb_vy_ += std::clamp(kb_vy_target_ - kb_vy_, -max_delta, max_delta);
        kb_wz_ += std::clamp(kb_wz_target_ - kb_wz_, -max_delta, max_delta);

        robot_state_.commands = {kb_vx_, kb_vy_, kb_wz_};
        robot_state_.height_command = kb_height_;
      }

      // ----- 7. 栈上构造单步 observation -----
      const bool include_height = (one_step_obs_dim_ == kOneStepObsDim46);
      const std::size_t obs_dim = BuildOneStepObservationStack(
        robot_state_, obs_scales_, latest_actions_, include_height, one_step_obs_buf_);

      // ----- 8. 更新历史 observation -----
      if (!history_warmed_up_) {
        std::copy(one_step_obs_buf_.begin(), one_step_obs_buf_.begin() + obs_dim, obs_history_.begin());
        history_warmed_up_ = true;
      } else {
        UpdateObservationHistory(one_step_obs_buf_, one_step_obs_dim_, obs_history_, history_obs_dim_);
      }

      // ----- 9. ONNX 推理 -----
      try {
        Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
          memory_info_, obs_history_.data(), history_obs_dim_,
          input_shape_.data(), input_shape_.size());

        const char * input_names[] = {input_name_.c_str()};
        const char * output_names[] = {output_name_.c_str()};
        auto output_tensors = ort_session_->Run(
          Ort::RunOptions{nullptr}, input_names, &input_tensor, 1, output_names, 1);

        float * raw_output = output_tensors[0].GetTensorMutableData<float>();

        // clip
        std::array<float, kNumActions> actions{};
        for (std::size_t i = 0; i < kNumActions; ++i) {
          actions[i] = std::clamp(raw_output[i], -10.0f, 10.0f);
        }

        // Action 步间变化率限制
        if (action_delta_max_ < 99.0f) {
          for (std::size_t i = 0; i < kNumActions; ++i) {
            actions[i] = std::clamp(actions[i],
              latest_actions_[i] - action_delta_max_,
              latest_actions_[i] + action_delta_max_);
          }
        }

        latest_actions_ = actions;

        std::array<double, kNumDofs> deviation{};
        for (std::size_t i = 0; i < kNumActions; ++i) {
          deviation[i] = static_cast<double>(actions[i] * action_scale_);
        }

        std::array<double, kNumDofs> new_motor_cmd{};
        for (std::size_t i = 0; i < kNumDofs; ++i) {
          new_motor_cmd[i] = ModelDeviationToJsPos(deviation[i], i);
        }

        {
          std::lock_guard<std::mutex> lock(cmd_mutex_);
          last_motor_cmd_ = new_motor_cmd;
        }

        inference_done_.store(true);

        // ★ 打印推理状态（含 dt 信息）
        inference_count_++;
        if (inference_count_ % 25 == 0) {
          printf("  [policy] dt=%.3fms cmd_target:[%.2f,%.2f,%.2f] cmd_actual:[%.2f,%.2f,%.2f] act:",
                 dt * 1000.0,
                 kb_vx_target_, kb_vy_target_, kb_wz_target_,
                 kb_vx_, kb_vy_, kb_wz_);
          for (std::size_t i = 0; i < kNumActions; ++i) { printf(" %+.3f", actions[i]); }
          printf("\n");
        }

      } catch (const Ort::Exception & e) {
        RCLCPP_ERROR(this->get_logger(), "ONNX inference failed: %s", e.what());
      }
    }
  }

  void StopInferenceThread()
  {
    inference_running_ = false;
    if (inference_thread_.joinable()) {
      inference_thread_.join();
    }
  }

  // ========================================================================================
  // RunFilteringOnly：倾倒保护期间只做滤波
  // ========================================================================================

  void RunFilteringOnly()
  {
    ImuState imu_snapshot;
    MotorRaw motor_snapshot;
    {
      std::scoped_lock lock(imu_mutex_, motor_mutex_);
      imu_snapshot = latest_imu_raw_;
      motor_snapshot = latest_motor_raw_;
    }

    {
      std::lock_guard<std::mutex> lock(filter_mutex_);
      for (int i = 0; i < 3; ++i) {
        imu_gyro_bias_[i] += imu_gyro_bias_alpha_ * (imu_snapshot.gyroscope[i] - imu_gyro_bias_[i]);
        double corrected = imu_snapshot.gyroscope[i] - imu_gyro_bias_[i];
        if (filter_initialized_) {
          imu_gyro_lpf_prev_[i] =
            imu_gyro_lpf_alpha_ * corrected + (1.0 - imu_gyro_lpf_alpha_) * imu_gyro_lpf_prev_[i];
        } else {
          imu_gyro_lpf_prev_[i] = corrected;
        }
      }

      for (std::size_t i = 0; i < kNumDofs; ++i) {
        const double raw_vel = motor_snapshot.velocity[i];
        motor_vel_bias_[i] += motor_vel_bias_alpha_ * (raw_vel - motor_vel_bias_[i]);
      }

      filter_initialized_ = true;
    }
  }

  // ========================================================================================
  // PublishTimerCallback（200Hz）— 仅发布 + 松手检测
  // ========================================================================================

  void PublishTimerCallback()
  {
    // ★ 安全 shutdown 检查（不在回调中直接调用 rclcpp::shutdown）
    if (shutdown_requested_.load()) {
      rclcpp::shutdown();
      return;
    }

    // ★ 松手检测
    CheckKeyRelease();

    sensor_msgs::msg::JointState js_msg;
    js_msg.header.stamp = this->now();
    js_msg.header.frame_id = "base_link";
    js_msg.name = {
      "FL_hip", "FL_thigh", "FL_calf",
      "FR_hip", "FR_thigh", "FR_calf",
      "RL_hip", "RL_thigh", "RL_calf",
      "RR_hip", "RR_thigh", "RR_calf"
    };

    // 倾倒保护 / 未启动
    if (tipped_over_.load() || !rl_active_.load() || !inference_done_.load()) {
      js_msg.position.resize(kNumDofs, 0.0);

      // 输出端 LPF：即使发零也更新滤波状态
      if (output_lpf_initialized_) {
        for (std::size_t i = 0; i < kNumDofs; ++i) {
          output_lpf_prev_[i] = output_lpf_alpha_ * 0.0 + (1.0 - output_lpf_alpha_) * output_lpf_prev_[i];
        }
      }

      joint_state_pub_->publish(js_msg);
      PublishDogState(js_msg);
      return;
    }

    // 正常发布
    std::array<double, kNumDofs> cmd_snapshot;
    {
      std::lock_guard<std::mutex> lock(cmd_mutex_);
      cmd_snapshot = last_motor_cmd_;
    }

    // 输出端 LPF（alpha=1.0 时直通）
    js_msg.position.resize(kNumDofs);
    if (output_lpf_alpha_ >= 0.999) {
      for (std::size_t i = 0; i < kNumDofs; ++i) {
        js_msg.position[i] = cmd_snapshot[i];
      }
    } else {
      for (std::size_t i = 0; i < kNumDofs; ++i) {
        if (output_lpf_initialized_) {
          output_lpf_prev_[i] = output_lpf_alpha_ * cmd_snapshot[i]
                                + (1.0 - output_lpf_alpha_) * output_lpf_prev_[i];
        } else {
          output_lpf_prev_[i] = cmd_snapshot[i];
        }
        js_msg.position[i] = output_lpf_prev_[i];
      }
      output_lpf_initialized_ = true;
    }

    joint_state_pub_->publish(js_msg);
    PublishDogState(js_msg);
  }

  // ========================================================================================
  // 发布 /dog_state 诊断话题
  // ========================================================================================

  void PublishDogState(const sensor_msgs::msg::JointState & js_msg)
  {
    sensor_msgs::msg::JointState state_msg;
    state_msg.header.stamp = js_msg.header.stamp;
    state_msg.name = {"cmd_vx", "cmd_vy", "cmd_wz",
                      "cmd_vx_target", "cmd_vy_target", "cmd_wz_target",
                      "grav_x", "grav_y", "grav_z",
                      "height_cmd"};
    state_msg.position = {
      kb_vx_, kb_vy_, kb_wz_,
      kb_vx_target_, kb_vy_target_, kb_wz_target_,
      robot_state_.projected_gravity[0],
      robot_state_.projected_gravity[1],
      robot_state_.projected_gravity[2],
      kb_height_
    };
    dog_state_pub_->publish(state_msg);
  }

  // ========================================================================================
  // 填充站立历史
  // ========================================================================================

  void FillStandingHistory()
  {
    obs_history_.assign(history_obs_dim_, 0.0f);
    const std::size_t gravity_offset = kNumCommands + kImuDim;
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

    while (keyboard_running_) {
      char ch = 0;
      int nread = read(STDIN_FILENO, &ch, 1);

      if (nread <= 0) {
        usleep(5000);  // 5ms
        continue;
      }

      // Escape 键处理
      if (ch == 27) {
        char seq[2] = {0};
        int n1 = read(STDIN_FILENO, &seq[0], 1);
        if (n1 <= 0) {
          printf("\n  [键盘] Esc 按下，正在退出...\n");
          keyboard_running_ = false;
          rclcpp::shutdown();
          break;
        } else {
          auto ret2 [[maybe_unused]] = read(STDIN_FILENO, &seq[1], 1);
        }
        continue;
      }

      {
        std::lock_guard<std::mutex> lock(data_mutex_);

        switch (ch) {
          case 'w': key_w_ = true; last_key_time_['w'] = std::chrono::steady_clock::now(); break;
          case 's': key_s_ = true; last_key_time_['s'] = std::chrono::steady_clock::now(); break;
          case 'a': key_a_ = true; last_key_time_['a'] = std::chrono::steady_clock::now(); break;
          case 'd': key_d_ = true; last_key_time_['d'] = std::chrono::steady_clock::now(); break;
          case 'q': key_q_ = true; last_key_time_['q'] = std::chrono::steady_clock::now(); break;
          case 'e': key_e_ = true; last_key_time_['e'] = std::chrono::steady_clock::now(); break;
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
            if (!rl_active_.load()) {
              if (tipped_over_.load()) {
                printf("  [键盘] 机器人仍处于倾倒状态，请先扶正！\n");
              } else {
                rl_active_.store(true);
                history_warmed_up_ = false;
                inference_done_.store(false);
                inference_count_ = 0;
                last_inference_time_ = std::chrono::steady_clock::now();
                FillStandingHistory();
                latest_actions_.fill(0.0f);
                last_motor_cmd_.fill(0.0);
                output_lpf_prev_.fill(0.0);
                output_lpf_initialized_ = false;
                kb_vx_target_ = 0.0; kb_vy_target_ = 0.0; kb_wz_target_ = 0.0;
                kb_vx_ = 0.0; kb_vy_ = 0.0; kb_wz_ = 0.0;
                printf("\n  ★★★ RL 已接管！（%zu 维）★★★\n\n", one_step_obs_dim_);
              }
            } else {
              printf("  [键盘] RL 已经在运行中\n");
            }
            break;
          case 'p':
            FillStandingHistory();
            latest_actions_.fill(0.0f);
            last_motor_cmd_.fill(0.0);
            output_lpf_prev_.fill(0.0);
            output_lpf_initialized_ = false;
            inference_done_.store(false);
            inference_count_ = 0;
            history_warmed_up_ = false;
            kb_vx_target_ = 0.0; kb_vy_target_ = 0.0; kb_wz_target_ = 0.0;
            kb_vx_ = 0.0; kb_vy_ = 0.0; kb_wz_ = 0.0;
            printf("  [键盘] 重置机器人（history、actions、commands 清零）\n");
            break;
          default:
            break;
        }

        kb_vx_target_ = key_w_ ? kb_forward_speed_ : (key_s_ ? kb_backward_speed_ : 0.0);
        kb_vy_target_ = key_a_ ? kb_left_speed_ : (key_d_ ? kb_right_speed_ : 0.0);
        kb_wz_target_ = key_q_ ? kb_turn_left_speed_ : (key_e_ ? kb_turn_right_speed_ : 0.0);
      }
    }

    tcsetattr(STDIN_FILENO, TCSANOW, &orig_termios);
  }

  // ★ 松手检测
  void CheckKeyRelease()
  {
    auto now = std::chrono::steady_clock::now();
    constexpr int kKeyTimeoutMs = 150;

    std::lock_guard<std::mutex> lock(data_mutex_);

    for (auto & [ch, time] : last_key_time_) {
      int elapsed = static_cast<int>(
        std::chrono::duration_cast<std::chrono::milliseconds>(now - time).count());
      if (elapsed > kKeyTimeoutMs) {
        switch (ch) {
          case 'w': key_w_ = false; if (kb_vx_target_ > 0) { kb_vx_target_ = 0.0; } break;
          case 's': key_s_ = false; if (kb_vx_target_ < 0) { kb_vx_target_ = 0.0; } break;
          case 'a': key_a_ = false; if (kb_vy_target_ > 0) { kb_vy_target_ = 0.0; } break;
          case 'd': key_d_ = false; if (kb_vy_target_ < 0) { kb_vy_target_ = 0.0; } break;
          case 'q': key_q_ = false; if (kb_wz_target_ < 0) { kb_wz_target_ = 0.0; } break;
          case 'e': key_e_ = false; if (kb_wz_target_ > 0) { kb_wz_target_ = 0.0; } break;
        }
      }
    }
  }

  // ========================================================================================
  // 打印状态（RL 运行时也打印）
  // ========================================================================================

  void PrintStatus()
  {
    if (!has_imu_ || !has_motor_feedback_) {
      RCLCPP_WARN(this->get_logger(), "waiting for /imu/data and /motor_feedback ...");
      return;
    }

    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3);

    if (rl_active_.load()) {
      oss << "\n========== dog_policy_test_9 (RL 运行中) ==========\n"
          << "commands: target=[" << kb_vx_target_ << ", " << kb_vy_target_ << ", " << kb_wz_target_ << "] "
          << "actual=[" << kb_vx_ << ", " << kb_vy_ << ", " << kb_wz_ << "]\n"
          << "height: " << kb_height_ << "\n"
          << "projected_gravity: ["
          << robot_state_.projected_gravity[0] << ", "
          << robot_state_.projected_gravity[1] << ", "
          << robot_state_.projected_gravity[2] << "]\n"
          << "tipped_over: " << (tipped_over_.load() ? "⚠️ YES" : "OK") << "\n"
          << "inference_thread: " << (inference_running_ ? "running" : "stopped") << "\n"
          << "out_lpf_alpha: " << output_lpf_alpha_ << "  act_delta_max: " << action_delta_max_ << "\n"
          << "================================================";
    } else {
      oss << "\n========== dog_policy_test_9 (等待中) ==========\n"
          << "mode: 按 y 启动 RL\n"
          << "tipped_over: " << (tipped_over_.load() ? "⚠️ YES" : "OK") << "\n"
          << "projected_gravity: ["
          << robot_state_.projected_gravity[0] << ", "
          << robot_state_.projected_gravity[1] << ", "
          << robot_state_.projected_gravity[2] << "]\n"
          << "obs_mode: " << one_step_obs_dim_ << " 维\n"
          << "================================================";
    }

    RCLCPP_INFO(this->get_logger(), "%s", oss.str().c_str());
  }

private:
  // =========================
  // ROS 订阅器 / 定时器 / 发布器
  // =========================
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<dog_control::msg::MotorFeedback>::SharedPtr motor_feedback_sub_;
  rclcpp::TimerBase::SharedPtr publish_timer_;   // ★ 只剩 200Hz publish_timer
  rclcpp::TimerBase::SharedPtr print_timer_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr emergency_stop_pub_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr dog_state_pub_;

  // =========================
  // 互斥锁
  // =========================
  std::mutex imu_mutex_;
  std::mutex motor_mutex_;
  std::mutex cmd_mutex_;
  std::mutex filter_mutex_;
  std::mutex data_mutex_;
  std::mutex gravity_mutex_;

  // =========================
  // 传感器原始数据
  // =========================
  ImuState latest_imu_raw_;
  struct MotorRaw {
    std::array<double, kNumDofs> position{};
    std::array<double, kNumDofs> velocity{};
  } latest_motor_raw_;

  std::atomic<bool> has_imu_{false};
  std::atomic<bool> has_motor_feedback_{false};

  // =========================
  // 运行时状态（★ 全部 atomic，线程安全）
  // =========================
  std::atomic<bool> rl_active_{false};
  std::atomic<bool> inference_done_{false};
  bool history_warmed_up_{false};
  bool filter_initialized_{false};
  int inference_count_{0};

  // 倾倒保护
  std::atomic<bool> tipped_over_{false};
  std::atomic<int> tipover_recovery_count_{0};
  std::atomic<bool> shutdown_requested_{false};

  std::array<double, kNumDofs> last_motor_cmd_{};

  // ----- 输入滤波状态 -----
  std::array<double, 3> imu_gyro_lpf_prev_{};
  std::array<double, 3> imu_gyro_bias_{};
  std::array<double, kNumDofs> motor_pos_lpf_prev_{};
  std::array<double, kNumDofs> motor_vel_lpf_prev_{};
  std::array<double, kNumDofs> motor_vel_bias_{};

  // 缓存 projected_gravity
  std::array<double, 3> cached_projected_gravity_{{0.0, 0.0, -1.0}};

  // 输出端 LPF 状态
  std::array<double, kNumDofs> output_lpf_prev_{};
  bool output_lpf_initialized_{false};

  RobotState robot_state_;
  ObsScales obs_scales_;
  std::array<float, kNumActions> latest_actions_{};

  // 栈上 obs 缓冲区
  std::array<float, 46> one_step_obs_buf_{};
  std::vector<float> obs_history_;

  std::size_t one_step_obs_dim_{kOneStepObsDim46};
  std::size_t history_obs_dim_{kHistoryObsDim46};

  // =========================
  // 键盘控制
  // =========================
  std::atomic<bool> keyboard_running_{false};
  std::thread keyboard_thread_;
  double kb_vx_target_{0.0};
  double kb_vy_target_{0.0};
  double kb_wz_target_{0.0};
  double kb_vx_{0.0};
  double kb_vy_{0.0};
  double kb_wz_{0.0};
  double kb_height_{0.25};
  double command_ramp_rate_{0.5};

  double kb_forward_speed_{0.5};
  double kb_backward_speed_{-0.5};
  double kb_left_speed_{0.5};
  double kb_right_speed_{-0.5};
  double kb_turn_left_speed_{-0.5};
  double kb_turn_right_speed_{0.5};
  std::map<char, std::chrono::steady_clock::time_point> last_key_time_;

  bool key_w_{false}, key_s_{false};
  bool key_a_{false}, key_d_{false};
  bool key_q_{false}, key_e_{false};

  // ----- 从 YAML 读取的参数 -----
  float action_scale_{0.25f};
  double imu_gyro_lpf_alpha_{1.0};
  double imu_gyro_bias_alpha_{0.001};
  double motor_pos_lpf_alpha_{1.0};
  double motor_vel_lpf_alpha_{1.0};
  double motor_vel_bias_alpha_{0.001};
  double tipover_threshold_{-0.3};

  // test_8+ 新增参数
  double output_lpf_alpha_{1.0};
  float action_delta_max_{100.0f};

  // =========================
  // ★ 推理独立线程
  // =========================
  std::atomic<bool> inference_running_{false};
  std::thread inference_thread_;
  std::chrono::steady_clock::time_point last_inference_time_;

  // =========================
  // ONNX Runtime
  // =========================
  std::unique_ptr<Ort::Env> ort_env_;
  std::unique_ptr<Ort::Session> ort_session_;
  std::string input_name_;
  std::string output_name_;
  Ort::MemoryInfo memory_info_{nullptr};
  std::array<int64_t, 2> input_shape_{1, 0};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<DogPolicyTestNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}