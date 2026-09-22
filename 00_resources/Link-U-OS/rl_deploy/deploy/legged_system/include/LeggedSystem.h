#pragma once

#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <Eigen/Dense>

#include "hardware_interface/handle.hpp"
#include "hardware_interface/hardware_info.hpp"
#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "rclcpp/clock.hpp"
#include "rclcpp/duration.hpp"
#include "rclcpp/macros.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp/time.hpp"
#include "rclcpp_lifecycle/node_interfaces/lifecycle_node_interface.hpp"
#include "rclcpp_lifecycle/state.hpp"

#include <geometry_msgs/msg/transform_stamped.hpp>
#include <tf2_ros/transform_broadcaster.h>

#include "Types.h"
#include "realtime_tools/realtime_box.hpp"
#include "realtime_tools/realtime_buffer.hpp"
#include "realtime_tools/realtime_publisher.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"

#include "joint_msgs/msg/detail/joint_command__struct.hpp"
#include "joint_msgs/msg/detail/joint_state__struct.hpp"
#include "joint_msgs/msg/joint_command.hpp"
#include "joint_msgs/msg/joint_state.hpp"

#include "ClosedAnkleWristParam.h"
#include "LoopAnkleAnalyticalSolver.h"

#include "aimrt_module_cpp_interface/core.h"
#include "aimrt_module_ros2_interface/channel/ros2_channel.h"
#include "core/aimrt_core.h"

namespace legged {

struct MotorData {
  double pos_, vel_, tau_;                 // state
  double posDes_, velDes_, kp_, kd_, ff_;  // command
};
struct MotorDataFloat {
  float pos_, vel_, tau_;                 // state
  float posDes_, velDes_, kp_, kd_, ff_;  // command
};
using Clock = std::chrono::high_resolution_clock;  // high-precision clock
using Duration = std::chrono::duration<double>;    // double-based duration

class LeggedSystemHardware : public hardware_interface::SystemInterface {
 public:
  hardware_interface::CallbackReturn on_init(const hardware_interface::HardwareInfo &info) override;
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;
  hardware_interface::CallbackReturn on_activate(const rclcpp_lifecycle::State &previous_state) override;
  hardware_interface::CallbackReturn on_deactivate(const rclcpp_lifecycle::State &previous_state) override;
  hardware_interface::return_type read(const rclcpp::Time &time, const rclcpp::Duration &period) override;
  hardware_interface::return_type write(const rclcpp::Time &time, const rclcpp::Duration &period) override;
  


 private:
  void processClosedChainState();
  void processClosedChainCommands();

  void aimrtInit();

  void imuCallback(const std::shared_ptr<const sensor_msgs::msg::Imu>& msg) {
    bodyDriveIMU_ = *msg;
    publishImuTransform(bodyDriveIMU_);
  }

  void legStateCallback(const std::shared_ptr<const joint_msgs::msg::JointState>& msg) {
    for (int i = 0; i < 12; i++) {
      bodyDriveJointData_[i].pos_ = msg->joints[i].position;
      bodyDriveJointData_[i].vel_ = msg->joints[i].velocity;
      bodyDriveJointData_[i].tau_ = msg->joints[i].effort;
    }
  }

  void armStateCallback(const std::shared_ptr<const joint_msgs::msg::JointState>& msg) {
    for (int i = 12; i < 26; i++) {
      bodyDriveJointData_[i].pos_ = msg->joints[i - 12].position;
      bodyDriveJointData_[i].vel_ = msg->joints[i - 12].velocity;
      bodyDriveJointData_[i].tau_ = msg->joints[i - 12].effort;
    }
    firstReceiveArmState = false;
  }

  void publishImuTransform(const sensor_msgs::msg::Imu &imu_msg) {
    geometry_msgs::msg::TransformStamped transformStamped;

    transformStamped.header.stamp = node_->now();;
    transformStamped.header.frame_id = "base_link";   
    transformStamped.child_frame_id = "world_frame";  

    transformStamped.transform.translation.x = 0.0;
    transformStamped.transform.translation.y = 0.0;
    transformStamped.transform.translation.z = 0.0;

    transformStamped.transform.rotation = imu_msg.orientation;

    tfBroadcaster_->sendTransform(transformStamped);
  }

  MotorData SerialJointData_[26]{};
  MotorDataFloat bodyDriveJointData_[26]{};
  sensor_msgs::msg::Imu bodyDriveIMU_;
  double imu_orientation_[4];     
  double imu_angular_velocity_[3];
  double imu_linear_acceleration_[3];

  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr motorPosPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr motorVelPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr motorTorquePublisher_;

  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr readAnkleSpacePosPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr readAnkleSpaceVelPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr readAnkleSpaceTorquePublisher_;

  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr motorCmdTorquePublisher_;

  std::shared_ptr<tf2_ros::TransformBroadcaster> tfBroadcaster_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread executor_thread_;

  aimrt::runtime::core::AimRTCore core_;
  aimrt::runtime::core::AimRTCore::Options options_;
  aimrt::CoreRef module_handle_;
  aimrt::channel::SubscriberRef aimrtMotorStateSubscriber_;
  aimrt::channel::SubscriberRef aimrtArmMotorStateSubscriber_;
  aimrt::channel::SubscriberRef aimrtImuSubscriber_;
  aimrt::channel::PublisherRef aimrtLegCmdPublisher_;
  aimrt::channel::PublisherRef aimrtArmCmdPublisher_;
  std::unique_ptr<aimrt::channel::PublisherProxy<joint_msgs::msg::JointCommand>> aimrtLegCmdPublisherProxy_;
  std::unique_ptr<aimrt::channel::PublisherProxy<joint_msgs::msg::JointCommand>> aimrtArmCmdPublisherProxy_;
  std::future<void> fu_;

  std::shared_ptr<rclcpp::Node> node_;

  std::thread loopThread_;
  std::atomic_bool loopRunning_{true};
  std::mutex motor_mtx_;

  joint_msgs::msg::JointCommand legJointCommand_;
  joint_msgs::msg::JointCommand armJointCommand_;

  double loopHz_{1000};

  std::vector<int> direction_motor{1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                                   1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};

  float base_motor[26] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                          -1.35, 0, 0, -1.57, 0, 0, 0, 1.35, 0, 0, -1.57, 0, 0};

  bool useAnkleTorque_{true};
  bool firstReceiveArmState{true};

  double readPosArrayBeforeConversion_[26]{};
  double readVelArrayBeforeConversion_[26]{};
  double readTauArrayBeforeConversion_[26]{};
  double readPosArrayAfterConversion_[26]{};
  double readVelArrayAfterConversion_[26]{};
  double readTauArrayAfterConversion_[26]{};

  double writePosDesArray_[26]{};
  double writeVelDesArray_[26]{};
  double writeFFArray_[26]{};
  double writeKpArray_[26]{};
  double writeKdArray_[26]{};

  double motorFFArray_[26]{};

  vector_t motor_pos_feedback_{26};
  vector_t motor_vel_feedback_{26};
  vector_t motor_tau_feedback_{26};

  vector_t read_Ankle_Space_Pos{26};
  vector_t read_Ankle_Space_Vel{26};
  vector_t read_Ankle_Space_Torque{26};

  vector_t motor_cmd_torque{26};

  vector_t joint_power_real_{26};
  vector_t power_sum_real_{1};

  std::unique_ptr<zy::LoopAnkleAnalyticalSolver> ankle_state_convert =
      std::make_unique<zy::LoopAnkleAnalyticalSolver>();
  std::unique_ptr<zy::LoopAnkleAnalyticalSolver> ankle_command_convert =
      std::make_unique<zy::LoopAnkleAnalyticalSolver>();
  std::unique_ptr<zy::ClosedAnkleWristParam> closed_ankle_wrist_param_ =
      std::make_unique<zy::ClosedAnkleWristParam>();
};

}  // namespace legged