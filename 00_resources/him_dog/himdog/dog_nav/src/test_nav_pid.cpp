// ========================================================================================
// test_nav_pid.cpp — 雷达导航基础动作测试（RL 底盘版：两档 + 提前量 + 死区 + 稳态确认）
// ========================================================================================
//
// ★ 针对 RL 足式底盘重写，放弃轮式 PID 思路:
//
//   1. 两档 bang-bang 速度:
//      远处给巡航速度 cruise，接近给最小能动速度 min
//      （RL 没有连续减速档位，低于 min 就停，强行 P 控制会卡死）
//
//   2. 提前量 overshoot 补偿:
//      发 vx=0 后会惯性滑一段，所以提前一段距离/角度就停
//      overshoot 需要实测标定，先设 0，看偏多少再补
//
//   3. 死区 deadband:
//      误差小于 deadband 直接停（vx=0 是优雅停车）
//
//   4. 稳态确认 steady_confirm:
//      连续 N 拍满足容差才算到达，防抖动误判
//
//   5. 超时兜底:
//      实在走不到（policy 卡住）超时强制停
//
// 不用 D 项（RL 误差微分是噪声）、不用速度斜坡（policy 自带平滑）
//
// 测试序列与 test_nav_movement.cpp 完全一致，方便对比
//
// 运行:
//   ros2 run dog_nav test_nav_pid
//
// 调参举例:
//   ros2 run dog_nav test_nav_pid --ros-args
//     -p cruise_vx:=0.3 -p min_vx:=0.2 -p switch_dist:=0.30
//     -p cruise_wz:=0.8 -p min_wz:=0.5 -p switch_angle:=0.30
//     -p overshoot_pos:=0.0 -p overshoot_yaw:=0.0
//     -p deadband_pos:=0.05 -p deadband_yaw:=0.05
//     -p steady_confirm:=3

#include <rclcpp/rclcpp.hpp>
#include <dog_nav/msg/dog_nav_command.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>

#include <cmath>
#include <string>
#include <vector>

using DogNavCommand = dog_nav::msg::DogNavCommand;

// ========================================================================================
// 测试项定义（与 test_nav_movement.cpp 保持一致）
// ========================================================================================

enum class TestAction
{
  ROTATE,   // 原地旋转（弧度）
  MOVE_X,   // 沿 X 前进（米）
  STOP,     // 停车
};

struct TestItem
{
  std::string name;
  TestAction action;
  double value;        // 旋转: 弧度, 移动: 米
  double tolerance;    // 允许误差
  double timeout_sec;  // 超时
};

// ========================================================================================
// 测试节点
// ========================================================================================

class TestNavPid : public rclcpp::Node
{
public:
  TestNavPid()
  : Node("test_nav_pid")
  {
    // =========================
    // 参数声明
    // =========================

    // 通用
    this->declare_parameter("odom_topic",    std::string("/lio/odom"));
    this->declare_parameter("cmd_topic",     std::string("/nav_cmd"));
    this->declare_parameter("pos_tolerance", 0.05);
    this->declare_parameter("yaw_tolerance", 0.087);
    this->declare_parameter("test_delay_sec", 1.0);

    // ★ MOVE_X 速度档位
    this->declare_parameter("cruise_vx",   0.3);    // 远处巡航速度
    this->declare_parameter("min_vx",      0.2);    // 最小能动速度（policy 死区）
    this->declare_parameter("switch_dist", 0.30);   // 切到最小速度的距离（米）

    // ★ ROTATE 速度档位
    this->declare_parameter("cruise_wz",   0.8);    // 远处巡航角速度
    this->declare_parameter("min_wz",      0.5);    // 最小能动角速度
    this->declare_parameter("switch_angle", 0.30);  // 切到最小速度的角度（弧度）

    // ★ 提前量（过冲补偿），先设 0，实测标定
    this->declare_parameter("overshoot_pos", 0.0);  // 米
    this->declare_parameter("overshoot_yaw", 0.0);  // 弧度

    // ★ 死区 + 稳态确认
    this->declare_parameter("deadband_pos", 0.05);
    this->declare_parameter("deadband_yaw", 0.05);
    this->declare_parameter("steady_confirm", 3);

    // =========================
    // 读取参数
    // =========================
    odom_topic_  = this->get_parameter("odom_topic").as_string();
    cmd_topic_   = this->get_parameter("cmd_topic").as_string();
    pos_tol_     = this->get_parameter("pos_tolerance").as_double();
    yaw_tol_     = this->get_parameter("yaw_tolerance").as_double();
    test_delay_  = this->get_parameter("test_delay_sec").as_double();

    cruise_vx_   = this->get_parameter("cruise_vx").as_double();
    min_vx_      = this->get_parameter("min_vx").as_double();
    switch_dist_ = this->get_parameter("switch_dist").as_double();

    cruise_wz_     = this->get_parameter("cruise_wz").as_double();
    min_wz_        = this->get_parameter("min_wz").as_double();
    switch_angle_  = this->get_parameter("switch_angle").as_double();

    overshoot_pos_ = this->get_parameter("overshoot_pos").as_double();
    overshoot_yaw_ = this->get_parameter("overshoot_yaw").as_double();

    deadband_pos_ = this->get_parameter("deadband_pos").as_double();
    deadband_yaw_ = this->get_parameter("deadband_yaw").as_double();
    steady_confirm_ = static_cast<int>(this->get_parameter("steady_confirm").as_int());

    // =========================
    // 订阅 + 发布
    // =========================
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

    cmd_pub_ = this->create_publisher<DogNavCommand>(cmd_topic_, 10);

    // =========================
    // 测试序列（与 test_nav_movement 完全一致）
    // =========================
    tests_ = {
      {"右转 90°",        TestAction::ROTATE, -M_PI / 2.0, yaw_tol_, 10.0},
      {"左转 90°（回正）",  TestAction::ROTATE,  M_PI / 2.0, yaw_tol_, 10.0},
      {"转 180°",         TestAction::ROTATE,  M_PI,       yaw_tol_, 10.0},
      {"转回 0°",          TestAction::ROTATE, -M_PI,       yaw_tol_, 10.0},
      {"前进 0.3m",       TestAction::MOVE_X,  0.3,        pos_tol_, 10.0},
      {"后退 0.3m（回原点）", TestAction::MOVE_X, -0.3,      pos_tol_, 10.0},
      {"前进 1.0m",       TestAction::MOVE_X,  1.0,        pos_tol_, 15.0},
      {"后退 1.0m（回原点）", TestAction::MOVE_X, -1.0,      pos_tol_, 15.0},
      {"停车",            TestAction::STOP,    0.0,        0.0,     0.0},
    };

    // 定时器 50Hz
    timer_ = this->create_wall_timer(
      std::chrono::milliseconds(20),
      std::bind(&TestNavPid::TimerCallback, this));

    // =========================
    // 启动横幅
    // =========================
    RCLCPP_INFO(this->get_logger(), "========================================");
    RCLCPP_INFO(this->get_logger(), "  ★ 雷达导航基础动作测试（RL 两档版）");
    RCLCPP_INFO(this->get_logger(), "  里程计: %s", odom_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "  指令:   %s", cmd_topic_.c_str());
    RCLCPP_INFO(this->get_logger(),
      "  MOVE_X: cruise=%.2f min=%.2f switch=%.2f overshoot=%.3f deadband=%.3f",
      cruise_vx_, min_vx_, switch_dist_, overshoot_pos_, deadband_pos_);
    RCLCPP_INFO(this->get_logger(),
      "  ROTATE: cruise=%.2f min=%.2f switch=%.2f overshoot=%.3f deadband=%.3f",
      cruise_wz_, min_wz_, switch_angle_, overshoot_yaw_, deadband_yaw_);
    RCLCPP_INFO(this->get_logger(), "  steady_confirm=%d", steady_confirm_);
    RCLCPP_INFO(this->get_logger(), "  共 %zu 个测试项", tests_.size());
    RCLCPP_INFO(this->get_logger(), "========================================");

    for (size_t i = 0; i < tests_.size(); ++i) {
      RCLCPP_INFO(this->get_logger(), "  [%zu] %s", i + 1, tests_[i].name.c_str());
    }

    RCLCPP_INFO(this->get_logger(), "等待里程计数据...");
  }

private:

  static double NormalizeAngle(double a)
  {
    while (a > M_PI) a -= 2.0 * M_PI;
    while (a < -M_PI) a += 2.0 * M_PI;
    return a;
  }

  // ========================================================================================
  // ★ 两档速度选择
  // ========================================================================================
  // |error| > switch      → cruise（全速）
  // deadband < |error| <= switch → min（最小能动）
  // |error| <= deadband   → 0（停）
  //
  // 返回 (速度大小, 是否在死区)
  //
  static double TwoStageSpeed(double error, double cruise, double min_v,
    double switch_th, double deadband)
  {
    double abs_err = std::abs(error);
    if (abs_err <= deadband) return 0.0;       // 死区 → 停
    double mag = (abs_err > switch_th) ? cruise : min_v;
    return (error > 0) ? mag : -mag;
  }

  // ========================================================================================
  // TimerCallback — 主循环
  // ========================================================================================
  void TimerCallback()
  {
    double now = this->now().seconds();

    if (!odom_received_) {
      return;
    }

    // 初始位姿锁定
    if (!initialized_) {
      start_x_ = cur_x_;
      start_y_ = cur_y_;
      start_yaw_ = cur_yaw_;
      initialized_ = true;
      phase_start_time_ = now;
      RCLCPP_INFO(this->get_logger(),
        "✅ 里程计就位，初始位姿: (%.3f, %.3f, %.1f°)",
        start_x_, start_y_, start_yaw_ * 180.0 / M_PI);
      return;
    }

    DogNavCommand cmd;
    cmd.header.stamp = this->now();
    cmd.header.frame_id = "base_link";
    cmd.height = 0.25f;

    // 测试间延迟（停车稳定）
    if (in_delay_) {
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      cmd_pub_->publish(cmd);
      if (now - phase_start_time_ < test_delay_) {
        return;
      }
      in_delay_ = false;
    }

    // 全部完成
    if (test_idx_ >= tests_.size()) {
      if (!all_done_) {
        all_done_ = true;
        RCLCPP_INFO(this->get_logger(), " ");
        RCLCPP_INFO(this->get_logger(), "========================================");
        RCLCPP_INFO(this->get_logger(), "  ✅ 全部 %zu 项测试完成!", tests_.size());
        RCLCPP_INFO(this->get_logger(), "  通过: %zu / %zu", passed_, tests_.size());
        if (passed_ == tests_.size()) {
          RCLCPP_INFO(this->get_logger(), "  🎉 全部通过！");
        }
        RCLCPP_INFO(this->get_logger(), "========================================");
      }
      // 持续发零速，确保安全
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      cmd_pub_->publish(cmd);
      return;
    }

    const auto & test = tests_[test_idx_];
    double elapsed = now - phase_start_time_;

    // ====== STOP ======
    if (test.action == TestAction::STOP) {
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      cmd_pub_->publish(cmd);
      PrintResult(test, true, 0.0, 0.0);
      AdvanceTest(now);
      return;
    }

    // ====== ROTATE ======
    if (test.action == TestAction::ROTATE) {
      // 真实目标 yaw
      double real_target_yaw = start_yaw_ + test.value;

      // ★ 提前量：有效目标 = 真实目标 - overshoot（顺着运动方向回退一点）
      //   转动方向由 test.value 的符号决定
      double overshoot = (test.value >= 0) ? overshoot_yaw_ : -overshoot_yaw_;
      double effective_target_yaw = start_yaw_ + test.value - overshoot;

      double error = NormalizeAngle(effective_target_yaw - cur_yaw_);

      // 稳态确认（用真实目标判定到达，不用提前量后的）
      double real_error = NormalizeAngle(real_target_yaw - cur_yaw_);
      if (std::abs(real_error) < test.tolerance) {
        steady_count_++;
      } else {
        steady_count_ = 0;
      }

      if ((steady_count_ >= steady_confirm_) || elapsed > test.timeout_sec) {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        cmd_pub_->publish(cmd);
        double actual = NormalizeAngle(cur_yaw_ - start_yaw_);
        bool ok = std::abs(NormalizeAngle(actual - test.value)) < test.tolerance;
        PrintResult(test, ok, test.value, actual);
        if (ok) passed_++;
        AdvanceTest(now);
        return;
      }

      // 两档速度
      double wz = TwoStageSpeed(error, cruise_wz_, min_wz_,
        switch_angle_, deadband_yaw_);

      cmd.vx = 0.0f;
      cmd.vy = 0.0f;
      cmd.wz = static_cast<float>(wz);
      cmd_pub_->publish(cmd);
      return;
    }

    // ====== MOVE_X ======
    if (test.action == TestAction::MOVE_X) {
      // 沿起始朝向投影的实际位移
      double actual_dx = (cur_x_ - start_x_) * std::cos(start_yaw_) +
                         (cur_y_ - start_y_) * std::sin(start_yaw_);

      // ★ 提前量：有效目标 = 真实目标 - overshoot
      double overshoot = (test.value >= 0) ? overshoot_pos_ : -overshoot_pos_;
      double effective_target = test.value - overshoot;
      double error = effective_target - actual_dx;

      // 稳态确认（用真实目标判定到达）
      double real_error = test.value - actual_dx;
      if (std::abs(real_error) < test.tolerance) {
        steady_count_++;
      } else {
        steady_count_ = 0;
      }

      if ((steady_count_ >= steady_confirm_) || elapsed > test.timeout_sec) {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        cmd_pub_->publish(cmd);
        bool ok = std::abs(real_error) < test.tolerance;
        PrintResult(test, ok, test.value, actual_dx);
        if (ok) passed_++;
        AdvanceTest(now);
        return;
      }

      // 两档速度
      double vx = TwoStageSpeed(error, cruise_vx_, min_vx_,
        switch_dist_, deadband_pos_);

      cmd.vx = static_cast<float>(vx);
      cmd.vy = 0.0f;
      cmd.wz = 0.0f;
      cmd_pub_->publish(cmd);
      return;
    }
  }

  void AdvanceTest(double now)
  {
    test_idx_++;
    // 记录下一个测试的起始位姿
    start_x_ = cur_x_;
    start_y_ = cur_y_;
    start_yaw_ = cur_yaw_;
    phase_start_time_ = now;
    in_delay_ = true;
    steady_count_ = 0;
  }

  void PrintResult(const TestItem & test, bool pass, double expected, double actual)
  {
    const char * result_str = pass ? "✅ PASS" : "❌ FAIL";
    if (test.action == TestAction::ROTATE) {
      RCLCPP_INFO(this->get_logger(),
        "%s [%zu] %-20s  期望: %.1f°  实际: %.1f°  误差: %.1f°",
        result_str, test_idx_ + 1, test.name.c_str(),
        expected * 180.0 / M_PI, actual * 180.0 / M_PI,
        (actual - expected) * 180.0 / M_PI);
    } else if (test.action == TestAction::MOVE_X) {
      RCLCPP_INFO(this->get_logger(),
        "%s [%zu] %-20s  期望: %.3fm  实际: %.3fm  误差: %.3fm",
        result_str, test_idx_ + 1, test.name.c_str(),
        expected, actual, actual - expected);
    } else {
      RCLCPP_INFO(this->get_logger(), "   [%zu] %s", test_idx_ + 1, test.name.c_str());
    }
  }

  // =========================
  // 成员
  // =========================
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Publisher<DogNavCommand>::SharedPtr cmd_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  // 参数
  std::string odom_topic_{"/lio/odom"};
  std::string cmd_topic_{"/nav_cmd"};
  double pos_tol_{0.05};
  double yaw_tol_{0.087};
  double test_delay_{1.0};

  // MOVE_X 档位
  double cruise_vx_{0.3};
  double min_vx_{0.2};
  double switch_dist_{0.30};

  // ROTATE 档位
  double cruise_wz_{0.8};
  double min_wz_{0.5};
  double switch_angle_{0.30};

  // 提前量
  double overshoot_pos_{0.0};
  double overshoot_yaw_{0.0};

  // 死区 + 稳态
  double deadband_pos_{0.05};
  double deadband_yaw_{0.05};
  int    steady_confirm_{3};

  // 位姿
  double cur_x_{0}, cur_y_{0}, cur_yaw_{0};
  double start_x_{0}, start_y_{0}, start_yaw_{0};
  bool odom_received_{false};
  bool initialized_{false};
  bool all_done_{false};
  bool in_delay_{true};
  double phase_start_time_{0};

  // 稳态计数
  int    steady_count_{0};

  // 测试序列
  std::vector<TestItem> tests_;
  size_t test_idx_{0};
  size_t passed_{0};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TestNavPid>());
  rclcpp::shutdown();
  return 0;
}
