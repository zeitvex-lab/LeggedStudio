// ========================================================================================
// record_points.cpp — 场地打点工具
// ========================================================================================
//
// 功能：
//   订阅 /lio/odom 实时显示当前位姿，按 s 记录当前目标点位坐标，
//   完成后输出 task_race_point.yaml 的坐标部分，直接复制粘贴即可。
//
// 使用方法：
//   1. 启动 Super-LIO（雷达里程计）
//   2. ros2 run dog_nav record_points
//   3. 把狗抬到某个点位
//   4. 按 n/p 切换到对应点位名称，按 s 保存
//   5. 保存后自动跳到下一个未记录的点位
//   6. 全部点完后按 w 输出 YAML
//   7. 按 q 退出
//
// 快捷键：
//   s     — 保存当前位置为当前目标点位
//   数字  — 输入编号直接跳转（多位，回车确认，backspace删除，esc取消）
//   n     — 切换到下一个点位（浏览）
//   p     — 切换到上一个点位（浏览）
//   u     — 撤销上一个点位（回退一步）
//   l     — 列出所有点位状态
//   w     — 输出 YAML 到终端
//   r     — 重新开始（清空所有点位）
//   q     — 退出

// # 场地布局（15 节点，与 field_path_planner.hpp / navigation_dog.cpp 对齐）:
// #
// #   【点13】【01】【点10】【02】【点11】【03】【点12】【04】【点14】    归位区
// #
// #   =======================================================  减速带
// #   【05】 【点6】 【点7】 【06】   【07】 【点8】 【点9】 【08】  第二排
// #
// #   【09】 【点2】 【点3】 【10】   【11】 【点4】 【点5】 【12】  第一排
// #
// #                       【点1】                                  起点前
// #
// #                       【0】                                    起点
// #
// # 取货映射（每点一个箱，一轮跑两个点凑齐左右吸盘）:
// #   点2→左吸09, 点3→右吸10, 点4→左吸11, 点5→右吸12
// #   点6→左吸05, 点7→右吸06, 点8→左吸07, 点9→右吸08
// #
// # 放货站位（归位区旁）:
// #   点10→放zone1/2, 点11→放zone2/3, 点12→放zone3/4
// #   点13→右吸放zone1, 点14→左吸放zone4
// #   （具体由吸盘侧决定，见 navigation_dog.cpp 的 place_zone_map_）


#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <map>
#include <thread>
#include <atomic>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>
#include <iostream>
#include <iomanip>
#include <fstream>
#include <sstream>

// ========================================================================================
// 点位定义（和 task_race_point.yaml 一一对应）
// ========================================================================================

struct PointEntry
{
  std::string yaml_key;     // YAML 中的 key
  std::string section;      // 所属段落
  std::string description;  // 描述
  double x, y, theta;       // 记录的坐标
  bool recorded;
};

// 所有点位（13 节点布局，与 navigation_dog.cpp / field_path_planner.hpp 对齐）
static std::vector<PointEntry> kPointList = {
  // 起点
  {"start_pose",  "start",  "起点 (点0)",                0, 0, 0, false},

  // 取货站位点（每轮跑两个点凑齐左右吸盘）
  {"point_1",     "pickup", "起点前方 (点1, 中转)",       0, 0, 0, false},
  {"point_2",     "pickup", "第一排左1 (点2, 左吸09)",    0, 0, 0, false},
  {"point_3",     "pickup", "第一排左2 (点3, 右吸10)",    0, 0, 0, false},
  {"point_4",     "pickup", "第一排右1 (点4, 左吸11)",    0, 0, 0, false},
  {"point_5",     "pickup", "第一排右2 (点5, 右吸12)",    0, 0, 0, false},
  {"point_6",     "pickup", "第二排左1 (点6, 左吸05)",    0, 0, 0, false},
  {"point_7",     "pickup", "第二排左2 (点7, 右吸06)",    0, 0, 0, false},
  {"point_8",     "pickup", "第二排右1 (点8, 左吸07)",    0, 0, 0, false},
  {"point_9",     "pickup", "第二排右2 (点9, 右吸08)",    0, 0, 0, false},

  // 放货站位点（归位区旁，对应 zone1~4）
  {"point_10",    "place",  "归位区01/02旁 (点10)",          0, 0, 0, false},
  {"point_11",    "place",  "归位区02/03旁 (点11)",          0, 0, 0, false},
  {"point_12",    "place",  "归位区03/04旁 (点12)",          0, 0, 0, false},
  {"point_13",    "place",  "归位区01左侧 (点13, 右吸zone1)", 0, 0, 0, false},
  {"point_14",    "place",  "归位区04右侧 (点14, 左吸zone4)", 0, 0, 0, false},

  // 归位区（不是路径节点，用于计算转身角度）
  {"zone_1",      "zone",   "归位区01",                   0, 0, 0, false},
  {"zone_2",      "zone",   "归位区02",                   0, 0, 0, false},
  {"zone_3",      "zone",   "归位区03",                   0, 0, 0, false},
  {"zone_4",      "zone",   "归位区04",                   0, 0, 0, false},

  // 物资箱位置（不是路径节点）
  {"box_05",      "box",    "第二排左1 (箱05)",           0, 0, 0, false},
  {"box_06",      "box",    "第二排左2 (箱06)",           0, 0, 0, false},
  {"box_07",      "box",    "第二排右1 (箱07)",           0, 0, 0, false},
  {"box_08",      "box",    "第二排右2 (箱08)",           0, 0, 0, false},
  {"box_09",      "box",    "第一排左1 (箱09)",           0, 0, 0, false},
  {"box_10",      "box",    "第一排左2 (箱10)",           0, 0, 0, false},
  {"box_11",      "box",    "第一排右1 (箱11)",           0, 0, 0, false},
  {"box_12",      "box",    "第一排右2 (箱12)",           0, 0, 0, false},
};

class RecordPointsNode : public rclcpp::Node
{
public:
  RecordPointsNode()
  : Node("record_points_node"), target_idx_(0)
  {
    this->declare_parameter("odom_topic", std::string("/lio/odom"));
    this->declare_parameter("output_path", std::string(""));

    odom_topic_ = this->get_parameter("odom_topic").as_string();
    output_path_ = this->get_parameter("output_path").as_string();

    // 订阅里程计
    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::QoS(10).best_effort(),
      [this](const nav_msgs::msg::Odometry::SharedPtr msg) {
        cur_x_ = msg->pose.pose.position.x;
        cur_y_ = msg->pose.pose.position.y;
        tf2::Quaternion q(
          msg->pose.pose.orientation.x,
          msg->pose.pose.orientation.y,
          msg->pose.pose.orientation.z,
          msg->pose.pose.orientation.w);
        tf2::Matrix3x3 m(q);
        double roll, pitch, yaw;
        m.getRPY(roll, pitch, yaw);
        cur_yaw_ = yaw;
        odom_received_ = true;
      });

    // 初始目标：第一个未记录的点位
    JumpToNextUnrecorded();

    // 打印帮助
    printf("\n");
    printf("╔══════════════════════════════════════════════════╗\n");
    printf("║  ★ 场地打点工具                                  ║\n");
    printf("╠══════════════════════════════════════════════════╣\n");
    printf("║  里程计: %-40s║\n", odom_topic_.c_str());
    printf("║  总点数: %-2zu 个                                  ║\n", kPointList.size());
    printf("╠══════════════════════════════════════════════════╣\n");
    printf("║  s = 保存当前位置为当前目标点位                    ║\n");
    printf("║  数字 = 输入编号直接跳转(回车确认)                  ║\n");
    printf("║  n = 下一个点位    p = 上一个点位                  ║\n");
    printf("║  u = 撤销上一个    l = 列出所有点位                ║\n");
    printf("║  w = 输出 YAML     r = 清空重来                    ║\n");
    printf("║  q = 退出                                         ║\n");
    printf("╚══════════════════════════════════════════════════╝\n");
    printf("\n");

    // 启动键盘线程
    keyboard_running_ = true;
    keyboard_thread_ = std::thread(&RecordPointsNode::KeyboardLoop, this);
  }

  ~RecordPointsNode()
  {
    keyboard_running_ = false;
    if (keyboard_thread_.joinable()) {
      keyboard_thread_.join();
    }
  }

private:

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
      tv.tv_usec = 100000;  // 100ms
      const int ret = select(STDIN_FILENO + 1, &set, nullptr, nullptr, &tv);
      if (ret <= 0) {
        PrintStatusLine();
        continue;
      }

      char c = 0;
      if (read(STDIN_FILENO, &c, 1) != 1) continue;

      // ===== 数字输入模式：累积数字、backspace 删除、回车跳转、esc 取消 =====
      if (num_input_mode_) {
        if (c >= '0' && c <= '9') {
          // 累积数字（限制最多 2 位，点位 ≤ 24）
          if (num_input_.size() < 2) {
            num_input_ += c;
            PrintNumInputLine();
          }
          continue;
        }
        if (c == 127 || c == 8) {  // backspace (DEL / BS)
          if (!num_input_.empty()) {
            num_input_.pop_back();
            PrintNumInputLine();
          }
          continue;
        }
        if (c == '\n' || c == '\r') {  // 回车 → 跳转
          ConfirmNumInput();
          continue;
        }
        if (c == 27) {  // esc → 取消
          CancelNumInput();
          continue;
        }
        // 输入模式下其他键忽略（避免误触 s/n/p 等）
        continue;
      }

      // ===== 普通模式 =====
      if (c >= '0' && c <= '9') {
        // 数字键 → 进入编号输入模式
        num_input_mode_ = true;
        num_input_ = std::string(1, c);
        PrintNumInputLine();
        continue;
      }

      // 除 q 外的任何按键都取消"退出确认"状态
      if (quit_confirm_ && c != 'q') {
        quit_confirm_ = false;
      }

      switch (c) {
        case 's':
          SaveCurrentPoint();
          break;
        case 'n':
          // 下一个点位
          if (target_idx_ + 1 < static_cast<int>(kPointList.size())) {
            target_idx_++;
          } else {
            target_idx_ = 0;
          }
          PrintTargetInfo();
          break;
        case 'p':
          // 上一个点位
          if (target_idx_ > 0) {
            target_idx_--;
          } else {
            target_idx_ = static_cast<int>(kPointList.size()) - 1;
          }
          PrintTargetInfo();
          break;
        case 'u':
          UndoLast();
          break;
        case 'l':
          ListAllPoints();
          break;
        case 'w':
          OutputYAML();
          break;
        case 'r':
          ResetAll();
          break;
        case 'q':
          if (dirty_ && !quit_confirm_) {
            // 有未保存改动，提示确认
            printf("\n");
            printf("  ⚠️ 有未保存的改动！先按 w 输出 YAML 保存。\n");
            printf("  ⚠️ 确定要直接退出（丢弃改动）？再按一次 q 确认，按其他键取消。\n\n");
            quit_confirm_ = true;
          } else {
            printf("\n  ★ 退出打点工具\n");
            keyboard_running_ = false;
            rclcpp::shutdown();
          }
          break;
      }
    }

    tcsetattr(STDIN_FILENO, TCSANOW, &old_tio);
  }

  // 跳转到第一个未记录的点位
  void JumpToNextUnrecorded()
  {
    for (size_t i = 0; i < kPointList.size(); ++i) {
      if (!kPointList[i].recorded) {
        target_idx_ = static_cast<int>(i);
        return;
      }
    }
    // 全部已记录，停在最后一个
    target_idx_ = static_cast<int>(kPointList.size()) - 1;
  }

  // 确认编号输入 → 跳转到对应点位（输入是 1-based 编号）
  void ConfirmNumInput()
  {
    if (num_input_.empty()) {
      CancelNumInput();
      return;
    }
    int num = std::atoi(num_input_.c_str());
    num_input_.clear();
    num_input_mode_ = false;

    // 编号 1..N 对应索引 0..N-1
    if (num < 1 || num > static_cast<int>(kPointList.size())) {
      printf("\n  ⚠️ 编号 %d 超范围（1~%zu），已取消\n\n", num, kPointList.size());
      return;
    }
    target_idx_ = num - 1;
    printf("\n");
    PrintTargetInfo();
  }

  // 取消编号输入
  void CancelNumInput()
  {
    num_input_.clear();
    num_input_mode_ = false;
    printf("\n  ✘ 已取消编号输入\n\n");
  }

  // 显示当前输入中的编号
  void PrintNumInputLine() const
  {
    printf("  跳转到编号: [%s] (1~%zu, 回车确认 / backspace删除 / esc取消)  \r",
           num_input_.c_str(), kPointList.size());
    fflush(stdout);
  }

  // 打印当前目标点位信息
  void PrintTargetInfo() const
  {
    const auto & pt = kPointList[target_idx_];
    const char * status = pt.recorded ? "✅ 已记录" : "⬜ 未记录";
    printf("\n  → 目标: [%2d/%2zu] %-10s %-30s %s\n",
           target_idx_ + 1, kPointList.size(),
           pt.yaml_key.c_str(), pt.description.c_str(), status);
    if (pt.recorded) {
      printf("    已有坐标: (%.4f, %.4f, %.1f°)  再按 s 会覆盖\n",
             pt.x, pt.y, pt.theta);
    }
    printf("\n");
  }

  // 保存当前位置为当前目标点位
  void SaveCurrentPoint()
  {
    if (!odom_received_) {
      printf("  ⚠️ 还没收到里程计数据，无法保存\n");
      return;
    }

    auto & pt = kPointList[target_idx_];
    pt.x = cur_x_;
    pt.y = cur_y_;
    pt.theta = cur_yaw_ * 180.0 / M_PI;  // 转为度
    pt.recorded = true;

    printf("\n");
    printf("  ✅ [%2d/%2zu] %-10s %-30s → (%.4f, %.4f, %.1f°)\n",
           target_idx_ + 1, kPointList.size(),
           pt.yaml_key.c_str(), pt.description.c_str(),
           pt.x, pt.y, pt.theta);

    // 标记有未保存改动（按 w 写出后清零）
    dirty_ = true;

    // 检查是否全部完成（停在原地，不自动跳转，由用户用编号控制去哪）
    int unrecorded = 0;
    for (const auto & p : kPointList) {
      if (!p.recorded) unrecorded++;
    }

    if (unrecorded == 0) {
      printf("  🎉 全部 %zu 个点位记录完毕！按 w 输出 YAML\n\n", kPointList.size());
    } else {
      printf("  （剩余 %d 个未记录，停在本点，输入编号跳转下一个）\n\n", unrecorded);
    }
  }

  // 撤销最后一个记录的点位
  void UndoLast()
  {
    // 找最后一个已记录的点
    int last = -1;
    for (int i = static_cast<int>(kPointList.size()) - 1; i >= 0; --i) {
      if (kPointList[i].recorded) {
        last = i;
        break;
      }
    }

    if (last < 0) {
      printf("  ⚠️ 没有已记录的点位可以撤销\n");
      return;
    }

    auto & pt = kPointList[last];
    printf("  ↩️  撤销 [%2d] %s (%.4f, %.4f, %.1f°)\n",
           last + 1, pt.yaml_key.c_str(), pt.x, pt.y, pt.theta);
    pt.recorded = false;
    pt.x = 0; pt.y = 0; pt.theta = 0;
    target_idx_ = last;
    dirty_ = true;
  }

  // 列出所有点位状态
  void ListAllPoints() const
  {
    printf("\n");
    printf("  ╔══════════════════════════════════════════════════╗\n");
    printf("  ║  所有点位状态                                    ║\n");
    printf("  ╠══════════════════════════════════════════════════╣\n");

    int recorded = 0;
    for (size_t i = 0; i < kPointList.size(); ++i) {
      const auto & pt = kPointList[i];
      const char * marker = (static_cast<int>(i) == target_idx_) ? " ◀ 当前" : "";
      if (pt.recorded) {
        recorded++;
        printf("  ✅ [%2zu] %-10s (%.3f, %.3f, %.1f°)%s\n",
               i + 1, pt.yaml_key.c_str(), pt.x, pt.y, pt.theta, marker);
      } else {
        printf("  ⬜ [%2zu] %-10s %s%s\n",
               i + 1, pt.yaml_key.c_str(), pt.description.c_str(), marker);
      }
    }
    printf("  ╠══════════════════════════════════════════════════╣\n");
    printf("  ║  已记录: %d / %zu                                 ║\n",
           recorded, kPointList.size());
    printf("  ╚══════════════════════════════════════════════════╝\n");
    printf("\n");
  }

  // 清空所有
  void ResetAll()
  {
    for (auto & pt : kPointList) {
      pt.recorded = false;
      pt.x = 0; pt.y = 0; pt.theta = 0;
    }
    target_idx_ = 0;
    dirty_ = true;
    printf("  🔄 已清空所有点位，重新开始\n");
  }

  // 输出 YAML 格式的坐标
  void OutputYAML()
  {
    printf("\n");
    printf("╔══════════════════════════════════════════════════╗\n");
    printf("║  ★ YAML 坐标输出                                 ║\n");
    printf("╚══════════════════════════════════════════════════╝\n");
    printf("\n");

    int recorded = 0;
    for (const auto & pt : kPointList) {
      if (pt.recorded) recorded++;
    }
    printf("# 已记录 %d / %zu 个点位\n", recorded, kPointList.size());
    printf("\n");

    // start_pose
    if (kPointList[0].recorded) {
      const auto & pt = kPointList[0];
      printf("start_pose: [%.4f, %.4f, %.1f]\n", pt.x, pt.y, pt.theta);
    } else {
      printf("start_pose: [0.0, 0.0, 0.0]    # 未记录\n");
    }
    printf("\n");

    // pickup_positions (point_1~9, 索引 1~9)
    printf("pickup_positions:\n");
    for (int i = 1; i <= 9; ++i) {
      const auto & pt = kPointList[i];
      if (pt.recorded) {
        printf("  %-10s [%.4f, %.4f, %.1f]    # %s\n",
               (pt.yaml_key + ":").c_str(), pt.x, pt.y, pt.theta, pt.description.c_str());
      } else {
        printf("  %-10s [0.0, 0.0, 0.0]          # 未记录: %s\n",
               (pt.yaml_key + ":").c_str(), pt.description.c_str());
      }
    }
    printf("\n");

    // place_positions (point_10~14, 索引 10~14)
    printf("place_positions:\n");
    for (int i = 10; i <= 14; ++i) {
      const auto & pt = kPointList[i];
      if (pt.recorded) {
        printf("  %-10s [%.4f, %.4f, %.1f]    # %s\n",
               (pt.yaml_key + ":").c_str(), pt.x, pt.y, pt.theta, pt.description.c_str());
      } else {
        printf("  %-10s [0.0, 0.0, 0.0]          # 未记录: %s\n",
               (pt.yaml_key + ":").c_str(), pt.description.c_str());
      }
    }
    printf("\n");

    // return_zones (zone_1~4, 索引 15~18)
    printf("return_zones:\n");
    for (int i = 15; i <= 18; ++i) {
      const auto & pt = kPointList[i];
      if (pt.recorded) {
        printf("  %-10s [%.4f, %.4f, %.1f]\n",
               (pt.yaml_key + ":").c_str(), pt.x, pt.y, pt.theta);
      } else {
        printf("  %-10s [0.0, 0.0, 0.0]\n", (pt.yaml_key + ":").c_str());
      }
    }
    printf("\n");

    // box_positions (box_05~12, 索引 19~26)
    printf("box_positions:\n");
    for (int i = 19; i <= 26; ++i) {
      const auto & pt = kPointList[i];
      if (pt.recorded) {
        printf("  %-10s [%.4f, %.4f, %.1f]    # %s\n",
               (pt.yaml_key + ":").c_str(), pt.x, pt.y, pt.theta, pt.description.c_str());
      } else {
        printf("  %-10s [0.0, 0.0, 0.0]          # 未记录: %s\n",
               (pt.yaml_key + ":").c_str(), pt.description.c_str());
      }
    }
    printf("\n");

    // 保存到文件
    if (!output_path_.empty()) {
      SaveToFile();
    } else {
      printf("  💡 复制上面的内容替换 task_race_point.yaml 中的坐标部分即可\n");
      printf("  💡 或者运行时加参数 -p output_path:=/path/to/task_race_point.yaml 自动保存\n");
    }
    dirty_ = false;  // 已输出，清未保存标记
  }

  void SaveToFile()
  {
    std::ofstream ofs(output_path_);
    if (!ofs.is_open()) {
      printf("  ❌ 无法打开文件: %s\n", output_path_.c_str());
      return;
    }

    ofs << std::fixed << std::setprecision(4);

    ofs << "# task_race_point.yaml — 场地坐标（由 record_points 自动生成）\n";
    ofs << "# 坐标单位: 米, 角度单位: 度\n\n";

    // start_pose
    {
      const auto & pt = kPointList[0];
      ofs << "start_pose: [" << pt.x << ", " << pt.y << ", " << pt.theta << "]\n\n";
    }

    // pickup_positions (point_1~9, 索引 1~9)
    ofs << "pickup_positions:\n";
    for (int i = 1; i <= 9; ++i) {
      const auto & pt = kPointList[i];
      ofs << "  " << pt.yaml_key << ": [" << pt.x << ", " << pt.y << ", " << pt.theta
          << "]    # " << pt.description << "\n";
    }
    ofs << "\n";

    // place_positions (point_10~14, 索引 10~14)
    ofs << "place_positions:\n";
    for (int i = 10; i <= 14; ++i) {
      const auto & pt = kPointList[i];
      ofs << "  " << pt.yaml_key << ": [" << pt.x << ", " << pt.y << ", " << pt.theta
          << "]    # " << pt.description << "\n";
    }
    ofs << "\n";

    // return_zones (zone_1~4, 索引 15~18)
    ofs << "return_zones:\n";
    for (int i = 15; i <= 18; ++i) {
      const auto & pt = kPointList[i];
      ofs << "  " << pt.yaml_key << ": [" << pt.x << ", " << pt.y << ", " << pt.theta << "]\n";
    }
    ofs << "\n";

    // box_positions (box_05~12, 索引 19~26)
    ofs << "box_positions:\n";
    for (int i = 19; i <= 26; ++i) {
      const auto & pt = kPointList[i];
      ofs << "  " << pt.yaml_key << ": [" << pt.x << ", " << pt.y << ", " << pt.theta
          << "]    # " << pt.description << "\n";
    }
    ofs << "\n";

    ofs.close();
    printf("  ✅ 已保存到: %s\n", output_path_.c_str());
  }

  // 实时位姿显示
  void PrintStatusLine()
  {
    if (!odom_received_) {
      printf("  ⏳ 等待里程计: %s  ...\r", odom_topic_.c_str());
      fflush(stdout);
      return;
    }

    const auto & pt = kPointList[target_idx_];
    const char * status = pt.recorded ? "✅" : "⬜";

    printf("  当前: (%.4f, %.4f, %.1f°)  |  %s [%2d] %-10s  |  s=保存 n/p=切换  \r",
           cur_x_, cur_y_, cur_yaw_ * 180.0 / M_PI,
           status, target_idx_ + 1, pt.yaml_key.c_str());
    fflush(stdout);
  }

  // =========================
  // 成员
  // =========================
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;

  std::string odom_topic_{"/lio/odom"};
  std::string output_path_;

  double cur_x_{0}, cur_y_{0}, cur_yaw_{0};
  bool odom_received_{false};

  int target_idx_;  // 当前目标点位索引
  std::atomic<bool> keyboard_running_{false};
  std::thread keyboard_thread_;

  // 编号输入模式（直接跳转用）
  bool num_input_mode_{false};   // 是否正在输入编号
  std::string num_input_;        // 输入中的编号字符串

  // 未保存改动标记 + 退出二次确认
  bool dirty_{false};            // 自上次 w 输出后有改动（s/撤销/清空）
  bool quit_confirm_{false};     // q 已按过一次，等待二次确认
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<RecordPointsNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}