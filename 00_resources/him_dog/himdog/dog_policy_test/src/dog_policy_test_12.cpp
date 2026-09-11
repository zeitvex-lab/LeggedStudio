// ========================================================================================
// dog_policy_test_12.cpp — 基于 test_11 + 内置模型热切换
// ========================================================================================
//
// ★ 新增功能（相比 test_11）：
//   - YAML 配置模型列表（model_names / model_paths / model_obs_dims）
//   - 运行时键盘快捷键切换模型：[ 上一个 / ] 下一个
//   - 切换时自动重置 history / actions / 滤波状态
//   - 导航模式 nav_cmd 的 model_path 自动匹配模型列表
//
// ★ 控制模式（YAML 配置 control_mode）：
//   0 → 键盘控制（默认，适合调试）
//   1 → joy 手柄控制（订阅 /joy，需要 joy_node）
//   2 → 导航控制（订阅 /nav_cmd DogNavCommand，由 dog_nav 路径规划控制）
//
// ★ 键盘快捷键（所有模式通用）：
//   y → 启动 RL    r → 重置    f → 关闭 RL
//   z → 站起       p → 蹲下    Esc → 退出
//   N → 上一个模型  M → 下一个模型  （★ test_12 新增）
//       切换模型时自动关闭 RL（回到默认站姿），按 y 重新启动 RL
//
// ★ joy 手柄模型切换（control_mode=1，★ 新增，对应 Python play_xbox）：
//   B / Start → 下一个模型    Back → 上一个模型
//   切换时自动关闭 RL，按 Y 重新启动
//
// 运行命令：
// ros2 run dog_policy_test dog_policy_test_12 --ros-args --params-file ./src/dog_policy_test/config/policy_params_12.yaml

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <sensor_msgs/msg/joy.hpp>
#include <std_msgs/msg/bool.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include "dog_control/msg/motor_feedback.hpp"
#include <dog_nav/msg/dog_nav_command.hpp>

#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
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
#include <fstream>
#include <cstring>
#include <sched.h>
#include <sys/resource.h>

#include <stdexcept>
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

// ----- nav_cmd / joy 超时 -----
constexpr double kNavCmdTimeoutSec = 0.5;  // 500ms 无新消息 → 归零
constexpr double kJoyTimeoutSec = 0.5;     // 500ms 无新消息 → 归零

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

// ★ 模型条目
struct ModelEntry
{
  std::string name;
  std::string path;
  int one_obs_dim;  // 45 or 46
  // ★ 每个模型独立的 joy 手柄参数（切换模型时跟随生效）
  // 默认值 = 历史全局值，旧 YAML 没填 joy 数组时仍能跑
  double joy_vx_max{0.6};
  double joy_vy_max{0.5};
  double joy_wz_max{0.8};
  double joy_deadband{0.1};
  int    joy_axis_vx{1};
  int    joy_axis_vy{0};
  int    joy_axis_wz{3};
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

// ========================================================================================
// ★ SystemMonitor — 同 test_11，完全不变
// ========================================================================================

class SystemMonitor
{
public:
  struct Config
  {
    double cpu_warn_percent{85.0};
    double mem_warn_percent{85.0};
    double temp_warn_celsius{75.0};
    double inference_dt_warn_ms{15.0};
    double inference_dt_overrun_ms{25.0};
    int sample_interval_ms{1000};
  };

  SystemMonitor() = default;

  void Start(const Config & cfg)
  {
    cfg_ = cfg;
    running_ = true;
    DetectThermalZone();
    monitor_thread_ = std::thread(&SystemMonitor::MonitorLoop, this);
  }

  void Stop()
  {
    running_ = false;
    if (monitor_thread_.joinable()) {
      monitor_thread_.join();
    }
  }

  void RecordInferenceTime(double dt_ms)
  {
    last_inference_dt_ms_.store(dt_ms, std::memory_order_relaxed);
    double prev_max = max_inference_dt_ms_.load(std::memory_order_relaxed);
    while (dt_ms > prev_max &&
           !max_inference_dt_ms_.compare_exchange_weak(prev_max, dt_ms,
             std::memory_order_relaxed, std::memory_order_relaxed)) {
    }
    inference_count_.fetch_add(1, std::memory_order_relaxed);
  }

  void ResetInferenceStats()
  {
    max_inference_dt_ms_.store(0.0, std::memory_order_relaxed);
    inference_count_.store(0, std::memory_order_relaxed);
    overrun_count_.store(0, std::memory_order_relaxed);
  }

private:
  void MonitorLoop()
  {
    setpriority(PRIO_PROCESS, 0, 19);
    uint64_t prev_total = 0, prev_idle = 0;
    ReadCpuTimes(prev_total, prev_idle);

    while (running_) {
      std::this_thread::sleep_for(std::chrono::milliseconds(cfg_.sample_interval_ms));

      double cpu_percent = 0.0;
      {
        uint64_t cur_total = 0, cur_idle = 0;
        if (ReadCpuTimes(cur_total, cur_idle)) {
          const uint64_t d_total = cur_total - prev_total;
          const uint64_t d_idle = cur_idle - prev_idle;
          if (d_total > 0) {
            cpu_percent = 100.0 * static_cast<double>(d_total - d_idle) / static_cast<double>(d_total);
          }
          prev_total = cur_total;
          prev_idle = cur_idle;
        }
      }

      double mem_total_mb = 0.0, mem_used_mb = 0.0, mem_percent = 0.0;
      {
        uint64_t total_kb = 0, available_kb = 0;
        if (ReadMemInfo(total_kb, available_kb)) {
          mem_total_mb = static_cast<double>(total_kb) / 1024.0;
          const double used_kb = static_cast<double>(total_kb) - static_cast<double>(available_kb);
          mem_used_mb = used_kb / 1024.0;
          if (total_kb > 0) {
            mem_percent = 100.0 * used_kb / static_cast<double>(total_kb);
          }
        }
      }

      double rss_mb = ReadSelfRssMb();
      double temp_c = ReadCpuTemperature();

      const double last_dt = last_inference_dt_ms_.load(std::memory_order_relaxed);
      const double max_dt = max_inference_dt_ms_.load(std::memory_order_relaxed);
      const int inf_count = inference_count_.load(std::memory_order_relaxed);

      if (last_dt > cfg_.inference_dt_overrun_ms) {
        overrun_count_.fetch_add(1, std::memory_order_relaxed);
      }
      max_inference_dt_ms_.store(0.0, std::memory_order_relaxed);
      const int overruns = overrun_count_.load(std::memory_order_relaxed);

      // 资源/告警打印已按需求精简（不再向终端输出 SystemMonitor 信息）；
      // overrun 计数等仍在后台维护，供 monitor_.ResetInferenceStats() 等接口使用。
      (void)cpu_percent; (void)mem_used_mb; (void)mem_total_mb;
      (void)mem_percent; (void)rss_mb; (void)temp_c;
      (void)last_dt; (void)max_dt; (void)inf_count; (void)overruns;
    }
  }

  bool ReadCpuTimes(uint64_t & total, uint64_t & idle)
  {
    std::ifstream ifs("/proc/stat");
    if (!ifs.is_open()) return false;
    std::string line;
    if (!std::getline(ifs, line)) return false;
    unsigned long long user, nice, system, idle_val, iowait, irq, softirq, steal;
    std::istringstream iss(line);
    std::string cpu_label;
    iss >> cpu_label >> user >> nice >> system >> idle_val >> iowait >> irq >> softirq >> steal;
    idle = idle_val + iowait;
    total = user + nice + system + idle_val + iowait + irq + softirq + steal;
    return true;
  }

  bool ReadMemInfo(uint64_t & total_kb, uint64_t & available_kb)
  {
    std::ifstream ifs("/proc/meminfo");
    if (!ifs.is_open()) return false;
    total_kb = 0;
    available_kb = 0;
    std::string line;
    while (std::getline(ifs, line)) {
      if (line.compare(0, 9, "MemTotal:") == 0) {
        std::istringstream iss(line.substr(9));
        iss >> total_kb;
      } else if (line.compare(0, 13, "MemAvailable:") == 0) {
        std::istringstream iss(line.substr(13));
        iss >> available_kb;
      }
      if (total_kb > 0 && available_kb > 0) break;
    }
    return (total_kb > 0);
  }

  double ReadSelfRssMb()
  {
    std::ifstream ifs("/proc/self/status");
    if (!ifs.is_open()) return 0.0;
    std::string line;
    while (std::getline(ifs, line)) {
      if (line.compare(0, 6, "VmRSS:") == 0) {
        std::istringstream iss(line.substr(6));
        uint64_t rss_kb = 0;
        iss >> rss_kb;
        return static_cast<double>(rss_kb) / 1024.0;
      }
    }
    return 0.0;
  }

  void DetectThermalZone()
  {
    const char * candidates[] = {
      "/sys/class/thermal/thermal_zone0/temp",
      "/sys/class/thermal/thermal_zone1/temp",
      "/sys/class/thermal/thermal_zone2/temp",
      "/sys/class/thermal/thermal_zone3/temp",
    };
    double max_temp = -999.0;
    std::string best_path;
    for (const char * path : candidates) {
      std::ifstream ifs(path);
      if (!ifs.is_open()) continue;
      int temp_millideg = 0;
      ifs >> temp_millideg;
      if (temp_millideg > 0) {
        double t = static_cast<double>(temp_millideg) / 1000.0;
        if (t > max_temp) { max_temp = t; best_path = path; }
      }
    }
    if (!best_path.empty()) { thermal_zone_path_ = best_path; }
  }

  double ReadCpuTemperature()
  {
    if (thermal_zone_path_.empty()) return -1.0;
    std::ifstream ifs(thermal_zone_path_);
    if (!ifs.is_open()) return -1.0;
    int temp_millideg = 0;
    ifs >> temp_millideg;
    return static_cast<double>(temp_millideg) / 1000.0;
  }

private:
  Config cfg_;
  std::atomic<bool> running_{false};
  std::thread monitor_thread_;
  std::atomic<double> last_inference_dt_ms_{0.0};
  std::atomic<double> max_inference_dt_ms_{0.0};
  std::atomic<int> inference_count_{0};
  std::atomic<int> overrun_count_{0};
  std::string thermal_zone_path_;
};

}  // namespace


class DogPolicyTestNode : public rclcpp::Node
{
public:
  DogPolicyTestNode()
  : Node("dog_policy_test_node")
  {
    // =========================
    // ★ 0. 读取模型列表参数
    // =========================
    this->declare_parameter("model_names", std::vector<std::string>{});
    this->declare_parameter("model_paths", std::vector<std::string>{});
    this->declare_parameter("model_obs_dims", std::vector<int>{});
    this->declare_parameter("default_model_index", 0);

    // ★ 每个模型独立的 joy 手柄参数（数组，与 model_paths 同序同长）
    // 留空默认 → 用 ModelEntry 里的默认值（历史全局值）
    this->declare_parameter("joy_vx_max_arr",   std::vector<double>{});
    this->declare_parameter("joy_vy_max_arr",   std::vector<double>{});
    this->declare_parameter("joy_wz_max_arr",   std::vector<double>{});
    this->declare_parameter("joy_deadband_arr", std::vector<double>{});
    this->declare_parameter("joy_axis_vx_arr",  std::vector<int>{});
    this->declare_parameter("joy_axis_vy_arr",  std::vector<int>{});
    this->declare_parameter("joy_axis_wz_arr",  std::vector<int>{});

    const auto model_names = this->get_parameter("model_names").as_string_array();
    const auto model_paths = this->get_parameter("model_paths").as_string_array();
    const auto model_obs_dims = this->get_parameter("model_obs_dims").as_integer_array();

    if (model_names.empty() || model_paths.empty() || model_obs_dims.empty()) {
      std::string err =
        "model_names / model_paths / model_obs_dims 参数为空！\n"
        "  实际读取到: model_names.size=" + std::to_string(model_names.size()) +
        ", model_paths.size=" + std::to_string(model_paths.size()) +
        ", model_obs_dims.size=" + std::to_string(model_obs_dims.size()) + "\n"
        "  ★ 请检查运行命令是否用了正确的 YAML:\n"
        "    --params-file ./src/dog_policy_test/config/policy_params_12.yaml\n"
        "    （注意是 policy_params_12.yaml，不是 policy_params.yaml！两者不能混用，\n"
        "     policy_params.yaml 里没有 model_names/paths/dims 这三个数组参数）";
      RCLCPP_ERROR(this->get_logger(), "%s", err.c_str());
      throw std::runtime_error(err);
    }

    if (model_names.size() != model_paths.size() || model_names.size() != model_obs_dims.size()) {
      char buf[256];
      std::snprintf(buf, sizeof(buf),
        "model_names(%zu) / model_paths(%zu) / model_obs_dims(%zu) 长度不一致！"
        "三个数组长度必须相同。", model_names.size(), model_paths.size(), model_obs_dims.size());
      RCLCPP_ERROR(this->get_logger(), "%s", buf);
      throw std::runtime_error(buf);
    }

    // 读取 joy 数组（可能为空 → 旧配置，用 ModelEntry 默认值）
    const auto joy_vx_max_arr   = this->get_parameter("joy_vx_max_arr").as_double_array();
    const auto joy_vy_max_arr   = this->get_parameter("joy_vy_max_arr").as_double_array();
    const auto joy_wz_max_arr   = this->get_parameter("joy_wz_max_arr").as_double_array();
    const auto joy_deadband_arr = this->get_parameter("joy_deadband_arr").as_double_array();
    const auto joy_axis_vx_arr  = this->get_parameter("joy_axis_vx_arr").as_integer_array();
    const auto joy_axis_vy_arr  = this->get_parameter("joy_axis_vy_arr").as_integer_array();
    const auto joy_axis_wz_arr  = this->get_parameter("joy_axis_wz_arr").as_integer_array();

    // joy 数组长度校验：要么全填且长度==模型数，要么全空（旧配置）
    const std::size_t n_models = model_names.size();
    auto arr_ok = [&](const auto & arr) {
      return arr.size() == n_models;
    };
    bool joy_arrays_ok = arr_ok(joy_vx_max_arr)   && arr_ok(joy_vy_max_arr)
                       && arr_ok(joy_wz_max_arr)   && arr_ok(joy_deadband_arr)
                       && arr_ok(joy_axis_vx_arr)  && arr_ok(joy_axis_vy_arr)
                       && arr_ok(joy_axis_wz_arr);
    bool joy_arrays_empty = joy_vx_max_arr.empty() && joy_vy_max_arr.empty()
                          && joy_wz_max_arr.empty() && joy_deadband_arr.empty()
                          && joy_axis_vx_arr.empty() && joy_axis_vy_arr.empty()
                          && joy_axis_wz_arr.empty();
    if (joy_arrays_empty) {
      // 未配置 joy_*_arr → 共用默认 joy 参数（静默）
    } else if (!joy_arrays_ok) {
      // joy_*_arr 长度不一致 → 改用默认 joy 参数（静默）
    }

    for (std::size_t i = 0; i < model_names.size(); ++i) {
      ModelEntry entry;
      entry.name       = model_names[i];
      entry.path       = model_paths[i];
      entry.one_obs_dim = model_obs_dims[i];
      // joy 参数：数组配置正确才覆盖默认值
      if (joy_arrays_ok) {
        entry.joy_vx_max   = joy_vx_max_arr[i];
        entry.joy_vy_max   = joy_vy_max_arr[i];
        entry.joy_wz_max   = joy_wz_max_arr[i];
        entry.joy_deadband = joy_deadband_arr[i];
        entry.joy_axis_vx  = joy_axis_vx_arr[i];
        entry.joy_axis_vy  = joy_axis_vy_arr[i];
        entry.joy_axis_wz  = joy_axis_wz_arr[i];
      }
      model_list_.push_back(entry);
    }

    int default_idx = this->get_parameter("default_model_index").as_int();
    if (default_idx < 0 || static_cast<std::size_t>(default_idx) >= model_list_.size()) {
      RCLCPP_WARN(this->get_logger(),
        "default_model_index=%d 越界，使用 0", default_idx);
      default_idx = 0;
    }

    // 打印模型列表（仅模型名称）
    printf("★ 模型列表（共 %zu 个）:\n", model_list_.size());
    for (std::size_t i = 0; i < model_list_.size(); ++i) {
      const char * marker = (static_cast<int>(i) == default_idx) ? " ◀ default" : "";
      printf("  [%zu] %s%s\n",
             i, model_list_[i].name.c_str(), marker);
    }

    // =========================
    // ★ 1. 创建 ONNX 环境 + 加载默认模型
    // =========================
    ort_env_ = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "dog_policy");
    memory_info_ = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    if (!LoadModel(default_idx)) {
      std::string err =
        "默认模型(default_model_index=" + std::to_string(default_idx) +
        ") 加载失败！\n"
        "  路径: " + model_list_[static_cast<std::size_t>(default_idx)].path + "\n"
        "  ★ 请检查: 文件是否存在、是否可读、onnx 是否损坏。";
      RCLCPP_ERROR(this->get_logger(), "%s", err.c_str());
      throw std::runtime_error(err);
    }

    // =========================
    // ★ 1.1 读取控制模式
    // =========================
    this->declare_parameter("control_mode", 0);
    control_mode_ = this->get_parameter("control_mode").as_int();

    if (control_mode_ < 0 || control_mode_ > 2) {
      char buf[128];
      std::snprintf(buf, sizeof(buf),
        "不支持的 control_mode = %d，只支持 0(键盘)/1(joy)/2(导航)！", control_mode_);
      RCLCPP_ERROR(this->get_logger(), "%s", buf);
      throw std::runtime_error(buf);
    }

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
    // ★ 1.5b 读取 joy 手柄速度参数（单值版，向后兼容）
    // =========================
    // 这 7 个单值参数仅作旧配置的 fallback：
    //   - 配了 joy_*_arr 数组 → LoadModel 会用数组里的每模型值覆盖
    //   - 没配数组           → ModelEntry 默认值生效（与这里一致）
    // 所以这里的成员赋值随后会被 LoadModel(default) 覆盖，但 declare 仍需保留
    // 以兼容老的 policy_params_12.yaml。
    this->declare_parameter("joy_vx_max", 0.6);
    this->declare_parameter("joy_vy_max", 0.5);
    this->declare_parameter("joy_wz_max", 0.8);
    this->declare_parameter("joy_deadband", 0.1);
    this->declare_parameter("joy_axis_vx", 1);    // 左摇杆 Y
    this->declare_parameter("joy_axis_vy", 0);    // 左摇杆 X
    this->declare_parameter("joy_axis_wz", 3);    // 右摇杆 X
    joy_vx_max_ = this->get_parameter("joy_vx_max").as_double();
    joy_vy_max_ = this->get_parameter("joy_vy_max").as_double();
    joy_wz_max_ = this->get_parameter("joy_wz_max").as_double();
    joy_deadband_ = this->get_parameter("joy_deadband").as_double();
    joy_axis_vx_ = this->get_parameter("joy_axis_vx").as_int();
    joy_axis_vy_ = this->get_parameter("joy_axis_vy").as_int();
    joy_axis_wz_ = this->get_parameter("joy_axis_wz").as_int();

    // =========================
    // ★ 1.5c 读取导航速度限幅参数
    // =========================
    this->declare_parameter("nav_vx_max", 0.6);
    this->declare_parameter("nav_vy_max", 0.5);
    this->declare_parameter("nav_wz_max", 0.8);
    this->declare_parameter("nav_height_min", 0.18);
    this->declare_parameter("nav_height_max", 0.32);
    nav_vx_max_ = this->get_parameter("nav_vx_max").as_double();
    nav_vy_max_ = this->get_parameter("nav_vy_max").as_double();
    nav_wz_max_ = this->get_parameter("nav_wz_max").as_double();
    nav_height_min_ = this->get_parameter("nav_height_min").as_double();
    nav_height_max_ = this->get_parameter("nav_height_max").as_double();

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
    // 1.9 读取系统监控参数
    // =========================
    this->declare_parameter("monitor_cpu_warn", 85.0);
    this->declare_parameter("monitor_mem_warn", 85.0);
    this->declare_parameter("monitor_temp_warn", 75.0);
    this->declare_parameter("monitor_inference_dt_warn", 15.0);
    this->declare_parameter("monitor_inference_dt_overrun", 25.0);
    this->declare_parameter("monitor_interval_ms", 1000);

    SystemMonitor::Config monitor_cfg;
    monitor_cfg.cpu_warn_percent = this->get_parameter("monitor_cpu_warn").as_double();
    monitor_cfg.mem_warn_percent = this->get_parameter("monitor_mem_warn").as_double();
    monitor_cfg.temp_warn_celsius = this->get_parameter("monitor_temp_warn").as_double();
    monitor_cfg.inference_dt_warn_ms = this->get_parameter("monitor_inference_dt_warn").as_double();
    monitor_cfg.inference_dt_overrun_ms = this->get_parameter("monitor_inference_dt_overrun").as_double();
    monitor_cfg.sample_interval_ms = this->get_parameter("monitor_interval_ms").as_int();

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
    // ★ 3.5 根据控制模式订阅对应话题
    // =========================
    if (control_mode_ == 1) {
      joy_sub_ = this->create_subscription<sensor_msgs::msg::Joy>(
        "/joy", 10,
        std::bind(&DogPolicyTestNode::JoyCallback, this, std::placeholders::_1));
    } else if (control_mode_ == 2) {
      nav_cmd_sub_ = this->create_subscription<dog_nav::msg::DogNavCommand>(
        "/nav_cmd", 10,
        std::bind(&DogPolicyTestNode::NavCmdCallback, this, std::placeholders::_1));
    }

    // =========================
    // 4. 发布 /joint_states + /dog_state
    // =========================
    joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);
    emergency_stop_pub_ = this->create_publisher<std_msgs::msg::Bool>("/emergency_stop", 10);
    dog_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/dog_state", 10);

    // =========================
    // 5. 推理独立线程
    // =========================
    inference_running_ = true;
    last_inference_time_ = std::chrono::steady_clock::now();
    inference_thread_ = std::thread(&DogPolicyTestNode::InferenceLoop, this);

    // =========================
    // 6. publish_timer（200Hz）
    // =========================
    publish_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(5),
      std::bind(&DogPolicyTestNode::PublishTimerCallback, this));

    // （定时打印状态的 print_timer_ 已按需求移除，终端不再每500ms输出大表）

    // =========================
    // 8. 启动系统监控线程
    // =========================
    monitor_.Start(monitor_cfg);

    const char * mode_str = ControlModeStr();
    RCLCPP_INFO(this->get_logger(),
      "dog_policy_test_12 started — model='%s' (%d/%zu), control_mode=%s, tipover=%.2f",
      model_list_[current_model_idx_].name.c_str(),
      current_model_idx_, model_list_.size(),
      mode_str, tipover_threshold_);
  }

  ~DogPolicyTestNode()
  {
    StopInferenceThread();
    StopKeyboardThread();
    monitor_.Stop();
  }

  bool IsKeyboardRunning() const { return keyboard_running_.load(); }

private:
  // ========================================================================================
  // ★★ 模型加载 / 热切换
  // ========================================================================================

  bool LoadModel(int index)
  {
    if (index < 0 || static_cast<std::size_t>(index) >= model_list_.size()) {
      RCLCPP_ERROR(this->get_logger(), "LoadModel: index=%d 越界", index);
      return false;
    }

    const ModelEntry & entry = model_list_[index];

    // 检查文件是否存在
    {
      std::ifstream test(entry.path);
      if (!test.is_open()) {
        RCLCPP_ERROR(this->get_logger(), "模型文件不存在: %s", entry.path.c_str());
        return false;
      }
    }

    // 更新 obs dim
    if (entry.one_obs_dim == 46) {
      one_step_obs_dim_ = kOneStepObsDim46;
      history_obs_dim_ = kHistoryObsDim46;
    } else if (entry.one_obs_dim == 45) {
      one_step_obs_dim_ = kOneStepObsDim45;
      history_obs_dim_ = kHistoryObsDim45;
    } else {
      RCLCPP_ERROR(this->get_logger(), "不支持的 one_obs_dim = %d", entry.one_obs_dim);
      return false;
    }

    // 创建 ONNX Session
    try {
      Ort::SessionOptions session_options;
      session_options.SetIntraOpNumThreads(1);
      session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

      auto new_session = std::make_unique<Ort::Session>(
        *ort_env_, entry.path.c_str(), session_options);

      Ort::AllocatorWithDefaultOptions allocator;
      auto input_name_alloc = new_session->GetInputNameAllocated(0, allocator);
      std::string new_input_name = input_name_alloc.get();
      auto output_name_alloc = new_session->GetOutputNameAllocated(0, allocator);
      std::string new_output_name = output_name_alloc.get();

      // ★ 加锁替换 session
      {
        std::lock_guard<std::mutex> lock(model_mutex_);
        ort_session_ = std::move(new_session);
        input_name_ = std::move(new_input_name);
        output_name_ = std::move(new_output_name);
        input_shape_ = {1, static_cast<int64_t>(history_obs_dim_)};
      }

      current_model_idx_ = index;
      current_model_path_ = entry.path;

      // ★ 切模型时把该模型的 joy 手柄参数同步进成员变量
      // （启动时 LoadModel(default) 也会走这里 → 默认模型的 joy 生效）
      joy_vx_max_   = entry.joy_vx_max;
      joy_vy_max_   = entry.joy_vy_max;
      joy_wz_max_   = entry.joy_wz_max;
      joy_deadband_ = entry.joy_deadband;
      joy_axis_vx_  = entry.joy_axis_vx;
      joy_axis_vy_  = entry.joy_axis_vy;
      joy_axis_wz_  = entry.joy_axis_wz;

      // 重置所有推理状态
      ResetInferenceState();

      // 终端精简：只打印当前模型名称
      printf("★ 当前模型: [%d/%zu] %s\n",
             index + 1, model_list_.size(), entry.name.c_str());

      return true;

    } catch (const Ort::Exception & e) {
      RCLCPP_ERROR(this->get_logger(), "ONNX 模型加载失败: %s — %s", entry.path.c_str(), e.what());
      return false;
    }
  }

  // ★ 切换到下一个/上一个模型（环形）
  void SwitchModel(int direction)
  {
    if (model_list_.size() <= 1) {
      return;  // 只有一个模型，无法切换（静默）
    }

    int new_idx = static_cast<int>(current_model_idx_) + direction;
    // 环形
    if (new_idx < 0) new_idx = static_cast<int>(model_list_.size()) - 1;
    if (static_cast<std::size_t>(new_idx) >= model_list_.size()) new_idx = 0;

    // 当前模型由 LoadModel 统一打印，这里不再重复
    if (!LoadModel(new_idx)) {
      RCLCPP_ERROR(this->get_logger(), "★ 模型切换失败！保持当前模型。");
    }
  }

  // ★ 重置推理状态（切换模型 / 按 r 时调用）
  void ResetInferenceState()
  {
    FillStandingHistory();
    latest_actions_.fill(0.0f);
    last_motor_cmd_.fill(0.0);
    output_lpf_prev_.fill(0.0);
    output_lpf_initialized_ = false;
    inference_done_.store(false);
    inference_count_ = 0;
    history_warmed_up_ = false;
  }

  // ========================================================================================
  // ★ 辅助：控制模式字符串
  // ========================================================================================

  const char * ControlModeStr() const
  {
    switch (control_mode_) {
      case 0: return "keyboard";
      case 1: return "joy";
      case 2: return "navigation";
      default: return "unknown";
    }
  }

  // ========================================================================================
  // ★ JoyCallback — 接收 /joy 手柄数据
  // ========================================================================================

  void JoyCallback(const sensor_msgs::msg::Joy::SharedPtr msg)
  {
    if (!msg) return;

    auto axis_safe = [&msg](int idx) -> double {
      if (idx < 0 || static_cast<size_t>(idx) >= msg->axes.size()) return 0.0;
      return msg->axes[static_cast<size_t>(idx)];
    };

    double axis_vx = axis_safe(joy_axis_vx_);
    double axis_vy = axis_safe(joy_axis_vy_);
    double axis_wz = axis_safe(joy_axis_wz_);

    auto apply_deadband = [this](double v) -> double {
      return (std::abs(v) < joy_deadband_) ? 0.0 : v;
    };
    axis_vx = apply_deadband(axis_vx);
    axis_vy = apply_deadband(axis_vy);
    axis_wz = apply_deadband(axis_wz);

    axis_vx = axis_vx;
    axis_vy = axis_vy;
    axis_wz = axis_wz;

    if (control_mode_ == 1) {
      auto button_pressed = [&msg](int idx) -> bool {
        if (idx < 0 || static_cast<size_t>(idx) >= msg->buttons.size()) return false;
        return msg->buttons[static_cast<size_t>(idx)] == 1;
      };

      if (button_pressed(3)) {  // Y → 开启 RL
        if (!rl_active_.load() && !tipped_over_.load()) {
          rl_active_.store(true);
          history_warmed_up_ = false;
        }
      }

      if (button_pressed(2)) {  // X → 关闭 RL
        rl_active_.store(false);
      }

      if (button_pressed(0)) {  // A → 重置
        ResetInferenceState();
        cmd_vx_target_ = 0.0; cmd_vy_target_ = 0.0; cmd_wz_target_ = 0.0;
        cmd_vx_ = 0.0; cmd_vy_ = 0.0; cmd_wz_ = 0.0;
        monitor_.ResetInferenceStats();
      }

      if (button_pressed(5)) {  // RB → 站起
        kb_height_ = std::min(0.35, kb_height_ + 0.02);
        printf("★ height = %.2f\n", kb_height_);
      }

      if (button_pressed(4)) {  // LB → 蹲下
        kb_height_ = std::max(0.20, kb_height_ - 0.02);
        printf("★ height = %.2f\n", kb_height_);
      }

      // ★ 模型切换（对应 Python play_xbox_onnx: B=下一个, Back=上一个, Start=下一个）
      // 边沿触发：仅在上升沿切换，避免 /joy 连续发布导致按住时疯狂切换
      const bool b_now     = button_pressed(1);  // B
      const bool back_now  = button_pressed(6);  // Back
      const bool start_now = button_pressed(7);  // Start

      if (b_now && !prev_joy_btn_b_) {
        rl_active_.store(false);
        SwitchModel(+1);
      }
      if (back_now && !prev_joy_btn_back_) {
        rl_active_.store(false);
        SwitchModel(-1);
      }
      if (start_now && !prev_joy_btn_start_) {
        rl_active_.store(false);
        SwitchModel(+1);
      }

      prev_joy_btn_b_ = b_now;
      prev_joy_btn_back_ = back_now;
      prev_joy_btn_start_ = start_now;
    }

    std::lock_guard<std::mutex> lock(joy_mutex_);
    joy_vx_ = axis_vx * joy_vx_max_;
    joy_vy_ = axis_vy * joy_vy_max_;
    joy_wz_ = axis_wz * joy_wz_max_;
    joy_time_ = std::chrono::steady_clock::now();
  }

  // ========================================================================================
  // ★ NavCmdCallback — 接收 /nav_cmd (DogNavCommand) 导航指令
  // ========================================================================================

  void NavCmdCallback(const dog_nav::msg::DogNavCommand::SharedPtr msg)
  {
    if (!msg) return;
    std::lock_guard<std::mutex> lock(nav_cmd_mutex_);

    auto is_valid = [](float v) -> bool {
      return std::isfinite(v);
    };
    if (!is_valid(msg->vx) || !is_valid(msg->vy) || !is_valid(msg->wz) || !is_valid(msg->height)) {
      return;  // nav_cmd 含 NaN/Inf，丢弃（静默）
    }

    nav_cmd_vx_ = std::clamp(static_cast<double>(msg->vx), -nav_vx_max_, nav_vx_max_);
    nav_cmd_vy_ = std::clamp(static_cast<double>(msg->vy), -nav_vy_max_, nav_vy_max_);
    nav_cmd_wz_ = std::clamp(static_cast<double>(msg->wz), -nav_wz_max_, nav_wz_max_);

    nav_cmd_height_ = std::clamp(static_cast<double>(msg->height), nav_height_min_, nav_height_max_);

    // ★ model_path 匹配模型列表
    if (!msg->model_path.empty()) {
      nav_cmd_model_path_ = msg->model_path;
      nav_cmd_model_matched_idx_ = -1;  // -1 = 未匹配
      for (std::size_t i = 0; i < model_list_.size(); ++i) {
        if (model_list_[i].path == msg->model_path ||
            model_list_[i].name == msg->model_path) {
          nav_cmd_model_matched_idx_ = static_cast<int>(i);
          break;
        }
      }
    }

    nav_cmd_time_ = std::chrono::steady_clock::now();
  }

  // ========================================================================================
  // ImuCallback / MotorFeedbackCallback — 同 test_11
  // ========================================================================================

  void ImuCallback(const sensor_msgs::msg::Imu::SharedPtr msg)
  {
    if (!msg) return;

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
    }

    const auto grav = RotateWorldToBody(quat_copy, {0.0, 0.0, -1.0});
    {
      std::lock_guard<std::mutex> lock(gravity_mutex_);
      cached_projected_gravity_ = grav;
    }

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
  }

  // ========================================================================================
  // ★ InferenceLoop — 同 test_11，但 ONNX 推理部分加 model_mutex_ 保护
  // ========================================================================================

  void InferenceLoop()
  {
    const auto inference_period = std::chrono::milliseconds(20);  // 50Hz
    auto next_tick = std::chrono::steady_clock::now() + inference_period;

    while (inference_running_) {
      std::this_thread::sleep_until(next_tick);
      auto now = std::chrono::steady_clock::now();
      next_tick += inference_period;
      if (now > next_tick + inference_period) {
        next_tick = now + inference_period;
      }

      const double dt = std::chrono::duration<double>(now - last_inference_time_).count();
      last_inference_time_ = now;
      const double dt_clamped = std::clamp(dt, 0.01, 0.05);

      if (!rl_active_.load()) continue;

      if (tipped_over_.load()) {
        RunFilteringOnly();
        continue;
      }

      // ----- 传感器同步读取 -----
      ImuState imu_snapshot;
      MotorRaw motor_snapshot;
      {
        std::scoped_lock lock(imu_mutex_, motor_mutex_);
        imu_snapshot = latest_imu_raw_;
        motor_snapshot = latest_motor_raw_;
      }

      // ----- IMU 滤波 -----
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

      {
        std::lock_guard<std::mutex> lock(gravity_mutex_);
        robot_state_.projected_gravity = cached_projected_gravity_;
      }

      // ----- 电机滤波 -----
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

      // ----- ★ 命令渐变（根据 control_mode 切换命令源）-----
      {
        std::lock_guard<std::mutex> lock(data_mutex_);
        const double max_delta = command_ramp_rate_ * dt_clamped;

        if (control_mode_ == 0) {
          // ★ 键盘模式
          kb_vx_ += std::clamp(kb_vx_target_ - kb_vx_, -max_delta, max_delta);
          kb_vy_ += std::clamp(kb_vy_target_ - kb_vy_, -max_delta, max_delta);
          kb_wz_ += std::clamp(kb_wz_target_ - kb_wz_, -max_delta, max_delta);
          robot_state_.commands = {kb_vx_, kb_vy_, kb_wz_};

        } else if (control_mode_ == 1) {
          // ★ Joy 手柄模式
          double target_vx = 0.0, target_vy = 0.0, target_wz = 0.0;
          {
            std::lock_guard<std::mutex> j_lock(joy_mutex_);
            const double elapsed = std::chrono::duration<double>(
              std::chrono::steady_clock::now() - joy_time_).count();
            if (elapsed < kJoyTimeoutSec) {
              target_vx = joy_vx_;
              target_vy = joy_vy_;
              target_wz = joy_wz_;
            }
          }
          cmd_vx_target_ = target_vx;
          cmd_vy_target_ = target_vy;
          cmd_wz_target_ = target_wz;
          cmd_vx_ += std::clamp(target_vx - cmd_vx_, -max_delta, max_delta);
          cmd_vy_ += std::clamp(target_vy - cmd_vy_, -max_delta, max_delta);
          cmd_wz_ += std::clamp(target_wz - cmd_wz_, -max_delta, max_delta);
          robot_state_.commands = {cmd_vx_, cmd_vy_, cmd_wz_};

        } else {
          // ★ 导航模式（control_mode_ == 2）
          double target_vx = 0.0, target_vy = 0.0, target_wz = 0.0;
          double nav_height = kb_height_;
          int nav_model_idx = -1;
          {
            std::lock_guard<std::mutex> cv_lock(nav_cmd_mutex_);
            const double elapsed = std::chrono::duration<double>(
              std::chrono::steady_clock::now() - nav_cmd_time_).count();
            if (elapsed < kNavCmdTimeoutSec) {
              target_vx = nav_cmd_vx_;
              target_vy = nav_cmd_vy_;
              target_wz = nav_cmd_wz_;
              nav_height = nav_cmd_height_;
              nav_model_idx = nav_cmd_model_matched_idx_;
            }
          }
          cmd_vx_target_ = target_vx;
          cmd_vy_target_ = target_vy;
          cmd_wz_target_ = target_wz;
          cmd_vx_ += std::clamp(target_vx - cmd_vx_, -max_delta, max_delta);
          cmd_vy_ += std::clamp(target_vy - cmd_vy_, -max_delta, max_delta);
          cmd_wz_ += std::clamp(target_wz - cmd_wz_, -max_delta, max_delta);
          robot_state_.commands = {cmd_vx_, cmd_vy_, cmd_wz_};
          robot_state_.height_command = nav_height;

          // ★ 导航请求切换模型（匹配到模型列表中的条目时触发）
          //   LoadModel 内部会打印当前模型，这里不再重复输出
          if (nav_model_idx >= 0 && nav_model_idx != static_cast<int>(current_model_idx_)) {
            LoadModel(nav_model_idx);
          }
        }

        // 键盘和 joy 模式使用 kb_height_，导航模式已在上面设置
        if (control_mode_ != 2) {
          robot_state_.height_command = kb_height_;
        }
      }

      // ----- 栈上构造单步 observation -----
      const bool include_height = (one_step_obs_dim_ == kOneStepObsDim46);
      const std::size_t obs_dim = BuildOneStepObservationStack(
        robot_state_, obs_scales_, latest_actions_, include_height, one_step_obs_buf_);

      // ----- 更新历史 observation -----
      if (!history_warmed_up_) {
        std::copy(one_step_obs_buf_.begin(), one_step_obs_buf_.begin() + obs_dim, obs_history_.begin());
        history_warmed_up_ = true;
      } else {
        UpdateObservationHistory(one_step_obs_buf_, one_step_obs_dim_, obs_history_, history_obs_dim_);
      }

      // ----- ★ ONNX 推理（加 model_mutex_ 保护） -----
      try {
        std::lock_guard<std::mutex> model_lock(model_mutex_);

        Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
          memory_info_, obs_history_.data(), history_obs_dim_,
          input_shape_.data(), input_shape_.size());

        const char * input_names[] = {input_name_.c_str()};
        const char * output_names[] = {output_name_.c_str()};
        auto output_tensors = ort_session_->Run(
          Ort::RunOptions{nullptr}, input_names, &input_tensor, 1, output_names, 1);

        float * raw_output = output_tensors[0].GetTensorMutableData<float>();

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

        monitor_.RecordInferenceTime(dt * 1000.0);

        inference_count_++;

      } catch (const Ort::Exception & e) {
        RCLCPP_ERROR(this->get_logger(), "ONNX inference failed: %s", e.what());
      }
    }
  }

  // ========================================================================================
  // RunFilteringOnly — RL 未激活 / 翻倒时只跑滤波
  // ========================================================================================

  void RunFilteringOnly()
  {
    ImuState imu_snapshot;
    {
      std::lock_guard<std::mutex> lock(imu_mutex_);
      imu_snapshot = latest_imu_raw_;
    }

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

    {
      std::lock_guard<std::mutex> lock(gravity_mutex_);
      robot_state_.projected_gravity = cached_projected_gravity_;
    }

    MotorRaw motor_snapshot;
    {
      std::lock_guard<std::mutex> lock(motor_mutex_);
      motor_snapshot = latest_motor_raw_;
    }

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

        motor_vel_bias_[i] += motor_vel_bias_alpha_ * (raw_vel - motor_vel_bias_[i]);
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
  }

  // ========================================================================================
  // ★ FillStandingHistory — 用零填充 standing 姿态的 history
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
  // ★ PublishTimerCallback — 200Hz 发布
  // ========================================================================================

  void PublishTimerCallback()
  {
    if (shutdown_requested_.load()) {
      rclcpp::shutdown();
      return;
    }

    // ★ 松手检测（仅键盘模式 0 生效）
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
  // 发布 /dog_state 诊断话题（与 test_11 一致）
  // ========================================================================================

  void PublishDogState(const sensor_msgs::msg::JointState & js_msg)
  {
    sensor_msgs::msg::JointState state_msg;
    state_msg.header.stamp = js_msg.header.stamp;
    state_msg.name = {"cmd_vx", "cmd_vy", "cmd_wz",
                      "cmd_vx_target", "cmd_vy_target", "cmd_wz_target",
                      "grav_x", "grav_y", "grav_z",
                      "height_cmd"};

    if (control_mode_ == 0) {
      state_msg.position = {
        kb_vx_, kb_vy_, kb_wz_,
        kb_vx_target_, kb_vy_target_, kb_wz_target_,
        robot_state_.projected_gravity[0],
        robot_state_.projected_gravity[1],
        robot_state_.projected_gravity[2],
        kb_height_
      };
    } else {
      state_msg.position = {
        cmd_vx_, cmd_vy_, cmd_wz_,
        cmd_vx_target_, cmd_vy_target_, cmd_wz_target_,
        robot_state_.projected_gravity[0],
        robot_state_.projected_gravity[1],
        robot_state_.projected_gravity[2],
        kb_height_
      };
    }
    dog_state_pub_->publish(state_msg);
  }

  // ========================================================================================
  // ★ 键盘线程（新增 [ / ] 模型切换）
  // ========================================================================================

  void StartKeyboardThread()
  {
    keyboard_running_ = true;
    keyboard_thread_ = std::thread(&DogPolicyTestNode::KeyboardLoop, this);
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
    struct termios old_tio, new_tio;
    tcgetattr(STDIN_FILENO, &old_tio);
    new_tio = old_tio;
    new_tio.c_lflag &= ~(ICANON | ECHO);
    tcsetattr(STDIN_FILENO, TCSANOW, &new_tio);

    while (keyboard_running_) {
      fd_set set;
      FD_ZERO(&set);
      FD_SET(STDIN_FILENO, &set);
      timeval tv;
      tv.tv_sec = 0;
      tv.tv_usec = 50000;  // 50ms
      const int ret = select(STDIN_FILENO + 1, &set, nullptr, nullptr, &tv);
      if (ret <= 0) continue;

      char c = 0;
      if (read(STDIN_FILENO, &c, 1) != 1) continue;

      if (c == 27) {  // ESC
        char seq[2] = {0, 0};
        read(STDIN_FILENO, &seq[0], 1);
        read(STDIN_FILENO, &seq[1], 1);
        if (seq[0] == '[') {
          // Arrow keys — ignore
        } else {
          // Plain ESC → shutdown
          printf("  [键盘] ESC → 退出\n");
          shutdown_requested_.store(true);
        }
        continue;
      }

      switch (c) {
        case 'y':
          if (!rl_active_.load() && !tipped_over_.load()) {
            rl_active_.store(true);
            history_warmed_up_ = false;
          }
          break;
        case 'f':
          rl_active_.store(false);
          break;
        case 'r':
          ResetInferenceState();
          {
            std::lock_guard<std::mutex> lock(data_mutex_);
            cmd_vx_target_ = 0.0; cmd_vy_target_ = 0.0; cmd_wz_target_ = 0.0;
            cmd_vx_ = 0.0; cmd_vy_ = 0.0; cmd_wz_ = 0.0;
            if (control_mode_ == 0) {
              kb_vx_target_ = 0.0; kb_vy_target_ = 0.0; kb_wz_target_ = 0.0;
              kb_vx_ = 0.0; kb_vy_ = 0.0; kb_wz_ = 0.0;
            }
          }
          monitor_.ResetInferenceStats();
          break;
        case 'z':
          {
            std::lock_guard<std::mutex> lock(data_mutex_);
            kb_height_ = std::min(0.35, kb_height_ + 0.02);
          }
          printf("★ height = %.2f\n", kb_height_);
          break;
        case 'p':
          {
            std::lock_guard<std::mutex> lock(data_mutex_);
            kb_height_ = std::max(0.20, kb_height_ - 0.02);
          }
          printf("★ height = %.2f\n", kb_height_);
          break;
        case 'N':  // ★ 上一个模型
          {
            rl_active_.store(false);
            SwitchModel(-1);
          }
          break;
        case 'M':  // ★ 下一个模型
          {
            rl_active_.store(false);
            SwitchModel(+1);
          }
          break;
        default:
          break;
      }

      // ★ 移动键（仅键盘模式 0）：按键保持 + 松手归零
      //   按住时终端自动重复发字符，持续刷新 last_key_time_；
      //   松手后 150ms 无新字符，由 CheckKeyRelease() 归零。
      {
        std::lock_guard<std::mutex> lock(data_mutex_);
        if (control_mode_ == 0) {
          switch (c) {
            case 'w': key_w_ = true; last_key_time_['w'] = std::chrono::steady_clock::now(); break;
            case 's': key_s_ = true; last_key_time_['s'] = std::chrono::steady_clock::now(); break;
            case 'a': key_a_ = true; last_key_time_['a'] = std::chrono::steady_clock::now(); break;
            case 'd': key_d_ = true; last_key_time_['d'] = std::chrono::steady_clock::now(); break;
            case 'q': key_q_ = true; last_key_time_['q'] = std::chrono::steady_clock::now(); break;
            case 'e': key_e_ = true; last_key_time_['e'] = std::chrono::steady_clock::now(); break;
            default: break;
          }

          // 由按键状态重算移动目标
          kb_vx_target_ = key_w_ ? kb_forward_speed_ : (key_s_ ? kb_backward_speed_ : 0.0);
          kb_vy_target_ = key_a_ ? kb_left_speed_ : (key_d_ ? kb_right_speed_ : 0.0);
          kb_wz_target_ = key_q_ ? kb_turn_left_speed_ : (key_e_ ? kb_turn_right_speed_ : 0.0);
        }
      }
    }

    tcsetattr(STDIN_FILENO, TCSANOW, &old_tio);
  }

  // ========================================================================================
  // ★ 松手检测（仅键盘模式 0）—— 按键保持 + 松手归零
  // ========================================================================================

  void CheckKeyRelease()
  {
    // Joy / 导航模式不需要松手检测
    if (control_mode_ != 0) return;

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
          default: break;
        }
      }
    }
  }

  // ========================================================================================
  // 打印状态
  // ========================================================================================

  // PrintStatus（每500ms打印状态大表）已按需求移除，终端只保留模型/RL/高度/倾倒/错误信息

  void StopInferenceThread()
  {
    inference_running_ = false;
    if (inference_thread_.joinable()) {
      inference_thread_.join();
    }
  }

private:
  // =========================
  // ROS 订阅器 / 定时器 / 发布器
  // =========================
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<dog_control::msg::MotorFeedback>::SharedPtr motor_feedback_sub_;
  rclcpp::Subscription<dog_nav::msg::DogNavCommand>::SharedPtr nav_cmd_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Joy>::SharedPtr joy_sub_;
  rclcpp::TimerBase::SharedPtr publish_timer_;
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
  std::mutex nav_cmd_mutex_;
  std::mutex joy_mutex_;
  std::mutex model_mutex_;   // ★ 保护 ONNX session 切换

  // =========================
  // 传感器原始数据
  // =========================
  ImuState latest_imu_raw_;
  struct MotorRaw {
    std::array<double, kNumDofs> position{};
    std::array<double, kNumDofs> velocity{};
  } latest_motor_raw_;

  // =========================
  // 运行时状态
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

  // 输入滤波状态
  std::array<double, 3> imu_gyro_lpf_prev_{};
  std::array<double, 3> imu_gyro_bias_{};
  std::array<double, kNumDofs> motor_pos_lpf_prev_{};
  std::array<double, kNumDofs> motor_vel_lpf_prev_{};
  std::array<double, kNumDofs> motor_vel_bias_{};

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
  // ★ 模型列表 + 当前索引
  // =========================
  std::vector<ModelEntry> model_list_;
  std::size_t current_model_idx_{0};

  // =========================
  // ★ 控制模式 (0=键盘, 1=joy, 2=导航)
  // =========================
  int control_mode_{0};

  // =========================
  // ★ nav_cmd / joy 共用渐变变量（mode 1 和 mode 2 使用）
  // =========================
  double cmd_vx_{0.0};
  double cmd_vy_{0.0};
  double cmd_wz_{0.0};
  double cmd_vx_target_{0.0};
  double cmd_vy_target_{0.0};
  double cmd_wz_target_{0.0};

  // =========================
  // ★ nav_cmd 模式原始数据（mode 2 使用）
  // =========================
  double nav_cmd_vx_{0.0};
  double nav_cmd_vy_{0.0};
  double nav_cmd_wz_{0.0};
  double nav_cmd_height_{0.25};
  std::string nav_cmd_model_path_;
  int nav_cmd_model_matched_idx_{-1};  // ★ 匹配到的模型列表索引
  std::chrono::steady_clock::time_point nav_cmd_time_{std::chrono::steady_clock::now()};

  // 导航速度/体高限幅（从 YAML 读取）
  double nav_vx_max_{0.6};
  double nav_vy_max_{0.5};
  double nav_wz_max_{0.8};
  double nav_height_min_{0.18};
  double nav_height_max_{0.32};

  // =========================
  // ★ Joy 模式原始数据（mode 1 使用）
  // =========================
  double joy_vx_{0.0};
  double joy_vy_{0.0};
  double joy_wz_{0.0};
  std::chrono::steady_clock::time_point joy_time_;
  double joy_vx_max_{0.6};
  double joy_vy_max_{0.5};
  double joy_wz_max_{0.8};
  double joy_deadband_{0.1};
  int joy_axis_vx_{1};
  int joy_axis_vy_{0};
  int joy_axis_wz_{3};

  // ★ joy 模型切换按钮边沿检测（B=1, Back=6, Start=7）
  bool prev_joy_btn_b_{false};
  bool prev_joy_btn_back_{false};
  bool prev_joy_btn_start_{false};

  // =========================
  // 键盘控制变量（mode 0 使用）
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

  double output_lpf_alpha_{1.0};
  float action_delta_max_{100.0f};

  // 推理独立线程
  std::atomic<bool> inference_running_{false};
  std::thread inference_thread_;
  std::chrono::steady_clock::time_point last_inference_time_;

  // ONNX Runtime
  std::unique_ptr<Ort::Env> ort_env_;
  std::unique_ptr<Ort::Session> ort_session_;
  std::string input_name_;
  std::string output_name_;
  Ort::MemoryInfo memory_info_{nullptr};
  std::array<int64_t, 2> input_shape_{1, 0};

  // 当前模型路径（用于 nav_cmd 比对）
  std::string current_model_path_;

  // 系统监控
  SystemMonitor monitor_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  // ★ 构造函数失败（模型加载失败 / 参数错误 / control_mode 非法）会抛 std::runtime_error，
  // 这里捕获后打印醒目错误信息，避免进程静默崩溃或留个半死的僵尸节点。
  std::shared_ptr<DogPolicyTestNode> node;
  try {
    node = std::make_shared<DogPolicyTestNode>();
  } catch (const std::exception & e) {
    printf("\n");
    printf("╔══════════════════════════════════════════════════╗\n");
    printf("║  ❌ dog_policy_test_12 启动失败                  ║\n");
    printf("╠══════════════════════════════════════════════════╣\n");
    printf("  原因: %s\n", e.what());
    printf("                                                    \n");
    printf("  ★ 排查清单:                                       \n");
    printf("    1. 运行命令是否用了 --params-file .../policy_params_12.yaml\n");
    printf("       （不能用 policy_params.yaml，它没有模型列表参数）\n");
    printf("    2. model_paths 里的 onnx 文件路径是否真实存在\n");
    printf("    3. 三个数组 model_names/paths/dims 长度是否一致\n");
    printf("    4. default_model_index 是否在模型列表范围内\n");
    printf("╚══════════════════════════════════════════════════╝\n");
    printf("\n");
    rclcpp::shutdown();
    return 1;
  }

  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
