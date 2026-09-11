/** 测试jjoint_states的功能对不对的上
 * @file print_joint.cpp
 * @brief 只发送 JointState 的简单节点
 *
 * 发布 /joint_states 话题，关节顺序:
 *   FL_hip, FL_thigh, FL_calf,
 *   FR_hip, FR_thigh, FR_calf,
 *   RL_hip, RL_thigh, RL_calf,
 *   RR_hip, RR_thigh, RR_calf
 *
 * position 数值由用户自行填写。
 */
#include <array>
#include <chrono>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

using namespace std::chrono_literals;

class PrintJointNode : public rclcpp::Node {
public:
  static constexpr std::size_t kNumDofs = 12;

  // FL, FR, RL, RR — 与 IsaacGym DOF 顺序一致
  static constexpr std::array<const char *, kNumDofs> kJointNames{
    "FL_hip", "FL_thigh", "FL_calf",    // FL → 0,1,2
    "FR_hip", "FR_thigh", "FR_calf",    // FR → 3,4,5
    "RL_hip", "RL_thigh", "RL_calf",    // RL → 6,7,8
    "RR_hip", "RR_thigh", "RR_calf"     // RR → 9,10,11
  };

  // 默认关节角度 (rad) — IsaacGym DOF 顺序: FL, FR, RL, RR
  static constexpr std::array<float, kNumDofs> kDefaultDofPos{
    -0.1f, -0.2f, -0.1f,     // FL
     0.1f,  0.2f,  0.1f,     // FR
     0.1f, -0.2f, -0.1f,     // RL
    -0.1f,  0.2f,  0.1f      // RR
  };

  PrintJointNode()
  : Node("print_joint_node")
  {
    pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);

    // TODO: 在这里分别调整 12 个关节的目标位置 (rad)
    //       初始值为 kDefaultDofPos，可以逐个修改
    positions_ = kDefaultDofPos;

    // 200Hz 定时发布 (5ms)
    timer_ = this->create_wall_timer(5ms, std::bind(&PrintJointNode::TimerCallback, this));

    RCLCPP_INFO(this->get_logger(), "print_joint_node started — publishing /joint_states at 200 Hz");
    RCLCPP_INFO(this->get_logger(),
      "Default positions (FL, FR, RL, RR):");
    RCLCPP_INFO(this->get_logger(),
      "  FL: hip=%.3f thigh=%.3f calf=%.3f",
      kDefaultDofPos[0], kDefaultDofPos[1], kDefaultDofPos[2]);
    RCLCPP_INFO(this->get_logger(),
      "  FR: hip=%.3f thigh=%.3f calf=%.3f",
      kDefaultDofPos[3], kDefaultDofPos[4], kDefaultDofPos[5]);
    RCLCPP_INFO(this->get_logger(),
      "  RL: hip=%.3f thigh=%.3f calf=%.3f",
      kDefaultDofPos[6], kDefaultDofPos[7], kDefaultDofPos[8]);
    RCLCPP_INFO(this->get_logger(),
      "  RR: hip=%.3f thigh=%.3f calf=%.3f",
      kDefaultDofPos[9], kDefaultDofPos[10], kDefaultDofPos[11]);
  }

private:
  void TimerCallback()
  {
    sensor_msgs::msg::JointState js_msg;
    js_msg.header.stamp = this->now();
    js_msg.header.frame_id = "base_link";

    js_msg.name.assign(kJointNames.begin(), kJointNames.end());
    js_msg.position.assign(positions_.begin(), positions_.end());

    pub_->publish(js_msg);
  }

  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  // TODO: 修改这里为你需要的关节角度 (rad)
  std::array<float, kNumDofs> positions_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<PrintJointNode>());
  rclcpp::shutdown();
  return 0;
}