// ========================================================================================
// sucker_dual.hpp — 双吸控制器（一次吸两箱，左右吸盘同步动作）
// ========================================================================================
//
// 与 sucker_controller.hpp 的区别:
//   - SuckerController: 单侧动作（左 或 右），用于旧机构左右分吸
//   - SuckerDual:       双侧同步（左右同时下/吸/抬），用于新机构一次吸两箱
//
// 串口协议（与 STM32 一致，和 SuckerController 相同）:
//   发送: "{angle_left_send},{angle_right_send},{pump}\n"
//   - 左舵机镜像: angle_left_send = 270 - angle_left_logic
//   - 0° = 吸取/放置位置（下到位），270° = 存储位置（抬起）
//   - pump: 0 = 关，1 = 开
//
// 角度模型:
//   逻辑 0   = 动作位（下到位，吸/放）
//   逻辑 270 = 存储位（抬起）
//   左右同时: 双吸时两侧都下到 0，抬起时两侧都回 270
//
// 状态机（取/放都是 3 相位）:
//   phase 0: 下到位   发 (0, 0, pump)，等 move_sec_
//   phase 1: 保持     等 hold_sec_（建真空 / 释放）
//   phase 2: 抬回     发 (270, 270, pump)，等 move_sec_
//   取箱: pump 全程 1（建真空后保持）
//   放箱: phase 0 泵 1（带着箱下放），phase 1/2 泵 0（释放后抬回）
//
// 用法:
//   SuckerDual sucker;
//   sucker.Open("/dev/ttyUSB0", 115200);
//   sucker.SetMoveSec(3.0);
//   sucker.SetHoldSec(0.5);
//   sucker.Home();                       // 归位
//   sucker.StartPick(now_sec);           // 开始取（双吸）
//   sucker.StartPlace(now_sec);          // 开始放（双放）
//   // 每帧:
//   sucker.Update(now_sec);
//   if (!sucker.IsActive()) { /* 完成 */ }
//

#ifndef DOG_NAV_SUCKER_DUAL_HPP_
#define DOG_NAV_SUCKER_DUAL_HPP_

#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <cerrno>
#include <cmath>
#include <string>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>

namespace dog_nav
{

class SuckerDual
{
public:
  SuckerDual() = default;
  ~SuckerDual() { Close(); }

  SuckerDual(const SuckerDual &) = delete;
  SuckerDual & operator=(const SuckerDual &) = delete;

  // ========================================================================================
  // Open — 打开串口（与 SuckerController 一致）
  // ========================================================================================
  bool Open(const std::string & port, int baudrate = 115200)
  {
    fd_ = ::open(port.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd_ < 0) {
      Log("★ [SuckerDual] 无法打开串口 %s: %s", port.c_str(), std::strerror(errno));
      return false;
    }

    int flags = ::fcntl(fd_, F_GETFL, 0);
    ::fcntl(fd_, F_SETFL, flags & ~O_NONBLOCK);

    struct termios tty{};
    if (::tcgetattr(fd_, &tty) != 0) {
      Log("★ [SuckerDual] tcgetattr 失败: %s", std::strerror(errno));
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
    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
    tty.c_cflag |= (CLOCAL | CREAD);
    tty.c_cflag &= ~(PARENB | CSTOPB | CRTSCTS);
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    tty.c_iflag &= ~(IXON | IXOFF | IXANY | IGNBRK | INLCR | ICRNL);
    tty.c_oflag &= ~OPOST;

    if (::tcsetattr(fd_, TCSANOW, &tty) != 0) {
      Log("★ [SuckerDual] tcsetattr 失败: %s", std::strerror(errno));
      Close();
      return false;
    }

    port_ = port;
    Log("★ [SuckerDual] 串口已打开: %s @ %d bps（双吸模式）", port.c_str(), baudrate);
    return true;
  }

  void Close()
  {
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
  }

  bool IsOpen() const { return fd_ >= 0; }

  // ========================================================================================
  // 时间参数
  // ========================================================================================
  void SetMoveSec(double s) { move_sec_ = s; }   // 舵机 0↔270 满程转动时间
  void SetHoldSec(double s) { hold_sec_ = s; }   // 下到位后保持时间（建真空/释放）

  // ========================================================================================
  // Home — 归位到存储位（两侧 270,270 泵 OFF）。Open 后调用一次
  // ========================================================================================
  void Home()
  {
    SendCmd(270, 270, 0);
    mode_ = Mode::Idle;
    phase_ = 0;
    active_ = false;
    holding_ = false;
    Log("★ [SuckerDual] 归位到存储位 (270,270) 泵 OFF");
  }

  // ========================================================================================
  // StartPick — 开始取箱（双吸，左右同时下→吸→抬）
  // ========================================================================================
  // 全程泵 ON:
  //   phase 0: 发 (0, 0, 1) 下到位
  //   phase 1: 保持（建真空）
  //   phase 2: 发 (270, 270, 1) 抬回（泵仍 ON，箱吸着）
  //
  void StartPick(double now_sec)
  {
    mode_ = Mode::Pick;
    direction_.clear();         // 取货是双吸，无方向
    phase_ = 0;
    phase_start_ = now_sec;
    active_ = true;
    holding_ = false;
    SendCmd(0, 0, 1);           // 两侧同时下到位 + 泵 ON
    Log("★ [SuckerDual] 取箱(双吸): 下到位 (0,0) 泵ON — 等 %.1fs", move_sec_);
  }

  // ========================================================================================
  // StartPlace — 开始放箱（双放，左右同时下→释放→抬）
  // ========================================================================================
  // phase 0: 发 (0, 0, 1) 下到位（带着箱，泵仍 ON）
  // phase 1: 泵 OFF 释放（保持下到位）
  // phase 2: 发 (270, 270, 0) 抬回（泵 OFF）
  //
  void StartPlace(double now_sec)
  {
    mode_ = Mode::Place;
    direction_ = "";        // 空表示双放
    phase_ = 0;
    phase_start_ = now_sec;
    active_ = true;
    holding_ = false;
    SendCmd(0, 0, 1);           // 两侧同时下到位 + 泵 ON（箱还吸着）
    Log("★ [SuckerDual] 放箱(双放): 下到位 (0,0) 泵ON — 等 %.1fs", move_sec_);
  }

  // ========================================================================================
  // StartPlace(direction) — 单侧放箱（双吸取了两箱后，分开放到不同 zone）
  // ========================================================================================
  // 只动指定侧，另一侧保持存储位（仍吸着另一个箱）:
  //   phase 0: 发下到位（指定侧 0，另侧 270），泵 ON
  //   phase 1: 泵 OFF 释放
  //   phase 2: 抬回（指定侧 270，另侧 270），泵 OFF
  //   ★ 注意: 另一侧的泵也关了！如果另侧箱靠同一个泵吸着，会同时掉。
  //          这个实现假设左右两路泵独立。如果共用一个泵，放一个另一个也掉，需另设计。
  //
  void StartPlace(const std::string & direction, double now_sec)
  {
    mode_ = Mode::Place;
    direction_ = direction;
    phase_ = 0;
    phase_start_ = now_sec;
    active_ = true;
    holding_ = false;
    int left = (direction == "left") ? 0 : 270;
    int right = (direction == "left") ? 270 : 0;
    SendCmd(left, right, 1);
    Log("★ [SuckerDual] 放箱(%s侧): 下到位 (左%d,右%d) 泵ON — 等 %.1fs",
        direction.c_str(), left, right, move_sec_);
  }

  // ========================================================================================
  // Update — 每帧推进状态机（返回 true 表示还在活动中）
  // ========================================================================================
  bool Update(double now_sec)
  {
    if (!active_) return false;

    double elapsed = now_sec - phase_start_;
    double dur = (phase_ == 1) ? hold_sec_ : move_sec_;

    if (elapsed < dur) return true;

    // phase 切换
    phase_start_ = now_sec;

    if (mode_ == Mode::Pick) {
      // 取箱: phase 0(下到位) → 1(保持) → 2(抬回，泵仍ON) → 完成
      if (phase_ == 0) {
        phase_ = 1;
        holding_ = true;
        Log("★ [SuckerDual] 取箱: 建真空保持 — 等 %.1fs", hold_sec_);
      } else if (phase_ == 1) {
        phase_ = 2;
        holding_ = false;
        SendCmd(270, 270, 1);   // 抬回存储位，泵仍 ON（箱吸着）
        Log("★ [SuckerDual] 取箱: 抬回 (270,270) 泵ON — 等 %.1fs", move_sec_);
      } else {
        // phase 2 完成
        active_ = false;
        mode_ = Mode::Idle;
        Log("★ [SuckerDual] 取箱完成（双吸，箱在存储位）");
      }
    } else if (mode_ == Mode::Place) {
      // 放箱: phase 0(下到位,泵ON) → 1(泵OFF释放) → 2(抬回,泵OFF) → 完成
      if (phase_ == 0) {
        phase_ = 1;
        holding_ = true;
        // 单侧放: 关泵但保持下到位姿态；双放: 同样关泵
        if (direction_.empty()) {
          SendCmd(0, 0, 0);
        } else {
          int left = (direction_ == "left") ? 0 : 270;
          int right = (direction_ == "left") ? 270 : 0;
          SendCmd(left, right, 0);
        }
        Log("★ [SuckerDual] 放箱: 泵OFF 释放 — 等 %.1fs", hold_sec_);
      } else if (phase_ == 1) {
        phase_ = 2;
        holding_ = false;
        SendCmd(270, 270, 0);   // 抬回存储位，泵 OFF（单侧放完，另侧箱仍在存储位）
        Log("★ [SuckerDual] 放箱: 抬回 (270,270) 泵OFF — 等 %.1fs", move_sec_);
      } else {
        active_ = false;
        mode_ = Mode::Idle;
        Log("★ [SuckerDual] 放箱完成");
      }
    }
    return active_;
  }

  // ========================================================================================
  // 状态查询
  // ========================================================================================
  bool IsActive() const { return active_; }
  bool IsHolding() const { return holding_; }     // 在 phase 1（保持期）
  bool IsPickMode() const { return mode_ == Mode::Pick; }
  bool IsPlaceMode() const { return mode_ == Mode::Place; }
  int Phase() const { return phase_; }

protected:
  // ========================================================================================
  // SendCmd — 发送命令（逻辑角度 + 泵）。virtual 便于单元测试拦截
  // ========================================================================================
  virtual void SendCmd(int angle_left_logic, int angle_right_logic, int pump_on)
  {
    angle_left_logic = std::clamp(angle_left_logic, 0, 270);
    angle_right_logic = std::clamp(angle_right_logic, 0, 270);
    int angle_left_send = 270 - angle_left_logic;   // 左舵机镜像

    char buf[32];
    int n = std::snprintf(buf, sizeof(buf), "%d,%d,%d\n",
                          angle_left_send, angle_right_logic, pump_on);

    if (fd_ < 0) {
      Log("★ [SuckerDual][串口未开] 发送(逻辑): 左%d 右%d 泵%d",
          angle_left_logic, angle_right_logic, pump_on);
      return;
    }

    ::ssize_t w = ::write(fd_, buf, static_cast<size_t>(n));
    if (w < 0) {
      Log("★ [SuckerDual] 串口写入失败: %s", std::strerror(errno));
      return;
    }
    ::tcdrain(fd_);
  }

private:
  enum class Mode { Idle, Pick, Place };

  // 日志: 默认空实现（避免 printf 干扰 ROS 日志）。需要调试时定义 SUCKER_DUAL_VERBOSE
  static void Log(const char * fmt, ...)
  {
#ifdef SUCKER_DUAL_VERBOSE
    std::printf("[SuckerDual] ");
    va_list ap; va_start(ap, fmt); std::vprintf(fmt, ap); va_end(ap);
    std::printf("\n");
#else
    (void)fmt;
#endif
  }

  int fd_{-1};
  std::string port_;

  Mode mode_{Mode::Idle};
  std::string direction_;        // 单侧放时用（"left"/"right"，空=双放/双吸）
  int phase_{0};                // 0=下到位, 1=保持, 2=抬回
  bool active_{false};
  bool holding_{false};
  double phase_start_{0.0};

  double move_sec_{3.0};        // 舵机 0↔270 满程转动时间
  double hold_sec_{0.5};        // 下到位保持时间
};

}  // namespace dog_nav

#endif  // DOG_NAV_SUCKER_DUAL_HPP_
