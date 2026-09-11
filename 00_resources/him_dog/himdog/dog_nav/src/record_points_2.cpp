// ========================================================================================
// record_points_2.cpp — 打点工具（★ 新机构版，10 节点，输出 task_race_2.yaml）
// ========================================================================================
//
// 与 record_points.cpp 的区别:
//   - 10 节点布局（无点13/14，点6-9 是放货点）
//   - 输出 task_race_2.yaml 的坐标段（start/pickup 1-5/place 6-9/zone 1-4）
//   - ★ 只需手打 3 个锚点（点1/点2/点6），点3/4/5/7/8/9 由几何推理自动算出（按 i 触发）
//
// 场地布局（10 节点）:
//   【01】  【02】  【03】  【04】     归位区
//   【点6】 【点7】 【点8】 【点9】     放货点（zone1→6...zone4→9）
//   ============减速带============
//   【05】【点4】【06】  【07】【点5】【08】   第二排
//   【09】【点2】【10】  【11】【点3】【12】   第一排
//            【点1】                起点前
//            【0】                  起点
//
// 打点流程（★ 3 锚点）:
//   手打 点1 / 点2 / 点6 三个锚点（s 记录）→ 按 i 推理出 点3/4/5/7/8/9 → 按 w 输出
//   点0(start) 与 zone1-4 不导航，可打可不打，不打则保留 0
//   手打覆盖推理: 若某点已手打(recorded && !derived)，推理不会覆盖它
//
// 用法:
//   ros2 run dog_nav record_points_2 --ros-args
//     -p output_path:=src/dog_nav/config/task_race_2.yaml
//   操作: 输入编号回车跳转 → s 记录 → i 推理 → w 输出 → q 退出（有未保存改动会提示）

#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <fstream>
#include <termios.h>
#include <unistd.h>

using nav_msgs::msg::Odometry;

// ========================================================================================
// 点位定义（10 个点位：start + point_1~9）
// ========================================================================================

struct PointEntry
{
  std::string yaml_key;     // yaml 参数名（不含前缀）
  std::string category;     // start / pickup / place / zone
  std::string description;  // 中文描述
  double x, y, theta;       // 坐标 + 朝向（度）
  bool recorded;            // 是否已记录（手打或推理）
  bool derived;             // 是否由锚点推理得出（非手打）
};

// ========================================================================================
// ★ 打点推理常量（坐标系: x 右为正, y 前为正, theta 度）
// ========================================================================================
//   取货点: 箱相邻 0.6m, 站位=两箱中点（离每箱 0.3m）; 第一排↔第二排行距 0.6m
//     → 同排点2→点3 横移 1.2m; 点2→点4(第二排) 纵移 0.6m
//   放货点: 归位区 01-04 间距 0.4m, 放货点与之同列 → 点6→点7→点8→点9 x 方向 0.4m 递增
//   只需手打 3 个锚点: 点1(枢纽) / 点2(取货锚点) / 点6(放货锚点), 其余 6 个自动推理
constexpr double kPickupDx = 1.2;   // 取货点同排横移（米）
constexpr double kPickupDy = 0.6;   // 取货点跨排纵移（米）
constexpr double kPlaceDx  = 0.4;   // 放货点 x 方向递增（米）

// 10 个点位（start + point_1~9，其中点1/2/6 为手打锚点，余下推理）
// derived 字段: false=手打/未记录; true=由锚点推理得出
static std::vector<PointEntry> kPointList = {
  // 起点（不导航，可打可不打）
  {"start_pose",  "start",  "起点 (点0)",                   0, 0, 0, false, false},

  // 取货站位点（点1-5）
  {"point_1",     "pickup", "★锚点 起点前 (点1, 枢纽不取货)", 0, 0, 0, false, false},
  {"point_2",     "pickup", "★锚点 第一排左 (点2, 吸09+10)",  0, 0, 0, false, false},
  {"point_3",     "pickup", "第一排右 (点3, 吸11+12)",       0, 0, 0, false, false},  // 推理自点2
  {"point_4",     "pickup", "第二排左 (点4, 吸05+06)",       0, 0, 0, false, false},  // 推理自点2
  {"point_5",     "pickup", "第二排右 (点5, 吸07+08)",       0, 0, 0, false, false},  // 推理自点2

  // 放货站位点（点6-9，归位区旁，1对1）
  {"point_6",     "place",  "★锚点 归位区01旁 (点6, 放zone1)", 0, 0, 0, false, false},
  {"point_7",     "place",  "归位区02旁 (点7, 放zone2)",     0, 0, 0, false, false},  // 推理自点6
  {"point_8",     "place",  "归位区03旁 (点8, 放zone3)",     0, 0, 0, false, false},  // 推理自点6
  {"point_9",     "place",  "归位区04旁 (点9, 放zone4)",     0, 0, 0, false, false},  // 推理自点6

};

// 索引布局:
//   0       = start_pose
//   1-5     = point_1 ~ point_5（pickup）
//   6-9     = point_6 ~ point_9（place）


class RecordPoints2Node : public rclcpp::Node
{
public:
  RecordPoints2Node()
  : Node("record_points_2_node"), target_idx_(0)
  {
    // 参数: 输出文件路径（空则只打印到终端）
    this->declare_parameter("output_path", std::string(""));
    this->declare_parameter("odom_topic", std::string("/lio/odom"));
    output_path_ = this->get_parameter("output_path").as_string();
    std::string odom_topic = this->get_parameter("odom_topic").as_string();

    odom_sub_ = this->create_subscription<Odometry>(
      odom_topic, rclcpp::QoS(10).best_effort(),
      std::bind(&RecordPoints2Node::OdomCallback, this, std::placeholders::_1));

    keyboard_running_ = true;
    keyboard_thread_ = std::thread(&RecordPoints2Node::KeyboardLoop, this);

    // 打印欢迎
    printf("\n");
    printf("╔══════════════════════════════════════════════════╗\n");
    printf("║  ★ 打点工具 record_points_2（10 节点，3 锚点）    ║\n");
    printf("╠══════════════════════════════════════════════════╣\n");
    printf("║  订阅 %s\n", odom_topic.c_str());
    printf("║  ★ 只需打 3 个锚点: 点1/点2/点6 (其余自动推理)     ║\n");
    printf("╠══════════════════════════════════════════════════╣\n");
    printf("║  s = 保存当前位置为当前目标点位                    ║\n");
    printf("║  i = 由锚点推理 点3/4/5/7/8/9 并显示               ║\n");
    printf("║  数字 = 输入编号直接跳转(回车确认)                 ║\n");
    printf("║  n = 下一个点位    p = 上一个点位                  ║\n");
    printf("║  u = 撤销上一个    l = 列出所有点位                ║\n");
    printf("║  w = 输出 YAML     r = 清空重来                    ║\n");
    printf("║  q = 退出                                         ║\n");
    printf("╚══════════════════════════════════════════════════╝\n");
    printf("\n");

    // 定位到第一个未记录点
    for (size_t i = 0; i < kPointList.size(); ++i) {
      if (!kPointList[i].recorded) {
        target_idx_ = static_cast<int>(i);
        break;
      }
    }
    target_idx_ = 0;
    PrintTargetInfo();
  }

  ~RecordPoints2Node()
  {
    keyboard_running_ = false;
    if (keyboard_thread_.joinable()) {
      keyboard_thread_.join();
    }
  }

private:

  void OdomCallback(const Odometry::SharedPtr msg)
  {
    cur_x_ = msg->pose.pose.position.x;
    cur_y_ = msg->pose.pose.position.y;
    tf2::Quaternion q(
      msg->pose.pose.orientation.x, msg->pose.pose.orientation.y,
      msg->pose.pose.orientation.z, msg->pose.pose.orientation.w);
    tf2::Matrix3x3 m(q);
    double roll, pitch, yaw;
    m.getRPY(roll, pitch, yaw);
    cur_yaw_deg_ = yaw * 180.0 / M_PI;
    odom_received_ = true;
  }

  // ========================================================================================
  // KeyboardLoop
  // ========================================================================================
  void KeyboardLoop()
  {
    // raw 模式（单字符）
    termios oldt, newt;
    tcgetattr(STDIN_FILENO, &oldt);
    newt = oldt;
    newt.c_lflag &= ~(ICANON | ECHO);
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);

    while (keyboard_running_ && rclcpp::ok()) {
      char c = 0;
      if (read(STDIN_FILENO, &c, 1) != 1) continue;

      // ===== 数字输入模式 =====
      if (num_input_mode_) {
        if (c >= '0' && c <= '9') {
          if (num_input_.size() < 2) {
            num_input_ += c;
            PrintNumInputLine();
          }
          continue;
        }
        if (c == 127 || c == 8) {
          if (!num_input_.empty()) {
            num_input_.pop_back();
            PrintNumInputLine();
          }
          continue;
        }
        if (c == '\n' || c == '\r') {
          ConfirmNumInput();
          continue;
        }
        if (c == 27) {
          CancelNumInput();
          continue;
        }
        continue;
      }

      // ===== 普通模式 =====
      if (c >= '0' && c <= '9') {
        num_input_mode_ = true;
        num_input_ = std::string(1, c);
        PrintNumInputLine();
        continue;
      }

      if (quit_confirm_ && c != 'q') {
        quit_confirm_ = false;
      }

      switch (c) {
        case 's':
          SaveCurrentPoint();
          break;
        case 'n':
          if (target_idx_ + 1 < static_cast<int>(kPointList.size())) {
            target_idx_++;
          } else {
            target_idx_ = 0;
          }
          PrintTargetInfo();
          break;
        case 'p':
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
        case 'i':
          InferAndShow();
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

    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
  }

  // ========================================================================================
  // 数字跳转
  // ========================================================================================
  void ConfirmNumInput()
  {
    if (num_input_.empty()) {
      CancelNumInput();
      return;
    }
    int num = std::atoi(num_input_.c_str());
    num_input_.clear();
    num_input_mode_ = false;

    if (num < 1 || num > static_cast<int>(kPointList.size())) {
      printf("\n  ⚠️ 编号 %d 超范围（1~%zu），已取消\n\n", num, kPointList.size());
      return;
    }
    target_idx_ = num - 1;
    printf("\n");
    PrintTargetInfo();
  }

  void CancelNumInput()
  {
    num_input_.clear();
    num_input_mode_ = false;
    printf("\n  ✘ 已取消编号输入\n\n");
  }

  void PrintNumInputLine() const
  {
    printf("  跳转到编号: [%s] (1~%zu, 回车确认 / backspace删除 / esc取消)  \r",
           num_input_.c_str(), kPointList.size());
    fflush(stdout);
  }

  // ========================================================================================
  // 打印当前目标点位
  // ========================================================================================
  void PrintTargetInfo() const
  {
    const auto & pt = kPointList[target_idx_];
    printf("┌─────────────────────────────────────────────────\n");
    printf("│ 当前目标 [%2d/%2zu] %s\n",
           target_idx_ + 1, kPointList.size(), pt.description.c_str());
    if (pt.recorded && pt.derived) {
      printf("│ 🧮 推理坐标: (%.4f, %.4f, %.1f°) （按 s 覆盖为手打）\n",
             pt.x, pt.y, pt.theta);
    } else if (pt.recorded) {
      printf("│ ★ 已有坐标: (%.4f, %.4f, %.1f°) 再按 s 会覆盖\n",
             pt.x, pt.y, pt.theta);
    } else {
      printf("│ （未记录）\n");
    }
    printf("│ 当前位姿: (%.4f, %.4f, %.1f°)%s\n",
           cur_x_, cur_y_, cur_yaw_deg_,
           odom_received_ ? "" : "  ⚠️ 未收到里程计");
    printf("└─────────────────────────────────────────────────\n");
    printf("  按 s 保存 / i推理 / 数字跳转 / n下一个 / p上一个 / l列表 / w输出 / q退出\n\n");
  }

  // ========================================================================================
  // ★ RefreshDerived — 由锚点推理出其余点（锚点一变即刷新）
  // ========================================================================================
  //
  // 坐标系: x 右为正, y 前为正, theta 度
  //   取货点（锚点 = 点2，θ 继承点2）:
  //     点3 = 点2 + (+kPickupDx, 0)        同排右移
  //     点4 = 点2 + (0, +kPickupDy)        第二排
  //     点5 = 点2 + (+kPickupDx, +kPickupDy) 第二排右
  //   放货点（锚点 = 点6，x 方向 kPlaceDx 递增，θ 与 y 继承点6）:
  //     点7 = 点6 + (+1·kPlaceDx, 0)
  //     点8 = 点6 + (+2·kPlaceDx, 0)
  //     点9 = 点6 + (+3·kPlaceDx, 0)
  //
  // 手打覆盖优先: 仅当某点未手打(recorded && !derived 不成立)时才填推理值
  //
  void RefreshDerived()
  {
    // 1. 清掉所有 derived 点（让推理完全由当前锚点重算）
    for (auto & pt : kPointList) {
      if (pt.derived) {
        pt.recorded = false;
        pt.derived = false;
        pt.x = 0; pt.y = 0; pt.theta = 0;
      }
    }

    // 2. 取货点: 点2(索引2) → 点3/4/5(索引 3/4/5)
    if (kPointList[2].recorded && !kPointList[2].derived) {
      const auto & a = kPointList[2];
      struct D { int idx; double dx; double dy; };
      const D pickup[] = {
        {3, kPickupDx, 0.0},
        {4, 0.0, kPickupDy},
        {5, kPickupDx, kPickupDy},
      };
      for (const auto & d : pickup) {
        auto & pt = kPointList[d.idx];
        if (!pt.recorded) {  // 未手打才填
          pt.x = a.x + d.dx;
          pt.y = a.y + d.dy;
          pt.theta = a.theta;
          pt.recorded = true;
          pt.derived = true;
        }
      }
    }

    // 3. 放货点: 点6(索引6) → 点7/8/9(索引 7/8/9)
    if (kPointList[6].recorded && !kPointList[6].derived) {
      const auto & a = kPointList[6];
      for (int k = 1; k <= 3; ++k) {
        auto & pt = kPointList[6 + k];
        if (!pt.recorded) {  // 未手打才填
          pt.x = a.x + k * kPlaceDx;
          pt.y = a.y;
          pt.theta = a.theta;
          pt.recorded = true;
          pt.derived = true;
        }
      }
    }
  }

  // ========================================================================================
  // SaveCurrentPoint
  // ========================================================================================
  void SaveCurrentPoint()
  {
    if (!odom_received_) {
      printf("  ⚠️ 未收到里程计，无法保存\n\n");
      return;
    }
    auto & pt = kPointList[target_idx_];
    pt.x = cur_x_;
    pt.y = cur_y_;
    pt.theta = cur_yaw_deg_;
    pt.recorded = true;
    pt.derived = false;  // 手打的一定不是推理点

    printf("\n");
    printf("  ✅ [%2d/%2zu] %-10s %-30s → (%.4f, %.4f, %.1f°)\n",
           target_idx_ + 1, kPointList.size(),
           pt.yaml_key.c_str(), pt.description.c_str(),
           pt.x, pt.y, pt.theta);

    // 锚点变了 → 重算推理点
    RefreshDerived();

    dirty_ = true;

    // ★ 完成判定: 只要 3 个锚点（点1/点2/点6）都已手打就算齐活
    //   推理点随之自动算出；点0(start) 与 zone1-4 不导航，可打可不打
    bool anchors_ready = kPointList[1].recorded && !kPointList[1].derived
                       && kPointList[2].recorded && !kPointList[2].derived
                       && kPointList[6].recorded && !kPointList[6].derived;
    if (anchors_ready) {
      printf("  🎉 3 个锚点（点1/2/6）齐了，推理点已自动算出！按 w 输出 YAML\n\n");
    } else {
      // 提示还缺哪个锚点（索引 1=点1, 2=点2, 6=点6）
      printf("  （停在本点）还缺锚点:");
      const int anchors[] = {1, 2, 6};
      for (int idx : anchors) {
        if (!(kPointList[idx].recorded && !kPointList[idx].derived)) {
          printf(" 点%d", idx);
        }
      }
      printf(" （输入编号跳转）\n\n");
    }
  }

  // ========================================================================================
  // UndoLast
  // ========================================================================================
  void UndoLast()
  {
    int last = -1;
    for (int i = static_cast<int>(kPointList.size()) - 1; i >= 0; --i) {
      // 优先撤销手打点（derived 点会随锚点重算，不单独撤）
      if (kPointList[i].recorded && !kPointList[i].derived) {
        last = i;
        break;
      }
    }
    if (last < 0) {
      printf("  ⚠️ 没有手打的点可撤销（推理点随锚点自动刷新）\n\n");
      return;
    }
    auto & pt = kPointList[last];
    printf("  ↩️  撤销 [%2d] %s (%.4f, %.4f, %.1f°)\n",
           last + 1, pt.yaml_key.c_str(), pt.x, pt.y, pt.theta);
    pt.recorded = false;
    pt.derived = false;
    pt.x = 0; pt.y = 0; pt.theta = 0;
    target_idx_ = last;
    // 撤销的可能是锚点 → 重算推理点
    RefreshDerived();
    dirty_ = true;
  }

  // ========================================================================================
  // ★ InferAndShow — 手动触发推理并打印结果（快捷键 i）
  // ========================================================================================
  void InferAndShow()
  {
    RefreshDerived();
    dirty_ = true;

    printf("\n");
    printf("  🧮 推理结果（基于点1/点2/点6）:\n");
    bool has_p2 = kPointList[2].recorded && !kPointList[2].derived;
    bool has_p6 = kPointList[6].recorded && !kPointList[6].derived;

    if (!has_p2 && !has_p6) {
      printf("    ⚠️ 锚点 点2 和 点6 都还没打，无东西可推理\n");
      printf("    先打 点1 / 点2 / 点6 三个锚点（s 记录）\n\n");
      return;
    }

    if (has_p2) {
      const int idxs[] = {3, 4, 5};
      for (int idx : idxs) {
        const auto & pt = kPointList[idx];
        if (pt.derived) {
          printf("    点%d (推理自点2) = (%.4f, %.4f, %.1f°)\n",
                 idx, pt.x, pt.y, pt.theta);
        }
      }
    } else {
      printf("    ⚠️ 点2 未打 → 点3/4/5 无法推理\n");
    }
    if (has_p6) {
      const int idxs[] = {7, 8, 9};
      for (int idx : idxs) {
        const auto & pt = kPointList[idx];
        if (pt.derived) {
          printf("    点%d (推理自点6) = (%.4f, %.4f, %.1f°)\n",
                 idx, pt.x, pt.y, pt.theta);
        }
      }
    } else {
      printf("    ⚠️ 点6 未打 → 点7/8/9 无法推理\n");
    }
    printf("  按 w 输出 YAML\n\n");
  }

  // ========================================================================================
  // ListAllPoints
  // ========================================================================================
  void ListAllPoints() const
  {
    printf("\n");
    printf("  %-4s %-12s %-30s %-10s %s\n", "编号", "key", "描述", "状态", "坐标");
    printf("  ----------------------------------------------------------------\n");
    for (size_t i = 0; i < kPointList.size(); ++i) {
      const auto & pt = kPointList[i];
      const char * marker = (static_cast<int>(i) == target_idx_) ? " ◀ 当前" : "";
      if (pt.recorded && pt.derived) {
        printf("  %-4zu %-12s %-30s 🧮推理    (%.3f, %.3f, %.1f)%s\n",
               i + 1, pt.yaml_key.c_str(), pt.description.c_str(),
               pt.x, pt.y, pt.theta, marker);
      } else if (pt.recorded) {
        printf("  %-4zu %-12s %-30s ✅记录    (%.3f, %.3f, %.1f)%s\n",
               i + 1, pt.yaml_key.c_str(), pt.description.c_str(),
               pt.x, pt.y, pt.theta, marker);
      } else {
        printf("  %-4zu %-12s %-30s ❌未记录              %s\n",
               i + 1, pt.yaml_key.c_str(), pt.description.c_str(), marker);
      }
    }
    // ★ 锚点完成度（点1/点2/点6）
    int anchors_done = 0;
    const int anchors[] = {1, 2, 6};
    for (int idx : anchors) {
      if (kPointList[idx].recorded && !kPointList[idx].derived) anchors_done++;
    }
    printf("\n  锚点完成: %d / 3 （点1/点2/点6）  点位总计: 已记录 %d / %zu\n\n",
           anchors_done, [&] {
             int r = 0;
             for (const auto & p : kPointList) if (p.recorded) r++;
             return r;
           }(), kPointList.size());
  }

  // ========================================================================================
  // ResetAll
  // ========================================================================================
  void ResetAll()
  {
    for (auto & pt : kPointList) {
      pt.recorded = false;
      pt.derived = false;
      pt.x = 0; pt.y = 0; pt.theta = 0;
    }
    target_idx_ = 0;
    dirty_ = true;
    printf("  🔄 已清空所有点位（含推理点），重新开始\n");
  }

  // ========================================================================================
  // OutputYAML — 输出到终端（task_race_2.yaml 的坐标段格式）
  // ========================================================================================
  void OutputYAML()
  {
    // 输出前先刷新推理点，确保 derived 坐标与当前锚点一致
    RefreshDerived();

    int recorded = 0;
    for (const auto & p : kPointList) if (p.recorded) recorded++;
    printf("\n");
    printf("╔══════════════════════════════════════════════════╗\n");
    printf("║  输出 YAML（task_race_2.yaml 坐标段）             ║\n");
    printf("╠══════════════════════════════════════════════════╝\n");
    printf("# 已记录 %d / %zu 个点位（含推理点）\n", recorded, kPointList.size());
    printf("# 复制下面内容替换 task_race_2.yaml 的对应段\n\n");

    // start_pose
    if (kPointList[0].recorded) {
      const auto & pt = kPointList[0];
      printf("start_pose: [%.4f, %.4f, %.1f]    # %s\n",
             pt.x, pt.y, pt.theta, pt.description.c_str());
    } else {
      printf("start_pose: [0.0, 0.0, 0.0]    # 未记录: %s\n",
             kPointList[0].description.c_str());
    }
    printf("\n");

    // pickup_positions (索引 1-5)
    printf("pickup_positions:\n");
    for (int i = 1; i <= 5; ++i) {
      const auto & pt = kPointList[i];
      if (pt.recorded) {
        printf("  %-10s [%.4f, %.4f, %.1f]    # %s%s\n",
               (pt.yaml_key + ":").c_str(), pt.x, pt.y, pt.theta,
               pt.description.c_str(), pt.derived ? " 🧮推理自点2" : "");
      } else {
        printf("  %-10s [0.0, 0.0, 0.0]          # 未记录: %s\n",
               (pt.yaml_key + ":").c_str(), pt.description.c_str());
      }
    }
    printf("\n");

    // place_positions (索引 6-9)
    printf("place_positions:\n");
    for (int i = 6; i <= 9; ++i) {
      const auto & pt = kPointList[i];
      if (pt.recorded) {
        printf("  %-10s [%.4f, %.4f, %.1f]    # %s%s\n",
               (pt.yaml_key + ":").c_str(), pt.x, pt.y, pt.theta,
               pt.description.c_str(), pt.derived ? " 🧮推理自点6" : "");
      } else {
        printf("  %-10s [0.0, 0.0, 0.0]          # 未记录: %s\n",
               (pt.yaml_key + ":").c_str(), pt.description.c_str());
      }
    }
    printf("\n");

    if (!output_path_.empty()) {
      SaveToFile();
    } else {
      printf("  💡 复制上面的内容替换 task_race_2.yaml 中的坐标部分即可\n");
      printf("  💡 或者运行时加参数 -p output_path:=/path/to/task_race_2.yaml 自动保存\n");
    }
    dirty_ = false;
  }

  // ========================================================================================
  // SaveToFile — 写入 task_race_2.yaml（替换坐标段，保留其它参数）
  // ========================================================================================
  void SaveToFile()
  {
    std::ifstream fin(output_path_);
    if (!fin.is_open()) {
      printf("  ⚠️ 无法打开 %s 读\n", output_path_.c_str());
      return;
    }
    std::vector<std::string> lines;
    std::string line;
    while (std::getline(fin, line)) lines.push_back(line);
    fin.close();

    std::ofstream ofs(output_path_, std::ios::trunc);
    if (!ofs.is_open()) {
      printf("  ⚠️ 无法打开 %s 写\n", output_path_.c_str());
      return;
    }

    size_t i = 0;
    while (i < lines.size()) {
      const std::string & l = lines[i];

      // start_pose
      if (l.find("start_pose:") == 0) {
        const auto & pt = kPointList[0];
        ofs << "start_pose: [" << pt.x << ", " << pt.y << ", " << pt.theta
            << "]    # " << pt.description << "\n";
        ++i; continue;
      }
      // pickup_positions 段
      if (l.find("pickup_positions:") == 0) {
        ofs << l << "\n";
        ++i;
        for (int k = 1; k <= 5 && i < lines.size(); ++k) {
          const auto & pt = kPointList[k];
          ofs << "  " << pt.yaml_key << ": [" << pt.x << ", " << pt.y << ", " << pt.theta
              << "]    # " << pt.description << (pt.derived ? " 🧮推理自点2" : "") << "\n";
          ++i;
        }
        continue;
      }
      // place_positions 段
      if (l.find("place_positions:") == 0) {
        ofs << l << "\n";
        ++i;
        for (int k = 6; k <= 9 && i < lines.size(); ++k) {
          const auto & pt = kPointList[k];
          ofs << "  " << pt.yaml_key << ": [" << pt.x << ", " << pt.y << ", " << pt.theta
              << "]    # " << pt.description << (pt.derived ? " 🧮推理自点6" : "") << "\n";
          ++i;
        }
        continue;
      }
      ofs << l << "\n";
      ++i;
    }
    ofs.close();
    printf("  ✅ 已写入 %s\n", output_path_.c_str());
  }

  rclcpp::Subscription<Odometry>::SharedPtr odom_sub_;
  std::thread keyboard_thread_;
  std::atomic<bool> keyboard_running_{false};

  int target_idx_;
  std::string output_path_;

  double cur_x_{0}, cur_y_{0}, cur_yaw_deg_{0};
  bool odom_received_{false};

  bool num_input_mode_{false};
  std::string num_input_;
  bool dirty_{false};
  bool quit_confirm_{false};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<RecordPoints2Node>());
  rclcpp::shutdown();
  return 0;
}
