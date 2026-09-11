// ========================================================================================
// test_nav_movement.cpp — 雷达导航基础动作测试
// ========================================================================================
//
// 测试内容:
//   1. 原地右转 90°
//   2. 原地左转 90°（回到原朝向）
//   3. 原地转 180°
//   4. 前进 0.3m
//   5. 前进 1.0m
//
// 每个动作通过 /lio/odom 里程计反馈判断是否完成
//
// 运行（上位机）:
//   ros2 run dog_nav test_nav_movement
//
// 或带参数:
//   ros2 run dog_nav test_nav_movement --ros-args
//     -p odom_topic:=/lio/odom
//     -p pos_tolerance:=0.05
//     -p yaw_tolerance:=0.087
//     -p cmd_topic:=/nav_cmd

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
// 测试项定义
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

class TestNavMovement : public rclcpp::Node
{
public:
  TestNavMovement()
  : Node("test_nav_movement")
  {
    // 参数
    this->declare_parameter("odom_topic", std::string("/lio/odom"));
    this->declare_parameter("cmd_topic", std::string("/nav_cmd"));
    this->declare_parameter("pos_tolerance", 0.05);
    this->declare_parameter("yaw_tolerance", 0.087);
    this->declare_parameter("nav_kp_xy", 0.5);
    this->declare_parameter("nav_kp_yaw", 1.5);
    this->declare_parameter("nav_max_vx", 0.3);
    this->declare_parameter("nav_max_wz", 0.8);
    this->declare_parameter("test_delay_sec", 1.0);

    odom_topic_ = this->get_parameter("odom_topic").as_string();
    cmd_topic_ = this->get_parameter("cmd_topic").as_string();
    pos_tol_ = this->get_parameter("pos_tolerance").as_double();
    yaw_tol_ = this->get_parameter("yaw_tolerance").as_double();
    kp_xy_ = this->get_parameter("nav_kp_xy").as_double();
    kp_yaw_ = this->get_parameter("nav_kp_yaw").as_double();
    max_vx_ = this->get_parameter("nav_max_vx").as_double();
    max_wz_ = this->get_parameter("nav_max_wz").as_double();
    test_delay_ = this->get_parameter("test_delay_sec").as_double();

    // 订阅 + 发布
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

    // 构建测试序列
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
      std::bind(&TestNavMovement::TimerCallback, this));

    start_time_ = this->now().seconds();

    RCLCPP_INFO(this->get_logger(), "========================================");
    RCLCPP_INFO(this->get_logger(), "  ★ 雷达导航基础动作测试");
    RCLCPP_INFO(this->get_logger(), "  里程计: %s", odom_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "  指令:   %s", cmd_topic_.c_str());
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

  void TimerCallback()
  {
    if (!odom_received_) {
      // 还没收到里程计，等
      return;
    }

    // 等待初始稳定
    if (!initialized_) {
      start_x_ = cur_x_;
      start_y_ = cur_y_;
      start_yaw_ = cur_yaw_;
      initialized_ = true;
      RCLCPP_INFO(this->get_logger(),
        "✅ 里程计就位，初始位姿: (%.3f, %.3f, %.1f°)",
        start_x_, start_y_, start_yaw_ * 180.0 / M_PI);
      phase_start_time_ = this->now().seconds();
      return;
    }

    double now = this->now().seconds();

    // 测试间延迟
    if (in_delay_) {
      if (now - phase_start_time_ < test_delay_) {
        DogNavCommand cmd;
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        cmd_pub_->publish(cmd);
        return;
      }
      in_delay_ = false;
    }

    // 全部完成
    if (test_idx_ >= tests_.size()) {
      if (!all_done_) {
        all_done_ = true;
        RCLCPP_INFO(this->get_logger(), " ");  // blank line separator
        RCLCPP_INFO(this->get_logger(), "========================================");
        RCLCPP_INFO(this->get_logger(), "  ✅ 全部 %zu 项测试完成!", tests_.size());
        RCLCPP_INFO(this->get_logger(), "  通过: %zu / %zu", passed_, tests_.size());
        if (passed_ == tests_.size()) {
          RCLCPP_INFO(this->get_logger(), "  🎉 全部通过！");
        }
        RCLCPP_INFO(this->get_logger(), "========================================");
      }
      return;
    }

    const auto & test = tests_[test_idx_];

    // ====== STOP ======
    if (test.action == TestAction::STOP) {
      DogNavCommand cmd;
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      cmd_pub_->publish(cmd);
      PrintResult(test, true, 0.0, 0.0);
      test_idx_++;
      phase_start_time_ = this->now().seconds();
      in_delay_ = true;
      return;
    }

    // ====== 计算控制量 ======
    DogNavCommand cmd;
    double elapsed = now - phase_start_time_;

    if (test.action == TestAction::ROTATE) {
      // 目标偏移量（相对于测试开始时的朝向）
      double target_yaw = start_yaw_ + test.value;  // 全局目标yaw
      double error = NormalizeAngle(target_yaw - cur_yaw_);

      if (std::abs(error) < test.tolerance || elapsed > test.timeout_sec) {
        // 完成
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        cmd_pub_->publish(cmd);
        double actual = NormalizeAngle(cur_yaw_ - start_yaw_);
        bool ok = std::abs(NormalizeAngle(actual - test.value)) < test.tolerance;
        PrintResult(test, ok, test.value, actual);
        if (ok) passed_++;
        AdvanceTest(now);
      } else {
        double wz = std::clamp(kp_yaw_ * error, -max_wz_, max_wz_);
        cmd.vx = 0.0f;
        cmd.vy = 0.0f;
        cmd.wz = static_cast<float>(wz);
        cmd_pub_->publish(cmd);
      }

    } else if (test.action == TestAction::MOVE_X) {
      // 沿当前朝向前进/后退
      double target_dist = test.value;
      double actual_dx = (cur_x_ - start_x_) * std::cos(start_yaw_) +
                          (cur_y_ - start_y_) * std::sin(start_yaw_);
      double error = target_dist - actual_dx;

      if (std::abs(error) < test.tolerance || elapsed > test.timeout_sec) {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        cmd_pub_->publish(cmd);
        bool ok = std::abs(error) < test.tolerance;
        PrintResult(test, ok, target_dist, actual_dx);
        if (ok) passed_++;
        AdvanceTest(now);
      } else {
        double vx = std::clamp(kp_xy_ * error, -max_vx_, max_vx_);
        cmd.vx = static_cast<float>(vx);
        cmd.vy = 0.0f;
        cmd.wz = 0.0f;
        cmd_pub_->publish(cmd);
      }
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

  // 成员
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Publisher<DogNavCommand>::SharedPtr cmd_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  std::string odom_topic_{"/lio/odom"};
  std::string cmd_topic_{"/nav_cmd"};
  double pos_tol_{0.05};
  double yaw_tol_{0.087};
  double kp_xy_{0.5};
  double kp_yaw_{1.5};
  double max_vx_{0.3};
  double max_wz_{0.8};
  double test_delay_{1.0};

  // 位姿
  double cur_x_{0}, cur_y_{0}, cur_yaw_{0};
  double start_x_{0}, start_y_{0}, start_yaw_{0};
  bool odom_received_{false};
  bool initialized_{false};
  bool all_done_{false};
  bool in_delay_{true};
  double start_time_{0};
  double phase_start_time_{0};

  // 测试序列
  std::vector<TestItem> tests_;
  size_t test_idx_{0};
  size_t passed_{0};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TestNavMovement>());
  rclcpp::shutdown();
  return 0;
}