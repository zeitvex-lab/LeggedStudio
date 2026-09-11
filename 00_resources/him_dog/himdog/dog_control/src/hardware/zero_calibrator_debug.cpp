#include "motor_ros2/motor_cfg.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <errno.h>
#include <fcntl.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

// ============================================================
// 前向声明 & 工具函数
// ============================================================

namespace {

// ---------- ANSI 彩色输出 ----------
constexpr const char *kReset  = "\033[0m";
constexpr const char *kRed    = "\033[1;31m";
constexpr const char *kGreen  = "\033[1;32m";
constexpr const char *kYellow = "\033[1;33m";
constexpr const char *kCyan   = "\033[1;36m";
constexpr const char *kGray   = "\033[90m";

// ---------- 时间戳工具 ----------
std::string timestamp_ms() {
  using clock = std::chrono::steady_clock;
  static const auto t0 = clock::now();
  auto now = clock::now();
  auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - t0).count();
  std::ostringstream oss;
  oss << "[" << std::setw(8) << ms << " ms] ";
  return oss.str();
}

// ---------- 分隔线 ----------
void print_sep(const char *title = nullptr) {
  const int width = 64;
  std::cout << kGray;
  if (title) {
    int tl = static_cast<int>(std::string(title).size());
    int left = (width - tl - 2) / 2;
    int right = width - tl - 2 - left;
    std::cout << std::string(left, '=') << " " << title << " "
              << std::string(right, '=') << kReset << "\n";
  } else {
    std::cout << std::string(width, '=') << kReset << "\n";
  }
}

// ---------- to_hex ----------
std::string to_hex(uint32_t v, int width = 2) {
  std::ostringstream oss;
  oss << "0x" << std::hex << std::uppercase << std::setw(width) << std::setfill('0') << v
      << std::dec;
  return oss.str();
}

std::string to_hex(uint8_t v) { return to_hex(static_cast<uint32_t>(v), 2); }

// ---------- CAN 错误码解码 ----------
std::string decode_can_errno(int err) {
  switch (err) {
    case ENETDOWN:   return "网络已关闭 (ENETDOWN) — CAN接口可能未 up";
    case EBADF:      return "无效文件描述符 (EBADF)";
    case EAGAIN:     return "非阻塞操作暂无数据 (EAGAIN/EWOULDBLOCK)";
    // EWOULDBLOCK == EAGAIN on Linux, no separate case needed
    case ENOBUFS:    return "发送缓冲区满 (ENOBUFS)";
    case ETIMEDOUT:  return "操作超时 (ETIMEDOUT)";
    default:         return std::string("errno=") + std::to_string(err) + " (" + strerror(err) + ")";
  }
}

// ---------- 电机协议错误码解码 ----------
std::string decode_motor_error(uint8_t error_code) {
  if (error_code == 0) return "正常 (无错误)";

  std::vector<std::string> bits;
  if (error_code & 0x01) bits.push_back("bit0:未标定");
  if (error_code & 0x02) bits.push_back("bit1:霍尔编码器故障");
  if (error_code & 0x04) bits.push_back("bit2:磁编码器故障");
  if (error_code & 0x08) bits.push_back("bit3:过温");
  if (error_code & 0x10) bits.push_back("bit4:过流");
  if (error_code & 0x20) bits.push_back("bit5:欠压");

  std::string result;
  for (size_t i = 0; i < bits.size(); ++i) {
    if (i > 0) result += ", ";
    result += bits[i];
  }
  return "error_code=0x" + to_hex(error_code) + " → " + result;
}

// ---------- 电机模式名称 ----------
std::string mode_name(uint8_t mode) {
  switch (mode) {
    case 0: return "运控模式(move)";
    case 1: return "位置模式(PP)";
    case 2: return "速度模式(Speed)";
    case 3: return "电流模式(Elect)";
    case 4: return "零点模式(Zero)";
    case 5: return "位置模式(CSP)";
    default: return "未知模式(" + std::to_string(mode) + ")";
  }
}

// ---------- to_upper ----------
std::string to_upper(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
    return static_cast<char>(std::toupper(c));
  });
  return s;
}

// ============================================================
// 电机端点定义
// ============================================================

struct MotorEndpoint {
  const char *joint_name;
  const char *can_if;
  uint8_t motor_id;
};

using LegMotors = std::array<MotorEndpoint, 3>;

const std::unordered_map<std::string, LegMotors> &leg_table() {
  static const std::unordered_map<std::string, LegMotors> kTable = {
      {"FL", {{{"FL_hip", "can0", 0x01},
               {"FL_thigh", "can0", 0x02},
               {"FL_calf", "can0", 0x03}}}},
      {"FR", {{{"FR_hip", "can1", 0x04},
               {"FR_thigh", "can1", 0x05},
               {"FR_calf", "can1", 0x06}}}},
      {"RL", {{{"RL_hip", "can3", 0x0A},
               {"RL_thigh", "can3", 0x0B},
               {"RL_calf", "can3", 0x0C}}}},
      {"RR", {{{"RR_hip", "can2", 0x07},
               {"RR_thigh", "can2", 0x08},
               {"RR_calf", "can2", 0x09}}}},
  };
  return kTable;
}

// ============================================================
// 系统环境预检
// ============================================================

struct PreCheckResult {
  bool can_if_exists;
  bool can_if_up;
  std::string bitrate_info;
  std::string state_info;
};

PreCheckResult check_can_interface(const std::string &can_if) {
  PreCheckResult result{false, false, "", ""};

  // 1) 检查 /sys/class/net/{can_if} 是否存在
  std::string sys_path = "/sys/class/net/" + can_if;
  {
    std::ifstream ifs(sys_path);
    result.can_if_exists = ifs.good();
  }

  if (!result.can_if_exists) {
    return result;
  }

  // 2) 读取 operstate
  {
    std::ifstream ifs(sys_path + "/operstate");
    if (ifs.good()) {
      std::getline(ifs, result.state_info);
    }
    result.can_if_up = (result.state_info == "up");
  }

  // 3) 读取 bitrate (可能存在于 /sys/class/net/{can_if}/bitrate_* 或通过 ip link)
  {
    std::ifstream ifs(sys_path + "/bitrate_baud");
    if (ifs.good()) {
      std::getline(ifs, result.bitrate_info);
    }
  }

  return result;
}

bool check_process_running(const std::string &proc_name) {
  // 简单检查 /proc 中是否有匹配的进程名
  // 不依赖 pgrep，直接扫描 /proc/[pid]/comm
  for (int pid = 1; pid < 65536; ++pid) {
    std::string comm_path = "/proc/" + std::to_string(pid) + "/comm";
    std::ifstream ifs(comm_path);
    if (!ifs.good()) continue;
    std::string comm;
    std::getline(ifs, comm);
    if (comm.find(proc_name) != std::string::npos) {
      return true;
    }
  }
  return false;
}

void run_system_precheck(const LegMotors &motors) {
  print_sep("系统环境预检");
  std::cout << timestamp_ms() << "正在检查系统环境...\n\n";

  // 收集所有需要检查的 CAN 接口（去重）
  std::vector<std::string> can_ifs;
  for (const auto &m : motors) {
    if (std::find(can_ifs.begin(), can_ifs.end(), m.can_if) == can_ifs.end()) {
      can_ifs.push_back(m.can_if);
    }
  }

  bool all_can_ok = true;
  for (const auto &iface : can_ifs) {
    std::cout << "  CAN接口: " << kCyan << iface << kReset << "\n";
    auto check = check_can_interface(iface);
    if (!check.can_if_exists) {
      std::cout << "    " << kRed << "[FAIL] 接口不存在！"
                << "路径 /sys/class/net/" << iface << " 不存在" << kReset << "\n";
      std::cout << "           → 请确认 CAN 硬件已连接，驱动已加载\n";
      std::cout << "           → 尝试: sudo ip link add dev " << iface << " type can\n";
      all_can_ok = false;
    } else {
      std::cout << "    " << kGreen << "[OK]   接口存在于 /sys/class/net/" << iface
                << kReset << "\n";

      if (check.can_if_up) {
        std::cout << "    " << kGreen << "[OK]   接口状态: " << check.state_info << kReset
                  << "\n";
      } else {
        std::cout << "    " << kRed << "[FAIL] 接口状态: " << check.state_info
                  << " (需要 up)" << kReset << "\n";
        std::cout << "           → 尝试: sudo ip link set " << iface
                  << " up type can bitrate 1000000\n";
        all_can_ok = false;
      }

      if (!check.bitrate_info.empty()) {
        std::cout << "    " << kGray << "[INFO] 比特率: " << check.bitrate_info << kReset
                  << "\n";
      }
    }
    std::cout << "\n";
  }

  // 检查 real_motor_controller 是否在运行
  bool controller_running = check_process_running("real_motor_controller");
  if (controller_running) {
    std::cout << "  " << kYellow << "[WARN] 检测到 real_motor_controller 正在运行！" << kReset
              << "\n";
    std::cout << "         → 两个程序同时访问 CAN 接口可能导致数据冲突\n";
    std::cout << "         → 建议先停止: ros2 lifecycle set /real_motor_controller shutdown\n";
    std::cout << "         → 或者: killall real_motor_controller\n\n";
  } else {
    std::cout << "  " << kGreen << "[OK]   real_motor_controller 未运行（无冲突）" << kReset
              << "\n\n";
  }

  // 检查权限
  {
    int test_fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (test_fd < 0) {
      std::cout << "  " << kRed << "[FAIL] 无法创建 CAN socket: "
                << decode_can_errno(errno) << kReset << "\n";
      std::cout << "         → 请使用 sudo 运行此程序，或授予 CAP_NET_RAW 权限\n";
      std::cout << "         → sudo setcap cap_net_raw+ep <可执行文件路径>\n\n";
      all_can_ok = false;
    } else {
      std::cout << "  " << kGreen << "[OK]   CAN socket 创建权限正常" << kReset << "\n\n";
      close(test_fd);
    }
  }

  if (!all_can_ok) {
    std::cout << kRed << ">>> 系统预检发现问题，请先解决上述问题再继续 <<<" << kReset << "\n\n";
  } else {
    std::cout << kGreen << ">>> 系统预检通过 <<<" << kReset << "\n\n";
  }
}

// ============================================================
// CAN 接口连通性测试（逐电机 ping）
// ============================================================

struct PingResult {
  bool success;
  int attempts;
  double elapsed_ms;
  uint8_t error_code;
  float initial_position;
  std::string detail;
};

PingResult ping_motor(const MotorEndpoint &ep) {
  PingResult result{false, 0, 0.0, 0, 0.0f, ""};

  auto t_start = std::chrono::steady_clock::now();

  try {
    RobStrideMotor motor(ep.can_if, static_cast<uint8_t>(0xFF), ep.motor_id, 0);

    const int max_attempts = 3;
    for (int attempt = 1; attempt <= max_attempts; ++attempt) {
      result.attempts = attempt;
      try {
        // 尝试使能电机来确认通信
        auto [pos, vel, torque, temp] = motor.enable_motor();
        result.success = true;
        result.error_code = motor.error_code;
        result.initial_position = pos;

        auto t_end = std::chrono::steady_clock::now();
        result.elapsed_ms =
            std::chrono::duration<double, std::milli>(t_end - t_start).count();

        std::ostringstream oss;
        oss << "pos=" << pos << " rad, vel=" << vel << " rad/s, "
            << "torque=" << torque << " Nm, temp=" << temp << "°C";
        if (motor.error_code != 0) {
          oss << " [WARN: " << decode_motor_error(motor.error_code) << "]";
        }
        result.detail = oss.str();

        // 使能后立即失能，保持安全
        try {
          motor.Disenable_Motor(0);
        } catch (...) {
          // 忽略
        }
        break;
      } catch (const std::exception &e) {
        auto t_end = std::chrono::steady_clock::now();
        result.elapsed_ms =
            std::chrono::duration<double, std::milli>(t_end - t_start).count();
        result.detail = std::string("尝试 #") + std::to_string(attempt) + ": " + e.what();

        if (attempt < max_attempts) {
          std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
      }
    }
  } catch (const std::exception &e) {
    result.detail = std::string("构造失败: ") + e.what();
    result.elapsed_ms = 0;
  }

  return result;
}

bool run_connectivity_test(const LegMotors &motors) {
  print_sep("电机连通性测试");
  std::cout << timestamp_ms() << "正在对 " << motors.size()
            << " 个电机进行 ping 测试 (最多3次重试)...\n\n";

  bool all_ok = true;
  for (size_t i = 0; i < motors.size(); ++i) {
    const auto &ep = motors[i];
    std::cout << "  [" << (i + 1) << "/" << motors.size() << "] "
              << kCyan << ep.joint_name << kReset
              << " (iface=" << ep.can_if << ", id=" << to_hex(ep.motor_id) << ")\n";

    auto ping = ping_motor(ep);

    if (ping.success) {
      std::cout << "    " << kGreen << "[OK]   连接成功" << kReset;
      std::cout << " (尝试 " << ping.attempts << " 次, 耗时 "
                << std::fixed << std::setprecision(1) << ping.elapsed_ms << " ms)\n";
      std::cout << "    " << kGray << "       反馈: " << ping.detail << kReset << "\n";
    } else {
      std::cout << "    " << kRed << "[FAIL] 连接失败！" << kReset << "\n";
      std::cout << "    " << kGray << "       详情: " << ping.detail << kReset << "\n";
      std::cout << "    " << kYellow << "       排查建议:" << kReset << "\n";
      std::cout << "    " << kYellow << "         1. 检查 " << ep.can_if << " 物理接线是否松动"
                << kReset << "\n";
      std::cout << "    " << kYellow << "         2. 确认电机ID " << to_hex(ep.motor_id)
                << " 是否正确" << kReset << "\n";
      std::cout << "    " << kYellow << "         3. 确认电机已上电（LED指示灯）" << kReset
                << "\n";
      std::cout << "    " << kYellow << "         4. 用 candump " << ep.can_if
                << " 查看是否有 CAN 数据" << kReset << "\n";
      std::cout << "    " << kYellow << "         5. 如果是第一个电机失败，检查 CAN 晶振/收发器"
                << kReset << "\n";
      all_ok = false;
    }
    std::cout << "\n";
  }

  if (all_ok) {
    std::cout << kGreen << ">>> 所有电机连通性测试通过 <<<" << kReset << "\n\n";
  } else {
    std::cout << kRed << ">>> 存在电机无法连接，建议先解决再继续 <<<" << kReset << "\n\n";
  }
  return all_ok;
}

// ============================================================
// 读取电机当前状态（用于对比验证）
// ============================================================

struct MotorSnapshot {
  bool valid;
  uint8_t run_mode;
  float mech_pos;
  float velocity;
  float torque;
  uint8_t error_code;
  std::string error_detail;
};

MotorSnapshot read_motor_state(RobStrideMotor &motor, const MotorEndpoint & /*ep*/) {
  MotorSnapshot snap{false, 0xFF, 0.0f, 0.0f, 0.0f, 0, ""};
  try {
    // 读取当前运行模式
    motor.Get_RobStrite_Motor_parameter(0x7005);
    snap.run_mode = static_cast<uint8_t>(motor.drw.run_mode.data);

    // 读取机械角度
    motor.Get_RobStrite_Motor_parameter(0x7010);
    snap.mech_pos = motor.drw.mechPos.data;

    // 尝试获取运控反馈
    try {
      motor.receive_status_frame();
      snap.velocity = motor.velocity_;
      snap.torque = motor.torque_;
    } catch (...) {
      // 运控状态可能不可读，忽略
    }

    snap.error_code = motor.error_code;
    if (snap.error_code != 0) {
      snap.error_detail = decode_motor_error(snap.error_code);
    }
    snap.valid = true;
  } catch (const std::exception &e) {
    snap.error_detail = std::string("读取状态失败: ") + e.what();
  }
  return snap;
}

void print_snapshot(const std::string &label, const MotorSnapshot &snap,
                    const MotorEndpoint &ep) {
  std::cout << "    " << kGray << label << ":" << kReset << "\n";
  if (!snap.valid) {
    std::cout << "      " << kRed << "(无法读取: " << snap.error_detail << ")" << kReset << "\n";
    return;
  }
  std::cout << "      运行模式: " << mode_name(snap.run_mode)
            << " (" << to_hex(snap.run_mode) << ")\n";
  std::cout << "      机械角度: " << std::fixed << std::setprecision(4) << snap.mech_pos
            << " rad\n";
  std::cout << "      接口/ID:  " << ep.can_if << " / " << to_hex(ep.motor_id) << "\n";
  if (!snap.error_detail.empty()) {
    std::cout << "      " << kYellow << "错误: " << snap.error_detail << kReset << "\n";
  }
}

// ============================================================
// 参数解析 & 使用帮助
// ============================================================

void print_usage(const char *prog) {
  std::cout
      << "Usage:\n"
      << "  " << prog << " --leg <FL|FR|RL|RR> [--yes] [--skip-check]\n\n"
      << "Options:\n"
      << "  --leg          Target leg to calibrate (FL/FR/RL/RR).\n"
      << "  --yes          Skip interactive confirmation.\n"
      << "  --skip-check   Skip system pre-check & connectivity test.\n"
      << "  -h, --help     Show this help message.\n\n"
      << "Example:\n"
      << "  ros2 run dog_control zero_calibrator_debug --leg FL\n"
      << "  ros2 run dog_control zero_calibrator_debug --leg FL --yes --skip-check\n";
}

bool parse_args(int argc, char **argv, std::string &leg, bool &skip_confirm,
                bool &skip_check) {
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--leg") {
      if (i + 1 >= argc) {
        std::cerr << kRed << "[ERROR] --leg requires a value." << kReset << "\n";
        return false;
      }
      leg = argv[++i];
    } else if (arg.rfind("--leg=", 0) == 0) {
      leg = arg.substr(std::string("--leg=").size());
    } else if (arg == "--yes") {
      skip_confirm = true;
    } else if (arg == "--skip-check") {
      skip_check = true;
    } else if (arg == "-h" || arg == "--help") {
      print_usage(argv[0]);
      std::exit(0);
    } else {
      std::cerr << kRed << "[ERROR] Unknown argument: " << arg << kReset << "\n";
      return false;
    }
  }

  if (leg.empty()) {
    std::cerr << kRed << "[ERROR] Missing required argument: --leg" << kReset << "\n";
    return false;
  }
  return true;
}

bool require_confirmation(const std::string &leg) {
  std::cout << "\n" << kYellow << "⚠  请确认:" << kReset << "\n";
  std::cout << "  1) 目标腿 " << kCyan << leg << kReset
            << " 的3个关节已手动放置在机械零位\n";
  std::cout << "  2) 机器人已抬离地面，无负载\n";
  std::cout << "  3) real_motor_controller 未在运行\n";
  std::cout << "  4) 急停开关已准备就绪\n\n";
  std::cout << "输入 y 继续标定, 输入其他任何字符取消: ";
  std::cout.flush();

  std::string input;
  std::getline(std::cin, input);

  if (input != "y") {
    std::cerr << kRed << "[ABORT] 用户取消。未发送任何零位指令。" << kReset << "\n";
    return false;
  }
  return true;
}

void print_leg_info(const std::string &leg, const LegMotors &motors) {
  print_sep("标定信息");
  std::cout << "  单腿机械零位标定工具 (DEBUG 版本)\n";
  std::cout << "  目标腿:   " << kCyan << leg << kReset << "\n";
  std::cout << "  电机列表:\n";
  for (const auto &m : motors) {
    std::cout << "    - " << std::left << std::setw(12) << m.joint_name
              << "  iface=" << std::setw(5) << m.can_if
              << "  id=" << to_hex(m.motor_id) << "\n";
  }
  std::cout << "\n";
}

// ============================================================
// 主动标定流程（带详细日志）
// ============================================================

struct CalibrationStepResult {
  bool set_zero_ok;
  bool mode_restore_ok;
  bool disable_ok;
  MotorSnapshot before;
  MotorSnapshot after;
  double step_elapsed_ms;
  std::string set_zero_error;
  std::string mode_restore_error;
  std::string disable_error;
};

CalibrationStepResult calibrate_single_motor(
    std::unique_ptr<RobStrideMotor> &motor,
    const MotorEndpoint &ep,
    size_t step_idx,
    size_t total_steps) {

  CalibrationStepResult result{false, false, false, {}, {}, 0.0, "", "", ""};

  auto t_start = std::chrono::steady_clock::now();

  std::cout << "\n" << timestamp_ms() << kCyan
            << "[STEP " << step_idx << "/" << total_steps << "] "
            << ep.joint_name << kReset
            << " (iface=" << ep.can_if << ", id=" << to_hex(ep.motor_id) << ")\n";

  // --- 读取标定前状态 ---
  std::cout << timestamp_ms() << "  读取标定前状态...\n";
  result.before = read_motor_state(*motor, ep);
  print_snapshot("标定前", result.before, ep);

  // --- Step A: 发送 Set_ZeroPos ---
  std::cout << timestamp_ms() << "  发送 Set_ZeroPos 指令...\n";
  try {
    motor->Set_ZeroPos();
    result.set_zero_ok = true;
    std::cout << "    " << kGreen << "[OK] Set_ZeroPos 指令已发送" << kReset << "\n";
  } catch (const std::exception &e) {
    result.set_zero_ok = false;
    result.set_zero_error = e.what();
    std::cout << "    " << kRed << "[FAIL] Set_ZeroPos 失败: " << e.what() << kReset << "\n";
    std::cout << "    " << kYellow << "  → 请检查电机是否已使能（能否听到电机工作声）" << kReset
              << "\n";
    std::cout << "    " << kYellow << "  → 请检查 CAN 总线是否有其他设备在发送冲突数据"
              << kReset << "\n";
    std::cout << "    " << kYellow << "  → 尝试用 cangen/candump 手动验证 CAN 通信" << kReset
              << "\n";
  }

  std::this_thread::sleep_for(std::chrono::milliseconds(200));

  // --- Step B: 恢复运控模式 ---
  std::cout << timestamp_ms() << "  恢复运控模式 (0x7005 → move_control_mode)...\n";
  try {
    motor->Set_RobStrite_Motor_parameter(0X7005, move_control_mode, Set_mode);
    std::this_thread::sleep_for(std::chrono::milliseconds(150));

    motor->Get_RobStrite_Motor_parameter(0x7005);
    std::this_thread::sleep_for(std::chrono::milliseconds(150));

    uint8_t current_mode = static_cast<uint8_t>(motor->drw.run_mode.data);
    if (current_mode == move_control_mode) {
      result.mode_restore_ok = true;
      std::cout << "    " << kGreen << "[OK] 运控模式已恢复 (mode=" << to_hex(current_mode)
                << ")" << kReset << "\n";
    } else {
      result.mode_restore_ok = false;
      result.mode_restore_error = "模式未切换，当前=" + to_hex(current_mode);
      std::cout << "    " << kYellow << "[WARN] 模式切换似乎未生效！当前模式: "
                << to_hex(current_mode) << " (" << mode_name(current_mode) << ")" << kReset
                << "\n";
      std::cout << "    " << kYellow << "  → 电机可能处于保护状态，尝试先 Disenable 再重试"
                << kReset << "\n";
    }
  } catch (const std::exception &e) {
    result.mode_restore_ok = false;
    result.mode_restore_error = e.what();
    std::cout << "    " << kRed << "[FAIL] 恢复运控模式失败: " << e.what() << kReset << "\n";
  }

  std::this_thread::sleep_for(std::chrono::milliseconds(200));

  // --- 读取标定后状态 ---
  std::cout << timestamp_ms() << "  读取标定后状态...\n";
  result.after = read_motor_state(*motor, ep);
  print_snapshot("标定后", result.after, ep);

  // --- 对比 ---
  if (result.before.valid && result.after.valid) {
    double pos_delta = std::abs(result.after.mech_pos - result.before.mech_pos);
    bool mode_changed = (result.before.run_mode != result.after.run_mode);
    std::cout << "    " << kGray << "对比: 角度变化 = " << std::fixed
              << std::setprecision(4) << pos_delta << " rad"
              << ", 模式变化 = " << (mode_changed ? "是" : "否") << kReset << "\n";
  }

  auto t_end = std::chrono::steady_clock::now();
  result.step_elapsed_ms =
      std::chrono::duration<double, std::milli>(t_end - t_start).count();

  std::cout << timestamp_ms() << "  本电机耗时: " << std::fixed << std::setprecision(1)
            << result.step_elapsed_ms << " ms\n";

  return result;
}

// ============================================================
// 汇总报告
// ============================================================

void print_final_report(const std::string &leg,
                        const LegMotors &motors,
                        const std::vector<CalibrationStepResult> &results) {
  print_sep("汇总报告");
  std::cout << "\n";
  std::cout << "  目标腿: " << kCyan << leg << kReset << "\n\n";

  int ok_count = 0;
  int fail_count = 0;

  // 表头
  std::cout << "  " << std::left << std::setw(12) << "关节名"
            << std::setw(10) << "SetZero" << std::setw(10) << "模式恢复"
            << std::setw(10) << "Disable" << std::setw(12) << "耗时(ms)"
            << "备注\n";
  std::cout << "  " << std::string(64, '-') << "\n";

  for (size_t i = 0; i < results.size(); ++i) {
    const auto &r = results[i];
    const auto &ep = motors[i];

    std::string sz = r.set_zero_ok ? (kGreen + std::string("OK") + kReset)
                                   : (kRed + std::string("FAIL") + kReset);
    std::string mr = r.mode_restore_ok ? (kGreen + std::string("OK") + kReset)
                                       : (kYellow + std::string("WARN") + kReset);
    std::string dis = r.disable_ok ? (kGreen + std::string("OK") + kReset)
                                   : (kRed + std::string("FAIL") + kReset);
    std::string note;
    if (!r.set_zero_error.empty()) note += r.set_zero_error;
    if (!r.mode_restore_error.empty()) {
      if (!note.empty()) note += "; ";
      note += r.mode_restore_error;
    }

    std::cout << "  " << std::left << std::setw(12) << ep.joint_name
              << sz << std::setw(6) << ""
              << mr << std::setw(5) << ""
              << dis << std::setw(5) << ""
              << std::fixed << std::setprecision(1) << std::setw(12) << r.step_elapsed_ms
              << kGray << note << kReset << "\n";

    if (r.set_zero_ok && r.mode_restore_ok && r.disable_ok) {
      ++ok_count;
    } else {
      ++fail_count;
    }
  }

  std::cout << "\n";
  std::cout << "  结果: " << kGreen << ok_count << " 成功" << kReset
            << ", " << (fail_count > 0 ? kRed : kGreen) << fail_count
            << " 失败" << kReset << "\n\n";

  if (fail_count > 0) {
    std::cout << kYellow << "  排查建议:" << kReset << "\n";
    for (size_t i = 0; i < results.size(); ++i) {
      if (results[i].set_zero_ok && results[i].mode_restore_ok && results[i].disable_ok) {
        continue;
      }
      const auto &ep = motors[i];
      const auto &r = results[i];

      std::cout << "  ● " << ep.joint_name << ":\n";
      if (!r.set_zero_ok) {
        std::cout << "    - SetZero 失败";
        if (r.set_zero_error.find("No frame") != std::string::npos ||
            r.set_zero_error.find("receive") != std::string::npos) {
          std::cout << " (未收到电机回复)";
          std::cout << "\n      → CAN 总线通信中断，请检查接线";
          std::cout << "\n      → 确认电机ID " << to_hex(ep.motor_id)
                    << " 与实际电机一致";
          std::cout << "\n      → 尝试: cansend " << ep.can_if
                    << " " << to_hex((uint32_t)0x03 << 24 | 0xFF << 8 | ep.motor_id)
                    << "#0100000000000000";
        } else {
          std::cout << ": " << r.set_zero_error;
        }
        std::cout << "\n";
      }
      if (!r.mode_restore_ok) {
        std::cout << "    - 模式恢复异常: " << r.mode_restore_error << "\n";
      }
      if (!r.disable_ok) {
        std::cout << "    - Disable 失败: " << r.disable_error << "\n";
      }
    }
    std::cout << "\n";
  } else {
    std::cout << kGreen << "  ✓ 所有电机零位标定成功完成！" << kReset << "\n\n";
  }
}

} // namespace

// ============================================================
// main
// ============================================================

int main(int argc, char **argv) {
  std::string leg;
  bool skip_confirm = false;
  bool skip_check = false;

  std::cout << "\n";
  print_sep("零位标定工具 (DEBUG)");
  std::cout << timestamp_ms() << "程序启动\n\n";

  if (!parse_args(argc, argv, leg, skip_confirm, skip_check)) {
    print_usage(argv[0]);
    return 1;
  }

  // --- 解析腿名称 ---
  leg = to_upper(leg);
  const auto &table = leg_table();
  const auto it = table.find(leg);
  if (it == table.end()) {
    // 检查用户是否输入了旧的格式
    std::string hint;
    if (leg == "LF") hint = " → 请使用 FL";
    else if (leg == "RF") hint = " → 请使用 FR";
    else if (leg == "LB") hint = " → 请使用 RL";
    else if (leg == "RB") hint = " → 请使用 RR";

    std::cerr << kRed << "[ERROR] 无效的腿标识: " << leg << "。支持: FL/FR/RL/RR" << hint
              << kReset << "\n";
    print_usage(argv[0]);
    return 1;
  }
  const LegMotors &selected = it->second;

  // --- 打印标定信息 ---
  print_leg_info(leg, selected);

  // --- 系统预检 ---
  if (!skip_check) {
    run_system_precheck(selected);

    // --- 连通性测试 ---
    bool connectivity_ok = run_connectivity_test(selected);
    if (!connectivity_ok) {
      std::cout << kYellow << "是否忽略连通性错误继续标定？(y/n): " << kReset;
      std::cout.flush();
      std::string input;
      std::getline(std::cin, input);
      if (input != "y") {
        std::cout << kRed << "[ABORT] 用户选择不继续。" << kReset << "\n";
        return 2;
      }
      std::cout << "\n";
    }
  } else {
    std::cout << timestamp_ms() << kYellow << "[WARN] --skip-check: 跳过系统预检和连通性测试"
              << kReset << "\n\n";
  }

  // --- 用户确认 ---
  if (!skip_confirm && !require_confirmation(leg)) {
    return 2;
  }
  if (skip_confirm) {
    std::cout << timestamp_ms() << kYellow << "[WARN] --yes: 跳过用户确认" << kReset << "\n";
  }

  // --- 创建电机对象 ---
  print_sep("开始标定");
  std::cout << timestamp_ms() << "创建电机连接对象...\n\n";

  std::vector<std::unique_ptr<RobStrideMotor>> motors;
  motors.reserve(selected.size());
  for (const auto &m : selected) {
    try {
      motors.emplace_back(std::make_unique<RobStrideMotor>(
          m.can_if, static_cast<uint8_t>(0xFF), m.motor_id, 0));
      std::cout << timestamp_ms() << "  " << kGreen << "[OK] " << m.joint_name
                << " 对象创建成功 (socket_fd=" << motors.back()->socket_fd << ")"
                << kReset << "\n";
    } catch (const std::exception &e) {
      std::cout << timestamp_ms() << "  " << kRed << "[FAIL] " << m.joint_name
                << " 对象创建失败: " << e.what() << kReset << "\n";
      motors.emplace_back(nullptr);
    }
  }

  // --- 逐电机标定 ---
  std::vector<CalibrationStepResult> cal_results;
  cal_results.reserve(motors.size());

  for (size_t i = 0; i < motors.size(); ++i) {
    if (!motors[i]) {
      CalibrationStepResult fail_res{};
      fail_res.set_zero_ok = false;
      fail_res.set_zero_error = "电机对象创建失败，跳过";
      fail_res.mode_restore_ok = false;
      fail_res.disable_ok = false;
      cal_results.push_back(fail_res);
      continue;
    }

    auto cal = calibrate_single_motor(motors[i], selected[i], i + 1, motors.size());
    cal_results.push_back(cal);

    std::this_thread::sleep_for(std::chrono::milliseconds(150));
  }

  // --- 失能所有电机 ---
  print_sep("失能电机");
  std::cout << timestamp_ms() << "正在失能所有目标电机...\n";
  for (size_t i = 0; i < motors.size(); ++i) {
    if (!motors[i]) {
      cal_results[i].disable_ok = false;
      cal_results[i].disable_error = "电机对象不存在";
      continue;
    }
    const auto &ep = selected[i];
    try {
      motors[i]->Disenable_Motor(0);
      cal_results[i].disable_ok = true;
      std::cout << "  " << kGreen << "[OK] " << ep.joint_name << " 已失能" << kReset << "\n";
    } catch (const std::exception &e) {
      cal_results[i].disable_ok = false;
      cal_results[i].disable_error = e.what();
      std::cout << "  " << kRed << "[FAIL] " << ep.joint_name << " 失能失败: " << e.what()
                << kReset << "\n";
      std::cout << "    " << kYellow << "→ 电机可能仍在使能状态，请手动断电确保安全"
                << kReset << "\n";
    }
  }

  // --- 汇总报告 ---
  print_final_report(leg, selected, cal_results);

  // --- 最终退出码 ---
  bool all_ok = true;
  for (const auto &r : cal_results) {
    if (!r.set_zero_ok || !r.disable_ok) {
      all_ok = false;
      break;
    }
  }

  if (all_ok) {
    std::cout << kGreen << "[DONE] 所有电机零位标定流程完成，电机已失能。" << kReset << "\n";
    return 0;
  }

  std::cerr << kRed << "[DONE-WITH-ERRORS] 标定流程完成但存在问题，请查看上方汇总报告。"
            << kReset << "\n";
  return 3;
}