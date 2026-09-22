#pragma once

#include <onnxruntime/onnxruntime_cxx_api.h>
#include <urdf/model.h>
#include <atomic>
#include <controller_interface/controller_interface.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <hardware_interface/system_interface.hpp>
#include <hardware_interface/types/hardware_interface_type_values.hpp>
#include <map>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/joy.hpp>
#include <std_msgs/msg/float32.hpp>
#include <std_msgs/msg/float64.hpp>
#include <vector>

#include "rl_controllers/HybridJointHandle.h"
#include "rl_controllers/Types.h"
#include "std_msgs/msg/float64_multi_array.hpp"

#include <tf2_ros/transform_broadcaster.h>
#include <geometry_msgs/msg/transform_stamped.hpp>

namespace legged {

struct RLRobotCfg {
  struct ControlCfg {
    std::map<std::string, float> stiffness;
    std::map<std::string, float> damping;
    float actionScale;
    int decimation;
    float user_torque_limit;
    float user_power_limit;
    float cycle_time;
  };

  struct LegInitState {
    // default joint angles
    scalar_t idx01_left_hip_roll;
    scalar_t idx02_left_hip_yaw;
    scalar_t idx03_left_hip_pitch;
    scalar_t idx04_left_tarsus;
    scalar_t idx05_left_toe_pitch;
    scalar_t idx06_left_toe_roll;
    scalar_t idx07_right_hip_roll;
    scalar_t idx08_right_hip_yaw;
    scalar_t idx09_right_hip_pitch;
    scalar_t idx10_right_tarsus;
    scalar_t idx11_right_toe_pitch;
    scalar_t idx12_right_toe_roll;
  };
  struct ArmInitState {
    scalar_t idx13_left_arm_joint1;
    scalar_t idx14_left_arm_joint2;
    scalar_t idx15_left_arm_joint3;
    scalar_t idx16_left_arm_joint4;
    scalar_t idx17_left_arm_joint5;
    scalar_t idx18_left_arm_joint6;
    scalar_t idx19_left_arm_joint7;
    scalar_t idx20_right_arm_joint1;
    scalar_t idx21_right_arm_joint2;
    scalar_t idx22_right_arm_joint3;
    scalar_t idx23_right_arm_joint4;
    scalar_t idx24_right_arm_joint5;
    scalar_t idx25_right_arm_joint6;
    scalar_t idx26_right_arm_joint7;
  };

  struct ObsScales {
    scalar_t linVel;
    scalar_t angVel;
    scalar_t dofPos;
    scalar_t dofVel;
    scalar_t quat;
    scalar_t heightMeasurements;
  };

  bool encoder_nomalize;

  scalar_t clipActions;
  scalar_t clipObs;

  LegInitState initState;
  ArmInitState arminitState;
  ObsScales obsScales;
  ControlCfg controlCfg;
};

struct JointState {
  scalar_t idx01_left_hip_roll;
  scalar_t idx02_left_hip_yaw;
  scalar_t idx03_left_hip_pitch;
  scalar_t idx04_left_tarsus;
  scalar_t idx05_left_toe_pitch;
  scalar_t idx06_left_toe_roll;
  scalar_t idx07_right_hip_roll;
  scalar_t idx08_right_hip_yaw;
  scalar_t idx09_right_hip_pitch;
  scalar_t idx10_right_tarsus;
  scalar_t idx11_right_toe_pitch;
  scalar_t idx12_right_toe_roll;
  scalar_t idx13_left_arm_joint1;
  scalar_t idx14_left_arm_joint2;
  scalar_t idx15_left_arm_joint3;
  scalar_t idx16_left_arm_joint4;
  scalar_t idx17_left_arm_joint5;
  scalar_t idx18_left_arm_joint6;
  scalar_t idx19_left_arm_joint7;
  scalar_t idx20_right_arm_joint1;
  scalar_t idx21_right_arm_joint2;
  scalar_t idx22_right_arm_joint3;
  scalar_t idx23_right_arm_joint4;
  scalar_t idx24_right_arm_joint5;
  scalar_t idx25_right_arm_joint6;
  scalar_t idx26_right_arm_joint7;
};

struct JoyInfo {
  float axes[8];
  int buttons[11];
};

struct Proprioception {
  vector_t jointPos;
  vector_t jointVel;
  vector3_t baseAngVel;
  vector3_t baseEulerXyz;
  vector_t refPos;
  vector_t posDiff;
  vector3_t projectedGravity;
};

struct Command {
  std::atomic<scalar_t> x;
  std::atomic<scalar_t> y;
  std::atomic<scalar_t> yaw;
};

class RLControllerBase : public controller_interface::ControllerInterface {
 public:
  enum class Mode : uint8_t { DEFAULT,
                              LIE,
                              STAND,
                              WALK };

  RLControllerBase();
  controller_interface::InterfaceConfiguration command_interface_configuration() const override;
  controller_interface::InterfaceConfiguration state_interface_configuration() const override;
  controller_interface::return_type update(const rclcpp::Time& time, const rclcpp::Duration& period) override;
  controller_interface::CallbackReturn on_init() override;
  controller_interface::CallbackReturn on_configure(const rclcpp_lifecycle::State& previous_state) override;
  controller_interface::CallbackReturn on_activate(const rclcpp_lifecycle::State& previous_state) override;
  controller_interface::CallbackReturn on_deactivate(const rclcpp_lifecycle::State& previous_state) override;
  controller_interface::CallbackReturn on_cleanup(const rclcpp_lifecycle::State& previous_state) override;
  controller_interface::CallbackReturn on_error(const rclcpp_lifecycle::State& previous_state) override;
  controller_interface::CallbackReturn on_shutdown(const rclcpp_lifecycle::State& previous_state) override;

  virtual bool loadModel() { return false; };
  virtual bool loadRLCfg() { return false; };
  virtual void computeActions(){};
  virtual void computeObservation(){};

  virtual void handleDefaultMode();
  virtual void handleLieMode();
  virtual void handleStandMode();
  virtual void handleWalkMode(){};
  virtual void starting();
  void holdJointsAtZero(const std::vector<int>& indices);

  // Function to read CSV file and store data in a 2D vector
  std::vector<std::vector<double>> readCSV(const std::string& filePath);
  virtual void calcFrameBlend(double phase, int trajectory_num_frames, int& frame_idx0, int& frame_idx1, double& blend);

 protected:
  virtual void updateStateEstimation(const rclcpp::Time& time, const rclcpp::Duration& period);

  virtual void cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr msg);
  virtual void joyInfoCallback(const sensor_msgs::msg::Joy::SharedPtr msg);

  std::vector<std::string> joint_names_;
  std::vector<std::string> command_interface_types_;
  std::vector<std::string> state_interface_types_;

  bool new_msg_ = false;
  rclcpp::Time start_time_;

  /* sim !!!*/
  std::vector<std::unique_ptr<HybridJointHandle>> hybridJointHandles_;

  Mode mode_;
  int64_t loopCount_;
  Command command_;
  RLRobotCfg robotCfg_{};

  JointState standJointState{-0.0, 0.0, 0.0,
                              0.0, -0.0, 0.0,
                              -0., 0.0, 0.0,
                              0.0, -0.0, 0.0,
                              0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                              0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};

  JointState lieJointState{0.0, 0.0, -0.0,
                            0.0, -0.0, 0.0,
                            0.0, 0.0, -0.0,
                            0.0, -0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  JoyInfo joyInfo;
  std::atomic_bool emergency_stop{false};
  std::atomic_bool start_control{false};
  rclcpp::Time switchTime;
  std::vector<std::string> jointNames;

  vector_t rbdState_;
  vector_t measuredRbdState_;
  Proprioception propri_;
  sensor_msgs::msg::Imu imuData_;
  std::shared_ptr<tf2_ros::TransformBroadcaster> tfBroadcaster_;

  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmdVelSub_;
  rclcpp::Subscription<sensor_msgs::msg::Joy>::SharedPtr joyInfoSub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr emgStopSub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr startCtrlSub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr walkModeSub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr switchModeSub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr positionCtrlSub_;

  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr realJointPosPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr realJointVelPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr realJointTorquePublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr rlPlannedJointPosPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr rlPlannedJointVelPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr rlPlannedTorquePublisher_;

  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr realImuAngularVelPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr realImuLinearAccPublisher_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr realImuEulerXyzPulbisher_;
  rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr phasePublisher_;

  int actuatedDofNum_;
  vector_t currentPos_;
  vector_t currentVel_;
  vector_t Posdes_;
  double phase_;
  double current_time_;
  double cmd_norm_;

  double lie_kp_large_, lie_kd_large_, lie_kp_ankle_, lie_kd_ankle_,
      stance_kp_large_, stance_kd_large_, stance_kp_ankle_, stance_kd_ankle_;

  double fps = 120.0;
  double trajectory_duration;
  int trajectory_num_frames;
  // double phase_ = 1.0;
  int frame_idx0;
  int frame_idx1;
  double blend;
  std::vector<std::vector<double>> ref_dof_pos;
  std::vector<double> ref_dof_pos_low;
  std::vector<double> ref_dof_pos_high;
  std::vector<double> ref_dof_pos_cal;
  vector_t allJointPos_;
  int actionsSize_;
  std::vector<int> leg_joint_mapping = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
  std::vector<int> joint_mapping_fixed = {13, 14, 16, 17, 18, 20, 21, 23, 24, 25};
  std::vector<int> arm_joint_mapping = {12, 15, 19, 22};

  std::vector<size_t> non_zero_indices = {2, 3, 4, 8, 9, 10, 12, 13, 14, 15};

 private:
  // PD stand
  std::vector<scalar_t> currentJointAngles_;
  std::vector<scalar_t> initJointAngles_;
  vector_t standJointAngles_;
  vector_t lieJointAngles_;
  vector_t sitJointAngles_;

  scalar_t standPercent_;
  scalar_t standDuration_;
};

}  // namespace legged