// ========================================================================================
// test_sucker.cpp — 吸盘 + 气泵控制器【硬件版】交互测试
// ========================================================================================
//
// 直接实例化真实的 SuckerController（不继承、不 mock）：
//   SendCmd 走基类 → ::write(fd, ...) + tcdrain → 真实写串口到 STM32。
// 时序用 std::chrono::steady_clock 墙钟（不是虚拟时钟），和 navigation_dog 实物一致。
//
// ★ 注意: sucker_controller.hpp 用了 <termios.h>（POSIX），只能 Linux 编译:
//   g++ -std=c++17 -I dog_nav/include dog_nav/test/test_sucker.cpp -o /tmp/test_sucker && /tmp/test_sucker
//
// 运行（参数全可省，默认与 navigation_dog 一致 /dev/ttyUSB0 @115200 move=3.0 hold=0.5）:
//   ./test_sucker [port] [baudrate] [move_sec] [hold_sec]
//   例: ./test_sucker /dev/ttyUSB0 115200 3.0 0.5
//
// 安全:
//   - 启动前打印参数 + 必须 y 确认（避免误跑驱动舵机/泵）
//   - 开头和退出各跑一次 Home()（归位到存储位 270,270 + 泵 OFF）
//   - Ctrl+C (SIGINT) → 置停止标志 → 主循环退出后自动 Home + Close
//   - 串口打开失败时提示 sudo chmod 666 / ls /dev/ttyUSB*（参照 test_serial.py）
//
// 菜单（输入首字符）:
//   h  归位 (270,270,0)
//   1  取箱 left    2  取箱 right
//   3  放箱 left    4  放箱 right
//   q  退出
//
#include "dog_nav/sucker_controller.hpp"

#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <chrono>
#include <thread>
#include <string>
#include <iostream>

using dog_nav::SuckerController;
using Clock = std::chrono::steady_clock;

// ========================================================================================
// 全局停止标志（SIGINT 置位）
// ========================================================================================
volatile sig_atomic_t g_stop = 0;

static void OnSigint(int) { g_stop = 1; }

// 从程序启动起算的墙钟秒数，喂给 StartPick/StartPlace/Update
static double NowSec(const Clock::time_point & t0)
{
  return std::chrono::duration<double>(Clock::now() - t0).count();
}

// ========================================================================================
// RunAction — 用 50Hz 墙钟把一个动作跑完（和 navigation_dog 的 timer 节拍一致）
// ========================================================================================
// 返回动作真实耗时（秒）。中途收到 SIGINT 会提前打断，主循环随后 Home。
//
static double RunAction(SuckerController & sc, const Clock::time_point & t0)
{
  double start = NowSec(t0);
  while (sc.IsActive() && !g_stop) {
    sc.Update(NowSec(t0));
    std::this_thread::sleep_for(std::chrono::milliseconds(20));   // 50Hz
  }
  return NowSec(t0) - start;
}

// ========================================================================================
// 主程序
// ========================================================================================
int main(int argc, char ** argv)
{
  // ---- 参数（全部可省，默认与 navigation_dog 一致）----
  std::string port = "/dev/ttyUSB0";
  int baudrate = 115200;
  double move_sec = 3.0;
  double hold_sec = 0.5;

  if (argc > 1) port = argv[1];
  if (argc > 2) baudrate = std::atoi(argv[2]);
  if (argc > 3) move_sec = std::atof(argv[3]);
  if (argc > 4) hold_sec = std::atof(argv[4]);

  // ---- 打印参数 ----
  std::printf("============================================================\n");
  std::printf("  ★ 吸盘 + 气泵控制器 — 硬件版交互测试\n");
  std::printf("============================================================\n");
  std::printf("  串口    : %s @ %d bps\n", port.c_str(), baudrate);
  std::printf("  move_sec: %.2fs  hold_sec: %.2fs\n", move_sec, hold_sec);
  std::printf("============================================================\n");

  // ---- 打开串口（真实硬件）----
  SuckerController sc;
  if (!sc.Open(port, baudrate)) {
    std::printf("\n★ 串口打开失败: %s\n", port.c_str());
    std::printf("  1) 检查设备是否存在: ls /dev/ttyUSB*\n");
    std::printf("  2) 给权限:           sudo chmod 666 %s\n", port.c_str());
    return 1;
  }

  sc.SetMoveSec(move_sec);
  sc.SetHoldSec(hold_sec);

  // ---- 注册 SIGINT ----
  std::signal(SIGINT, OnSigint);

  // ---- ⚠️ 安全确认 ----
  std::printf("\n⚠️  即将驱动真实舵机和气泵（STM32 @ %s）\n", port.c_str());
  std::printf("    确认吸盘机构无阻挡、泵气路正常后输入 y 继续，其它键退出: ");
  std::string line;
  if (!std::getline(std::cin, line) || line.empty() || (line[0] != 'y' && line[0] != 'Y')) {
    std::printf("已取消，退出。\n");
    sc.Close();
    return 0;
  }

  // ---- 进入安全初始态 ----
  std::printf("\n[初始化] ");
  sc.Home();   // 归位到存储位 (270,270) 泵 OFF

  // ---- 交互菜单 ----
  bool quit = false;
  while (!quit && !g_stop) {
    std::printf("\n----- 菜单 -----\n");
    std::printf("  h  归位 (270,270,0)\n");
    std::printf("  1  取箱 left    2  取箱 right\n");
    std::printf("  3  放箱 left    4  放箱 right\n");
    std::printf("  q  退出\n");
    std::printf("> ");

    if (!std::getline(std::cin, line)) {
      // stdin 关闭（如 Ctrl+D），按退出处理
      g_stop = 1;
      break;
    }
    if (line.empty()) continue;

    const Clock::time_point t0 = Clock::now();   // 每个动作重置零点
    char cmd = line[0];

    switch (cmd) {
      case 'h':
      case 'H':
        sc.Home();
        std::printf("  -> 已归位 (270,270,0)\n");
        break;

      case '1':
        std::printf("\n[取箱 left] 启动...\n");
        sc.StartPick("left", NowSec(t0));
        {
          double dt = RunAction(sc, t0);
          std::printf("  -> 取箱 left %s，真实耗时 %.2fs\n",
                      g_stop ? "被中断" : "完成", dt);
        }
        break;

      case '2':
        std::printf("\n[取箱 right] 启动...\n");
        sc.StartPick("right", NowSec(t0));
        {
          double dt = RunAction(sc, t0);
          std::printf("  -> 取箱 right %s，真实耗时 %.2fs\n",
                      g_stop ? "被中断" : "完成", dt);
        }
        break;

      case '3':
        std::printf("\n[放箱 left] 启动...\n");
        sc.StartPlace("left", NowSec(t0));
        {
          double dt = RunAction(sc, t0);
          std::printf("  -> 放箱 left %s，真实耗时 %.2fs\n",
                      g_stop ? "被中断" : "完成", dt);
        }
        break;

      case '4':
        std::printf("\n[放箱 right] 启动...\n");
        sc.StartPlace("right", NowSec(t0));
        {
          double dt = RunAction(sc, t0);
          std::printf("  -> 放箱 right %s，真实耗时 %.2fs\n",
                      g_stop ? "被中断" : "完成", dt);
        }
        break;

      case 'q':
      case 'Q':
        quit = true;
        break;

      default:
        std::printf("  未知命令 '%c'\n", cmd);
        break;
    }
  }

  // ---- 退出路径：归位 + 关泵 + 关串口 ----
  if (g_stop) {
    std::printf("\n[SIGINT] 收到中断信号，安全退出...\n");
  }
  std::printf("\n[退出] ");
  sc.Home();   // 归位 + 泵 OFF
  sc.Close();
  std::printf("  -> 串口已关闭，再见。\n");

  return 0;
}
