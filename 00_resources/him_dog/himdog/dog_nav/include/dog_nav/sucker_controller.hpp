// ========================================================================================
// sucker_controller.hpp — 吸盘舵机 + 气泵串口控制器（header-only）
// ========================================================================================
//
// 串口协议（发往 STM32，与 test_serial.py 一致）:
//   格式: "{angle_left},{angle_right},{num}\n"   (ASCII)
//     angle_left / angle_right: 舵机角度 0~270
//       0   = 动作位（吸取 / 放置）
//       270 = 存储位（抬起）
//     num: 气泵控制
//       1 = 泵 ON（吸取）
//       0 = 泵 OFF（释放）
//   左舵机安装方向相反，发送前做镜像: send = 270 - logic
//
// 动作时序（基于时间推进的状态机，需在循环/timer 里周期调用 Update）:
//
//   取箱 StartPick:
//     phase 0  下到箱位   (down_l, down_r, pump=1)   等 move_sec
//     phase 1  建立真空   (保持不动,    pump=1)      等 hold_sec
//     phase 2  抬回存储   (270, 270,    pump=1)      等 move_sec   箱吸在存储位
//     完成（泵保持 ON，箱吸着）
//
//   放箱 StartPlace:
//     phase 0  下到放位   (down_l, down_r, pump=1)   等 move_sec   箱仍吸着
//     phase 1  泵 OFF     (保持不动,    pump=0)      等 hold_sec   释放箱
//     phase 2  抬回存储   (270, 270,    pump=0)      等 move_sec   空抬回
//     完成（泵 OFF，无箱）
//
// 用法:
//   SuckerController sc;
//   sc.Open("/dev/ttyUSB0");
//   sc.SetMoveSec(3.0);
//   sc.SetHoldSec(0.5);
//   sc.Home();                         // 归位到存储位，泵 OFF
//
//   sc.StartPick("left", now_sec);     // 启动取箱
//   while (sc.IsActive()) {
//     sc.Update(now_sec);              // 在 timer/主循环里周期调用
//     now_sec = GetNow();
//   }
//   // ... 移动到归位区 ...
//   sc.StartPlace("left", now_sec);    // 启动放箱
//   while (sc.IsActive()) { sc.Update(now_sec); ... }
//
// 注: 日志走 printf。若要接 ROS 日志，把 Log() 函数体换成 RCLCPP_INFO 即可。
//
#ifndef DOG_NAV_SUCKER_CONTROLLER_HPP_
#define DOG_NAV_SUCKER_CONTROLLER_HPP_

#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <cerrno>
#include <string>
#include <algorithm>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>

namespace dog_nav
{

// ========================================================================================
// SuckerController — 吸盘 + 气泵控制器
// ========================================================================================
class SuckerController
{
public:
  SuckerController() = default;
  ~SuckerController() { Close(); }

  // 禁止拷贝（持有 fd）
  SuckerController(const SuckerController &) = delete;
  SuckerController & operator=(const SuckerController &) = delete;

  // ========================================================================================
  // Open — 打开串口
  // ========================================================================================
  bool Open(const std::string & port, int baudrate = 115200)
  {
    fd_ = ::open(port.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd_ < 0) {
      Log("★ 无法打开吸盘串口 %s: %s", port.c_str(), std::strerror(errno));
      return false;
    }

    // 清除 O_NONBLOCK，恢复阻塞读写
    int flags = ::fcntl(fd_, F_GETFL, 0);
    ::fcntl(fd_, F_SETFL, flags & ~O_NONBLOCK);

    struct termios tty{};
    if (::tcgetattr(fd_, &tty) != 0) {
      Log("★ tcgetattr 失败: %s", std::strerror(errno));
      Close();
      return false;
    }

    speed_t speed = B115200;
    switch (baudrate) {
      case 9600:   speed = B9600;   break;
      case 19200:  speed = B19200;  break;
      case 38400:  speed = B38400;  break;
      case 57600:  speed = B57600;  break;
      case 115200: speed = B115200; break;
      default:     speed = B115200; break;
    }
    ::cfsetospeed(&tty, speed);
    ::cfsetispeed(&tty, speed);
    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;             // 8 位
    tty.c_cflag |= (CLOCAL | CREAD);                        // 启用接收，忽略调制解调器控制
    tty.c_cflag &= ~(PARENB | CSTOPB | CRTSCTS);           // 无校验，1 停止位，无流控
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);         // 原始模式
    tty.c_iflag &= ~(IXON | IXOFF | IXANY | IGNBRK | INLCR | ICRNL);
    tty.c_oflag &= ~OPOST;

    if (::tcsetattr(fd_, TCSANOW, &tty) != 0) {
      Log("★ tcsetattr 失败: %s", std::strerror(errno));
      Close();
      return false;
    }

    port_ = port;
    Log("★ 吸盘串口已打开: %s @ %d bps", port.c_str(), baudrate);
    return true;
  }

  // 关闭串口
  void Close()
  {
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
  }

  bool IsOpen() const { return fd_ >= 0; }

  // ========================================================================================
  // 时间参数（秒）
  // ========================================================================================
  void SetMoveSec(double s) { move_sec_ = s; }   // 舵机 0↔270 满程转动时间
  void SetHoldSec(double s) { hold_sec_ = s; }   // 下到位后保持时间（建真空 / 释放）

  // ========================================================================================
  // Home — 归位到存储位（舵机 270,270，泵 OFF）。Open 后调用一次
  // ========================================================================================
  void Home()
  {
    mode_ = Mode::Idle;
    phase_ = 0;
    active_ = false;
    SendCmd(270, 270, 0);
    Log("★ 归位到存储位 (270,270) 泵 OFF");
  }

  // ========================================================================================
  // StartPick — 启动取箱动作
  // ========================================================================================
  // direction: "left" / "right" 吸盘侧，决定哪个舵机下到动作位
  //
  void StartPick(const std::string & direction, double now_sec)
  {
    SetupDownAngles(direction);
    mode_ = Mode::Pick;
    phase_ = 0;
    phase_start_ = now_sec;
    active_ = true;

    // phase 0: 下到箱位 + 泵 ON
    SendCmd(down_left_, down_right_, 1);
    Log("★ 取箱[%s]: 下到箱位 (左%d 右%d) 泵 ON — 等 %.1fs",
        direction.c_str(), down_left_, down_right_, move_sec_);
  }

  // ========================================================================================
  // StartPlace — 启动放箱动作
  // ========================================================================================
  // direction: "left" / "right" 吸盘侧
  // 进入放箱时箱应已吸在存储位（泵 ON），由 phase 0 保持吸取下到放位
  //
  void StartPlace(const std::string & direction, double now_sec)
  {
    SetupDownAngles(direction);
    mode_ = Mode::Place;
    phase_ = 0;
    phase_start_ = now_sec;
    active_ = true;

    // phase 0: 下到放位 + 泵 ON（箱仍吸着）
    SendCmd(down_left_, down_right_, 1);
    Log("★ 放箱[%s]: 下到放位 (左%d 右%d) 泵 ON — 等 %.1fs",
        direction.c_str(), down_left_, down_right_, move_sec_);
  }

  // ========================================================================================
  // Update — 每帧推进。需在 timer/主循环里周期调用
  // ========================================================================================
  // 返回 true 表示这一帧动作刚完成（IsActive 会变 false）
  //
  bool Update(double now_sec)
  {
    if (!active_) return false;

    double elapsed = now_sec - phase_start_;
    if (elapsed < PhaseDuration()) return false;   // 本 phase 还没到时间

    // 本 phase 完成，推进
    Log("  phase%d 完成 (用时 %.2fs)", phase_, elapsed);
    phase_++;
    phase_start_ = now_sec;

    if (mode_ == Mode::Pick) {
      // phase: 0(下) → 1(建真空) → 2(抬) → done
      if (phase_ == 1) {
        SendCmd(down_left_, down_right_, 1);   // 保持泵 ON 建立真空
        Log("★ 取箱: 建立真空 泵 ON — 等 %.1fs", hold_sec_);
      } else if (phase_ == 2) {
        SendCmd(270, 270, 1);                   // 抬回存储，泵保持 ON（箱吸着）
        Log("★ 取箱: 抬回存储 (270,270) 泵 ON — 等 %.1fs", move_sec_);
      } else {
        active_ = false;
        Log("★ 取箱[%s] 完成（箱在存储位，泵保持 ON）", direction_.c_str());
        return true;
      }
    } else {  // Mode::Place
      // phase: 0(下) → 1(释放) → 2(抬) → done
      if (phase_ == 1) {
        SendCmd(down_left_, down_right_, 0);   // 泵 OFF 释放
        Log("★ 放箱: 泵 OFF 释放 — 等 %.1fs", hold_sec_);
      } else if (phase_ == 2) {
        SendCmd(270, 270, 0);                   // 抬回存储，泵 OFF
        Log("★ 放箱: 抬回存储 (270,270) 泵 OFF — 等 %.1fs", move_sec_);
      } else {
        active_ = false;
        Log("★ 放箱[%s] 完成（已释放，泵 OFF）", direction_.c_str());
        return true;
      }
    }
    return false;
  }

  // ========================================================================================
  // 状态查询
  // ========================================================================================
  bool IsActive() const { return active_; }
  bool IsPickMode() const { return mode_ == Mode::Pick; }
  bool IsPlaceMode() const { return mode_ == Mode::Place; }
  const std::string & Direction() const { return direction_; }

  // 当前是否正在吸着箱子（取箱后到放箱释放前都为 true）
  // 用于让上层判断运输途中是否带箱
  bool IsHolding() const
  {
    // 取箱完成(箱在存储位) 或 取/放途中未到释放阶段
    if (mode_ == Mode::Pick) return true;            // 取箱全程吸着
    if (mode_ == Mode::Place) return phase_ < 1;     // 放箱到 phase 1(释放) 前都吸着
    return false;
  }

protected:
  // ========================================================================================
  // SendCmd — 发送命令（逻辑角度 0~270 + 气泵 0/1）
  // ========================================================================================
  // virtual 便于单元测试子类拦截（覆盖此方法即可捕获发出的命令，无需真实串口）
  //
  virtual void SendCmd(int angle_left_logic, int angle_right_logic, int pump_on)
  {
    angle_left_logic = std::clamp(angle_left_logic, 0, 270);
    angle_right_logic = std::clamp(angle_right_logic, 0, 270);
    int angle_left_send = 270 - angle_left_logic;   // 左舵机镜像

    char buf[32];
    int n = std::snprintf(buf, sizeof(buf), "%d,%d,%d\n",
                          angle_left_send, angle_right_logic, pump_on);

    if (fd_ < 0) {
      Log("★ [串口未开] 发送(逻辑): 左%d 右%d 泵%d",
          angle_left_logic, angle_right_logic, pump_on);
      return;
    }

    ::ssize_t w = ::write(fd_, buf, static_cast<size_t>(n));
    if (w < 0) {
      Log("★ 吸盘串口写入失败: %s", std::strerror(errno));
      return;
    }
    ::tcdrain(fd_);   // 等待发送完成
  }

private:

  // 根据 direction 设置下到动作位的角度（一侧下，另一侧保持存储位）
  void SetupDownAngles(const std::string & direction)
  {
    direction_ = direction;
    if (direction == "left") {
      down_left_ = 0; down_right_ = 270;    // 左舵机下，右舵机保持存储
    } else {
      down_left_ = 270; down_right_ = 0;    // 右舵机下，左舵机保持存储
    }
  }

  // 当前 phase 的持续时长: phase 1 用 hold_sec_，其余用 move_sec_
  double PhaseDuration() const
  {
    return (phase_ == 1) ? hold_sec_ : move_sec_;
  }

  // 简单日志（printf；接 ROS 日志请替换此函数体为 RCLCPP_INFO）
  void Log(const char * fmt, ...) const
  {
    std::printf("[Sucker] ");
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
  enum class Mode { Idle, Pick, Place };

  int fd_{-1};
  std::string port_;

  // 时间参数
  double move_sec_{3.0};    // 舵机 0↔270 满程转动时间
  double hold_sec_{0.5};    // 下到位后保持（建真空 / 释放）时间

  // 状态机
  Mode mode_{Mode::Idle};
  int phase_{0};
  bool active_{false};
  std::string direction_;
  int down_left_{270};       // 下到动作位的左舵机逻辑角度
  int down_right_{270};
  double phase_start_{0.0};
};

}  // namespace dog_nav

#endif  // DOG_NAV_SUCKER_CONTROLLER_HPP_
