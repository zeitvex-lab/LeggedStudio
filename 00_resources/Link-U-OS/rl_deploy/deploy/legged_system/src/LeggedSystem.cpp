#include "LeggedSystem.h"

#include <ifaddrs.h>
#include <net/if.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <ostream>
#include <vector>

#include "hardware_interface/sensor_interface.hpp"
#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "rclcpp/rclcpp.hpp"

#include "Utilities.h"

namespace legged {

namespace {
// names passed to /body_drive/leg_joint_command
constexpr std::array<const char*, 12> kLegJointNames = {
    "idx01_left_hip_roll",
    "idx02_left_hip_yaw",
    "idx03_left_hip_pitch",
    "idx04_left_tarsus",
    "idx05_01_left_toe_motorA",
    "idx06_01_left_toe_motorB",
    "idx07_right_hip_roll",
    "idx08_right_hip_yaw",
    "idx09_right_hip_pitch",
    "idx10_right_tarsus",
    "idx11_01_right_toe_motorA",
    "idx12_01_right_toe_motorB"};

// names passed to /body_drive/arm_joint_command
constexpr std::array<const char*, 14> kArmJointNames = {
    "idx13_left_arm_joint1",
    "idx14_left_arm_joint2",
    "idx15_left_arm_joint3",
    "idx16_left_arm_joint4",
    "idx17_left_arm_joint5",
    "idx18_01_left_wrist_rod_A_joint",
    "idx19_01_left_wrist_rod_B_joint",
    "idx20_right_arm_joint1",
    "idx21_right_arm_joint2",
    "idx22_right_arm_joint3",
    "idx23_right_arm_joint4",
    "idx24_right_arm_joint5",
    "idx25_01_right_wrist_rod_A_joint",
    "idx26_01_right_wrist_rod_B_joint"};
}  // namespace

template <int row_>
using Vector = Eigen::Matrix<double, row_, 1>;

Vector<26> m_q;  // motor position feedback (prior conversion)
Vector<26> m_v;  // motor velocity feedback (prior conversion)
Vector<26> m_t;  // motor torque feedback (prior conversion)

void LeggedSystemHardware::processClosedChainState() {
  Eigen::VectorXd motor_position = Eigen::VectorXd::Zero(12);
  Eigen::VectorXd motor_velocity = Eigen::VectorXd::Zero(12);
  Eigen::VectorXd motor_effort = Eigen::VectorXd::Zero(12);

  for (int leg_index = 0; leg_index < 2; leg_index++) {
    for (int i = 0; i < 6; i++) {
      motor_position[i + leg_index * 6] = SerialJointData_[i + leg_index * 6].pos_;
      motor_velocity[i + leg_index * 6] = SerialJointData_[i + leg_index * 6].vel_;
      motor_effort[i + leg_index * 6] = SerialJointData_[i + leg_index * 6].tau_;
    }

    Eigen::Vector2d ankle_motors_pos = motor_position.segment(4 + leg_index * 6, 2);
    Eigen::Vector2d ankle_motors_vel = motor_velocity.segment(4 + leg_index * 6, 2);
    Eigen::Vector2d ankle_motors_tau = motor_effort.segment(4 + leg_index * 6, 2);

    if (leg_index == 0) {
      double dd = closed_ankle_wrist_param_->ankle_d;
      double ll1 = closed_ankle_wrist_param_->ankle_l;
      double hh1 = closed_ankle_wrist_param_->ankle_h2;
      double hh2 = closed_ankle_wrist_param_->ankle_h1;
      ankle_state_convert->SetLinkLength(dd, ll1, hh1, hh2);

      double tmp = ankle_motors_pos[0];
      ankle_motors_pos[0] = ankle_motors_pos[1];
      ankle_motors_pos[1] = tmp;

      tmp = ankle_motors_vel[0];
      ankle_motors_vel[0] = ankle_motors_vel[1];
      ankle_motors_vel[1] = tmp;

      tmp = ankle_motors_tau[0];
      ankle_motors_tau[0] = ankle_motors_tau[1];
      ankle_motors_tau[1] = tmp;
    } else {
      double dd = closed_ankle_wrist_param_->ankle_d;
      double ll1 = closed_ankle_wrist_param_->ankle_l;
      double hh1 = closed_ankle_wrist_param_->ankle_h1;
      double hh2 = closed_ankle_wrist_param_->ankle_h2;
      ankle_state_convert->SetLinkLength(dd, ll1, hh1, hh2);
    }

    ankle_motors_pos[0] *= closed_ankle_wrist_param_->ankle_motor1_direction;
    ankle_motors_pos[1] *= closed_ankle_wrist_param_->ankle_motor2_direction;
    ankle_motors_vel[0] *= closed_ankle_wrist_param_->ankle_motor1_direction;
    ankle_motors_vel[1] *= closed_ankle_wrist_param_->ankle_motor2_direction;
    ankle_motors_tau[0] *= closed_ankle_wrist_param_->ankle_motor1_direction;
    ankle_motors_tau[1] *= closed_ankle_wrist_param_->ankle_motor2_direction;

    motor_position.segment(4 + leg_index * 6, 2) = ankle_state_convert->FK(ankle_motors_pos);

    if (std::abs(motor_position[4 + leg_index * 6]) >= closed_ankle_wrist_param_->ankle_pitch_limit) {
      motor_position[4 + leg_index * 6] =
          std::copysign(closed_ankle_wrist_param_->ankle_pitch_limit, motor_position[4 + leg_index * 6]);
    }
    if (std::abs(motor_position[5 + leg_index * 6]) >= closed_ankle_wrist_param_->ankle_roll_limit) {
      motor_position[5 + leg_index * 6] =
          std::copysign(closed_ankle_wrist_param_->ankle_roll_limit, motor_position[5 + leg_index * 6]);
    }

    motor_position[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_pitch_direction;
    motor_position[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_roll_direction;

    ankle_state_convert->UpdateJ1(ankle_motors_pos);

    motor_velocity.segment(4 + leg_index * 6, 2) = ankle_state_convert->DFK(ankle_motors_vel);
    motor_velocity[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_pitch_direction;
    motor_velocity[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_roll_direction;

    motor_effort.segment(4 + leg_index * 6, 2) = ankle_state_convert->FDyn(ankle_motors_tau);
    motor_effort[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_pitch_direction;
    motor_effort[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_roll_direction;

    for (int i = 0; i < 6; i++) {
      SerialJointData_[i + leg_index * 6].pos_ = motor_position[i + leg_index * 6];
      SerialJointData_[i + leg_index * 6].vel_ = motor_velocity[i + leg_index * 6];
      SerialJointData_[i + leg_index * 6].tau_ = motor_effort[i + leg_index * 6];
    }
  }
}

void LeggedSystemHardware::processClosedChainCommands() {
  Eigen::VectorXd des_motor_position = Eigen::VectorXd::Zero(12);
  Eigen::VectorXd des_motor_velocity = Eigen::VectorXd::Zero(12);
  Eigen::VectorXd des_motor_effort = Eigen::VectorXd::Zero(12);
  Eigen::VectorXd motor_position_here = Eigen::VectorXd::Zero(12);

  for (int leg_index = 0; leg_index < 2; leg_index++) {
    for (int i = 0; i < 6; i++) {
      des_motor_position[i + leg_index * 6] = writePosDesArray_[i + leg_index * 6];
      des_motor_velocity[i + leg_index * 6] = writeVelDesArray_[i + leg_index * 6];
      des_motor_effort[i + leg_index * 6] = writeFFArray_[i + leg_index * 6];
      motor_position_here[i + leg_index * 6] = readPosArrayBeforeConversion_[i + leg_index * 6];
    }

    Eigen::Vector2d ankle_motors_pos_here = motor_position_here.segment(4 + leg_index * 6, 2);
    Eigen::Vector2d des_pr = des_motor_position.segment(4 + leg_index * 6, 2);
    Eigen::Vector2d des_vel_pr = des_motor_velocity.segment(4 + leg_index * 6, 2);
    Eigen::Vector2d des_tau_pr = des_motor_effort.segment(4 + leg_index * 6, 2);

    des_pr[0] *= closed_ankle_wrist_param_->ankle_pitch_direction;
    des_pr[1] *= closed_ankle_wrist_param_->ankle_roll_direction;
    des_vel_pr[0] *= closed_ankle_wrist_param_->ankle_pitch_direction;
    des_vel_pr[1] *= closed_ankle_wrist_param_->ankle_roll_direction;
    des_tau_pr[0] *= closed_ankle_wrist_param_->ankle_pitch_direction;
    des_tau_pr[1] *= closed_ankle_wrist_param_->ankle_roll_direction;

    if (leg_index == 0) {
      double dd = closed_ankle_wrist_param_->ankle_d;
      double ll1 = closed_ankle_wrist_param_->ankle_l;
      double hh1 = closed_ankle_wrist_param_->ankle_h2;
      double hh2 = closed_ankle_wrist_param_->ankle_h1;
      ankle_command_convert->SetLinkLength(dd, ll1, hh1, hh2);

      des_motor_position.segment(4 + leg_index * 6, 2) = ankle_command_convert->IK(des_pr);

      if (std::abs(des_motor_position[4 + leg_index * 6]) > closed_ankle_wrist_param_->ankle_actuator_pos_limit) {
        des_motor_position[4 + leg_index * 6] =
            std::copysign(closed_ankle_wrist_param_->ankle_actuator_pos_limit, des_motor_position[4 + leg_index * 6]);
      }
      if (std::abs(des_motor_position[5 + leg_index * 6]) > closed_ankle_wrist_param_->ankle_actuator_pos_limit) {
        des_motor_position[5 + leg_index * 6] =
            std::copysign(closed_ankle_wrist_param_->ankle_actuator_pos_limit, des_motor_position[5 + leg_index * 6]);
      }

      double tmp = des_motor_position[4 + leg_index * 6];
      des_motor_position[4 + leg_index * 6] = des_motor_position[5 + leg_index * 6];
      des_motor_position[5 + leg_index * 6] = tmp;
      des_motor_position[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor2_direction;
      des_motor_position[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor1_direction;

      auto cur_mc = ankle_motors_pos_here;
      tmp = closed_ankle_wrist_param_->ankle_motor2_direction * cur_mc[0];
      cur_mc[0] = closed_ankle_wrist_param_->ankle_motor1_direction * cur_mc[1];
      cur_mc[1] = tmp;
      ankle_command_convert->UpdateJ1(cur_mc);

      des_motor_velocity.segment(4 + leg_index * 6, 2) = ankle_command_convert->DIK(des_vel_pr);
      des_motor_effort.segment(4 + leg_index * 6, 2) = ankle_command_convert->IDyn(des_tau_pr);

      tmp = des_motor_velocity[4 + leg_index * 6];
      des_motor_velocity[4 + leg_index * 6] = des_motor_velocity[5 + leg_index * 6];
      des_motor_velocity[5 + leg_index * 6] = tmp;
      des_motor_velocity[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor2_direction;
      des_motor_velocity[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor1_direction;

      tmp = des_motor_effort[4 + leg_index * 6];
      des_motor_effort[4 + leg_index * 6] = des_motor_effort[5 + leg_index * 6];
      des_motor_effort[5 + leg_index * 6] = tmp;
      des_motor_effort[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor2_direction;
      des_motor_effort[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor1_direction;
    } else {
      double dd = closed_ankle_wrist_param_->ankle_d;
      double ll1 = closed_ankle_wrist_param_->ankle_l;
      double hh1 = closed_ankle_wrist_param_->ankle_h1;
      double hh2 = closed_ankle_wrist_param_->ankle_h2;
      ankle_command_convert->SetLinkLength(dd, ll1, hh1, hh2);

      des_motor_position.segment(4 + leg_index * 6, 2) = ankle_command_convert->IK(des_pr);

      if (std::abs(des_motor_position[4 + leg_index * 6]) > closed_ankle_wrist_param_->ankle_actuator_pos_limit) {
        des_motor_position[4 + leg_index * 6] =
            std::copysign(closed_ankle_wrist_param_->ankle_actuator_pos_limit, des_motor_position[4 + leg_index * 6]);
      }
      if (std::abs(des_motor_position[5 + leg_index * 6]) > closed_ankle_wrist_param_->ankle_actuator_pos_limit) {
        des_motor_position[5 + leg_index * 6] =
            std::copysign(closed_ankle_wrist_param_->ankle_actuator_pos_limit, des_motor_position[5 + leg_index * 6]);
      }
      des_motor_position[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor1_direction;
      des_motor_position[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor2_direction;

      auto cur_mc = ankle_motors_pos_here;
      cur_mc[0] *= closed_ankle_wrist_param_->ankle_motor1_direction;
      cur_mc[1] *= closed_ankle_wrist_param_->ankle_motor2_direction;
      ankle_command_convert->UpdateJ1(cur_mc);

      des_motor_velocity.segment(4 + leg_index * 6, 2) = ankle_command_convert->DIK(des_vel_pr);
      des_motor_velocity[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor1_direction;
      des_motor_velocity[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor2_direction;

      des_motor_effort.segment(4 + leg_index * 6, 2) = ankle_command_convert->IDyn(des_tau_pr);
      des_motor_effort[4 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor1_direction;
      des_motor_effort[5 + leg_index * 6] *= closed_ankle_wrist_param_->ankle_motor2_direction;
    }

    for (int i = 0; i < 6; i++) {
      writeFFArray_[i + leg_index * 6] = des_motor_effort[i + leg_index * 6];
    }
  }
}
hardware_interface::CallbackReturn LeggedSystemHardware::on_init(const hardware_interface::HardwareInfo& info) {
  // Urdf not found in hardware info, error
  if (hardware_interface::SystemInterface::on_init(info) != hardware_interface::CallbackReturn::SUCCESS) {
    return hardware_interface::CallbackReturn::ERROR;
  }

  for (auto joint : info.joints) {
    RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "Found %s successfully!", joint.name.c_str());
  }

  motor_pos_feedback_.setZero();
  motor_vel_feedback_.setZero();
  motor_tau_feedback_.setZero();

  read_Ankle_Space_Pos.setZero();
  read_Ankle_Space_Vel.setZero();
  read_Ankle_Space_Torque.setZero();

  motor_cmd_torque.setZero();
  legJointCommand_.joints.resize(12);
  armJointCommand_.joints.resize(14);
  // set joint name for leg and arm commands

  for (size_t i = 0; i < kLegJointNames.size(); i++) {
    legJointCommand_.joints[i].name = kLegJointNames[i];
  }
  for (size_t i = 0; i < kArmJointNames.size(); i++) {
    armJointCommand_.joints[i].name = kArmJointNames[i];
  }

  return hardware_interface::CallbackReturn::SUCCESS;
}

std::vector<hardware_interface::StateInterface> LeggedSystemHardware::export_state_interfaces() {
  std::vector<hardware_interface::StateInterface> state_interfaces;
  // binding state interfaces to SerialJointData_
  for (size_t i = 0; i < info_.joints.size(); i++) {
    state_interfaces.emplace_back(hardware_interface::StateInterface(
        info_.joints[i].name, hardware_interface::HW_IF_POSITION, &SerialJointData_[i].pos_));
    state_interfaces.emplace_back(hardware_interface::StateInterface(
        info_.joints[i].name, hardware_interface::HW_IF_VELOCITY, &SerialJointData_[i].vel_));
    state_interfaces.emplace_back(hardware_interface::StateInterface(
        info_.joints[i].name, hardware_interface::HW_IF_EFFORT, &SerialJointData_[i].tau_));
  }

  // ===== IMU state interfaces =====
  state_interfaces.emplace_back(
    "imu", "orientation.x", &imu_orientation_[0]);
  state_interfaces.emplace_back(
    "imu", "orientation.y", &imu_orientation_[1]);
  state_interfaces.emplace_back(
    "imu", "orientation.z", &imu_orientation_[2]);
  state_interfaces.emplace_back(
    "imu", "orientation.w", &imu_orientation_[3]);

  state_interfaces.emplace_back(
    "imu", "angular_velocity.x", &imu_angular_velocity_[0]);
  state_interfaces.emplace_back(
    "imu", "angular_velocity.y", &imu_angular_velocity_[1]);
  state_interfaces.emplace_back(
    "imu", "angular_velocity.z", &imu_angular_velocity_[2]);

  state_interfaces.emplace_back(
    "imu", "linear_acceleration.x", &imu_linear_acceleration_[0]);
  state_interfaces.emplace_back(
    "imu", "linear_acceleration.y", &imu_linear_acceleration_[1]);
  state_interfaces.emplace_back(
    "imu", "linear_acceleration.z", &imu_linear_acceleration_[2]);

  return state_interfaces;
}

std::vector<hardware_interface::CommandInterface> LeggedSystemHardware::export_command_interfaces() {
  std::vector<hardware_interface::CommandInterface> command_interfaces;
  // binding command interfaces to SerialJointData_
  for (size_t i = 0; i < info_.joints.size(); i++) {
    command_interfaces.emplace_back(hardware_interface::CommandInterface(
        info_.joints[i].name, hardware_interface::HW_IF_POSITION, &SerialJointData_[i].posDes_));
    command_interfaces.emplace_back(hardware_interface::CommandInterface(
        info_.joints[i].name, hardware_interface::HW_IF_VELOCITY, &SerialJointData_[i].velDes_));
    command_interfaces.emplace_back(hardware_interface::CommandInterface(
        info_.joints[i].name, hardware_interface::HW_IF_EFFORT, &SerialJointData_[i].ff_));
    command_interfaces.emplace_back(
        hardware_interface::CommandInterface(info_.joints[i].name, "Kp", &SerialJointData_[i].kp_));
    command_interfaces.emplace_back(
        hardware_interface::CommandInterface(info_.joints[i].name, "Kd", &SerialJointData_[i].kd_));

    RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "%s", command_interfaces[i].get_name().c_str());
  }

  return command_interfaces;
}

hardware_interface::CallbackReturn LeggedSystemHardware::on_activate(
    const rclcpp_lifecycle::State& /*previous_state*/) {
  RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "Activating ...please wait...");

  this->node_ = std::make_shared<rclcpp::Node>("hardware_node");

  this->node_->declare_parameter<std::string>("aimrt_cfg_path");
  auto aimrt_cfg_path = this->node_->get_parameter("aimrt_cfg_path").as_string();
  RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "aimrt_cfg_path: %s", aimrt_cfg_path.c_str());
  options_.cfg_file_path = aimrt_cfg_path;
  
  motorPosPublisher_ = this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/motor_pos", 1);
  motorVelPublisher_ = this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/motor_vel", 1);
  motorTorquePublisher_ =
      this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/motor_torque", 1);
  readAnkleSpacePosPublisher_ =
      this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/read_ankle_space_pos", 1);
  readAnkleSpaceVelPublisher_ =
      this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/read_ankle_space_vel", 1);
  readAnkleSpaceTorquePublisher_ =
      this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/read_ankle_space_torque", 1);
  motorCmdTorquePublisher_ =
      this->node_->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/motor_cmd_torque", 1);

  tfBroadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(this->node_);

  executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
  executor_->add_node(this->node_);
  executor_thread_ = std::thread([this]() { executor_->spin(); });

  aimrtInit();

  return hardware_interface::CallbackReturn::SUCCESS;
}

void LeggedSystemHardware::aimrtInit(){
  // Initialize
  if (!std::filesystem::exists(options_.cfg_file_path)) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"),"Config file path does not exist: %s",options_.cfg_file_path.c_str());
    std::exit(EXIT_FAILURE);
  }

  if (!std::filesystem::is_regular_file(options_.cfg_file_path)) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"),"Config path exists but is not a regular file: %s",options_.cfg_file_path.c_str());
    std::exit(EXIT_FAILURE);
  }
  
  try {
    RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "Initializing AimRTCore, config file: %s", options_.cfg_file_path.c_str());
    core_.Initialize(options_);
    RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "AimRTCore initialized successfully");
  } catch (const std::exception& e) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "AimRTCore initialization error: %s", e.what());
    exit(-1);
  }

  // Create Module
  aimrt::CoreRef module_handle_(core_.GetModuleManager().CreateModule("LeggedSystemModule"));

  // Create Publishers
  aimrtLegCmdPublisher_= module_handle_.GetChannelHandle().GetPublisher("/body_drive/leg_joint_command");
  if (!aimrtLegCmdPublisher_) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Get publisher for topic '/body_drive/leg_joint_command' failed");
    throw std::runtime_error("Get publisher for topic '/body_drive/leg_joint_command' failed");
  }

  aimrtArmCmdPublisher_= module_handle_.GetChannelHandle().GetPublisher("/body_drive/arm_joint_command");
  if (!aimrtArmCmdPublisher_) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Get publisher for topic '/body_drive/arm_joint_command' failed");
    throw std::runtime_error("Get publisher for topic '/body_drive/arm_joint_command' failed");
  }

  bool ret = aimrt::channel::RegisterPublishType<joint_msgs::msg::JointCommand>(aimrtLegCmdPublisher_);
  if (!ret) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Register publish type for aimrtLegCmdPublisher_ (topic: /body_drive/leg_joint_command) failed");
    throw std::runtime_error("Register publish type for aimrtLegCmdPublisher_ failed");
  }
              
  ret = aimrt::channel::RegisterPublishType<joint_msgs::msg::JointCommand>(aimrtArmCmdPublisher_);
  if (!ret) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Register publish type for aimrtArmCmdPublisher_ (topic: /body_drive/arm_joint_command) failed");
    throw std::runtime_error("Register publish type for aimrtArmCmdPublisher_ failed");
  }
  
  aimrtLegCmdPublisherProxy_ = std::make_unique<aimrt::channel::PublisherProxy<joint_msgs::msg::JointCommand>>(aimrtLegCmdPublisher_);
  aimrtArmCmdPublisherProxy_ = std::make_unique<aimrt::channel::PublisherProxy<joint_msgs::msg::JointCommand>>(aimrtArmCmdPublisher_);
  
  // Create Subscribers
  aimrtMotorStateSubscriber_= module_handle_.GetChannelHandle().GetSubscriber("/body_drive/leg_joint_state");
  if (!aimrtMotorStateSubscriber_) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Get subscriber for topic '/body_drive/leg_joint_state' failed");
    throw std::runtime_error("Get subscriber for topic '/body_drive/leg_joint_state' failed");
  }

  ret = aimrt::channel::Subscribe<joint_msgs::msg::JointState>(
    aimrtMotorStateSubscriber_,
    std::bind(&LeggedSystemHardware::legStateCallback, this, std::placeholders::_1));
  if (!ret) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Subscribe to topic '/body_drive/leg_joint_state' failed");
    throw std::runtime_error("Subscribe to topic '/body_drive/leg_joint_state' failed");
  }
              
  aimrtArmMotorStateSubscriber_= module_handle_.GetChannelHandle().GetSubscriber("/body_drive/arm_joint_state");
  if (!aimrtArmMotorStateSubscriber_) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Get subscriber for topic '/body_drive/arm_joint_state' failed");
    throw std::runtime_error("Get subscriber for topic '/body_drive/arm_joint_state' failed");
  }

  ret = aimrt::channel::Subscribe<joint_msgs::msg::JointState>(
    aimrtArmMotorStateSubscriber_,
    std::bind(&LeggedSystemHardware::armStateCallback, this, std::placeholders::_1));
  if (!ret) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Subscribe to topic '/body_drive/arm_joint_state' failed");
    throw std::runtime_error("Subscribe to topic '/body_drive/arm_joint_state' failed");
  }

  aimrtImuSubscriber_= module_handle_.GetChannelHandle().GetSubscriber("/body_drive/imu/data");
  if (!aimrtImuSubscriber_) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Get subscriber for topic '/body_drive/imu/data' failed");
    throw std::runtime_error("Get subscriber for topic '/body_drive/imu/data' failed");
  }

  ret = aimrt::channel::Subscribe<sensor_msgs::msg::Imu>(
    aimrtImuSubscriber_,
    std::bind(&LeggedSystemHardware::imuCallback, this, std::placeholders::_1));
  if (!ret) {
    RCLCPP_ERROR(rclcpp::get_logger("LeggedSystemHardware"), "Subscribe to topic '/body_drive/imu/data' failed");
    throw std::runtime_error("Subscribe to topic '/body_drive/imu/data' failed");
  }
  
  //start Async
  fu_ = core_.AsyncStart();
}

hardware_interface::CallbackReturn LeggedSystemHardware::on_deactivate(
    const rclcpp_lifecycle::State& /*previous_state*/) {
  RCLCPP_INFO(rclcpp::get_logger("LeggedSystemHardware"), "Deactivating ...please wait...");

  if (executor_thread_.joinable()) {
    executor_->cancel();
    executor_thread_.join();
  }
  
  // Shutdown AimRTCore
  core_.Shutdown();
  fu_.wait();
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::return_type LeggedSystemHardware::read(const rclcpp::Time& /*time*/,
                                                           [[maybe_unused]] const rclcpp::Duration& period) {
  for (int i = 0; i < 26; i++) {
    SerialJointData_[i].pos_ = bodyDriveJointData_[i].pos_ * direction_motor[i] + base_motor[i];
    SerialJointData_[i].vel_ = bodyDriveJointData_[i].vel_ * direction_motor[i];
    SerialJointData_[i].tau_ = bodyDriveJointData_[i].tau_ * direction_motor[i];
  }

  for (int i = 0; i < 26; i++) {
    motor_pos_feedback_(i) = SerialJointData_[i].pos_;
    motor_vel_feedback_(i) = SerialJointData_[i].vel_;
    motor_tau_feedback_(i) = SerialJointData_[i].tau_;

    readPosArrayBeforeConversion_[i] = SerialJointData_[i].pos_;
    readVelArrayBeforeConversion_[i] = SerialJointData_[i].vel_;
    readTauArrayBeforeConversion_[i] = SerialJointData_[i].tau_;
  }

  motorPosPublisher_->publish(createFloat64MultiArrayFromVector(motor_pos_feedback_));
  motorVelPublisher_->publish(createFloat64MultiArrayFromVector(motor_vel_feedback_));
  motorTorquePublisher_->publish(createFloat64MultiArrayFromVector(motor_tau_feedback_));

  m_q = Eigen::Map<Eigen::Matrix<double, 26, 1>>(readPosArrayBeforeConversion_);
  m_v = Eigen::Map<Eigen::Matrix<double, 26, 1>>(readVelArrayBeforeConversion_);
  m_t = Eigen::Map<Eigen::Matrix<double, 26, 1>>(readTauArrayBeforeConversion_);

  processClosedChainState();

  for (int i = 0; i < 26; ++i) {
    readPosArrayAfterConversion_[i] = SerialJointData_[i].pos_;
    readVelArrayAfterConversion_[i] = SerialJointData_[i].vel_;
    readTauArrayAfterConversion_[i] = SerialJointData_[i].tau_;

    read_Ankle_Space_Pos(i) = SerialJointData_[i].pos_;
    read_Ankle_Space_Vel(i) = SerialJointData_[i].vel_;
    read_Ankle_Space_Torque(i) = SerialJointData_[i].tau_;
  }

  readAnkleSpacePosPublisher_->publish(createFloat64MultiArrayFromVector(read_Ankle_Space_Pos));
  readAnkleSpaceVelPublisher_->publish(createFloat64MultiArrayFromVector(read_Ankle_Space_Vel));
  readAnkleSpaceTorquePublisher_->publish(createFloat64MultiArrayFromVector(read_Ankle_Space_Torque));

  // for safety
  for (int i = 0; i < 26; ++i) {
    SerialJointData_[i].velDes_ = 0;
    SerialJointData_[i].ff_ = 0;
    SerialJointData_[i].kp_ = 0;
    SerialJointData_[i].kd_ = 1.5;
  }

  imu_orientation_[0] = bodyDriveIMU_.orientation.x;
  imu_orientation_[1] = bodyDriveIMU_.orientation.y;
  imu_orientation_[2] = bodyDriveIMU_.orientation.z;
  imu_orientation_[3] = bodyDriveIMU_.orientation.w;

  imu_angular_velocity_[0] = bodyDriveIMU_.angular_velocity.x;
  imu_angular_velocity_[1] = bodyDriveIMU_.angular_velocity.y;
  imu_angular_velocity_[2] = bodyDriveIMU_.angular_velocity.z;

  imu_linear_acceleration_[0] = bodyDriveIMU_.linear_acceleration.x;
  imu_linear_acceleration_[1] = bodyDriveIMU_.linear_acceleration.y;
  imu_linear_acceleration_[2] = bodyDriveIMU_.linear_acceleration.z;

  return hardware_interface::return_type::OK;
}

hardware_interface::return_type LeggedSystemHardware::write(const rclcpp::Time& /*time*/,
                                                            [[maybe_unused]] const rclcpp::Duration& period) {
  if (useAnkleTorque_) {
    for (int i = 0; i < 26; ++i) {
      writePosDesArray_[i] = SerialJointData_[i].posDes_;
      writeVelDesArray_[i] = SerialJointData_[i].velDes_;
      writeFFArray_[i] = SerialJointData_[i].kp_ * (SerialJointData_[i].posDes_ - SerialJointData_[i].pos_) +
                         SerialJointData_[i].kd_ * (SerialJointData_[i].velDes_ - SerialJointData_[i].vel_);
      writeKpArray_[i] = SerialJointData_[i].kp_;
      writeKdArray_[i] = SerialJointData_[i].kd_;
    }
  } else {
    for (int i = 0; i < 26; ++i) {
      writePosDesArray_[i] = SerialJointData_[i].posDes_;
      writeVelDesArray_[i] = SerialJointData_[i].velDes_;
      writeFFArray_[i] = SerialJointData_[i].ff_;
      writeKpArray_[i] = SerialJointData_[i].kp_;
      writeKdArray_[i] = SerialJointData_[i].kd_;
    }
  }
  processClosedChainCommands();
  for (int leg_index = 0; leg_index < 2; leg_index++) {
    for (int i = 0; i < 6; i++) {
      if (i == 4 || i == 5) {
        legJointCommand_.joints[i + 6 * leg_index].position = 0.;
        legJointCommand_.joints[i + 6 * leg_index].velocity = 0.;
        legJointCommand_.joints[i + 6 * leg_index].effort = writeFFArray_[i + 6 * leg_index];
        legJointCommand_.joints[i + 6 * leg_index].stiffness = 0.;
        legJointCommand_.joints[i + 6 * leg_index].damping = 0.;
      } else {
        legJointCommand_.joints[i + 6 * leg_index].position = writePosDesArray_[i + 6 * leg_index];
        legJointCommand_.joints[i + 6 * leg_index].velocity = writeVelDesArray_[i + 6 * leg_index];
        legJointCommand_.joints[i + 6 * leg_index].effort = 0.;
        legJointCommand_.joints[i + 6 * leg_index].stiffness = writeKpArray_[i + 6 * leg_index];
        legJointCommand_.joints[i + 6 * leg_index].damping = writeKdArray_[i + 6 * leg_index];
      }
    }
  }

  for (int arm_index = 0; arm_index < 2; arm_index++) {
    for (int i = 0; i < 7; i++) {
      armJointCommand_.joints[i + 7 * arm_index].position =
          writePosDesArray_[i + 7 * arm_index + 12] - base_motor[i + 7 * arm_index + 12];
      armJointCommand_.joints[i + 7 * arm_index].velocity = 0.;
      armJointCommand_.joints[i + 7 * arm_index].effort = 0.;
      armJointCommand_.joints[i + 7 * arm_index].stiffness = 0.;
      armJointCommand_.joints[i + 7 * arm_index].damping = 0.;
    }
  }

  aimrtLegCmdPublisherProxy_->Publish(legJointCommand_);

  if (!firstReceiveArmState) {
    aimrtArmCmdPublisherProxy_->Publish(armJointCommand_);
  }

  if (useAnkleTorque_) {
    for (int i = 0; i < 12; ++i) {
      if (i == 4 || i == 5 || i == 10 || i == 11) {
        motor_cmd_torque(i) = writeFFArray_[i];
      } else {
        motor_cmd_torque(i) = writeKpArray_[i] * (writePosDesArray_[i] - readPosArrayBeforeConversion_[i]) *
                              writeKdArray_[i] * (writeVelDesArray_[i] - readVelArrayBeforeConversion_[i]);
      }
    }
  }

  else {
    for (int i = 0; i < 12; ++i) {
      motor_cmd_torque(i) = writeKpArray_[i] * (writePosDesArray_[i] - readPosArrayBeforeConversion_[i]) *
                            writeKdArray_[i] * (writeVelDesArray_[i] - readVelArrayBeforeConversion_[i]);
    }
  }

  motorCmdTorquePublisher_->publish(createFloat64MultiArrayFromVector(motor_cmd_torque));

  return hardware_interface::return_type::OK;
}

}  // namespace legged

#include "pluginlib/class_list_macros.hpp"
PLUGINLIB_EXPORT_CLASS(legged::LeggedSystemHardware, hardware_interface::SystemInterface)
