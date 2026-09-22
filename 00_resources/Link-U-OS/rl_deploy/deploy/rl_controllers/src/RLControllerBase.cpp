#include <rl_controllers/RLControllerBase.h>
#include <rl_controllers/RotationTools.h>
#include <rl_controllers/Utilities.h>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <fstream>

namespace {
constexpr double kDeltaPosThreshold = 0.05;

double getGainOrDefault(const std::map<std::string, float> &gains, const std::string &jointName) {
  const auto it = gains.find(jointName);
  return it == gains.end() ? 0.0 : static_cast<double>(it->second);
}
}  // namespace

namespace legged {

using config_type = controller_interface::interface_configuration_type;

RLControllerBase::RLControllerBase() : controller_interface::ControllerInterface() {}

// First
controller_interface::CallbackReturn RLControllerBase::on_init() {
  jointNames = {"idx01_left_hip_roll", "idx02_left_hip_yaw", "idx03_left_hip_pitch", "idx04_left_tarsus", "idx05_left_toe_pitch", "idx06_left_toe_roll",
                "idx07_right_hip_roll", "idx08_right_hip_yaw", "idx09_right_hip_pitch", "idx10_right_tarsus", "idx11_right_toe_pitch", "idx12_right_toe_roll",
                "idx13_left_arm_joint1", "idx14_left_arm_joint2", "idx15_left_arm_joint3", "idx16_left_arm_joint4", "idx17_left_arm_joint5", "idx18_left_arm_joint6", "idx19_left_arm_joint7",
                "idx20_right_arm_joint1", "idx21_right_arm_joint2", "idx22_right_arm_joint3", "idx23_right_arm_joint4", "idx24_right_arm_joint5", "idx25_right_arm_joint6", "idx26_right_arm_joint7"};

  // Store variables from the parameter server into joint_names_, command_interface_types_, and state_interface_types_
  joint_names_ = auto_declare<std::vector<std::string>>("joints", joint_names_);
  command_interface_types_ =
      auto_declare<std::vector<std::string>>("command_interfaces", command_interface_types_);
  state_interface_types_ =
      auto_declare<std::vector<std::string>>("state_interfaces", state_interface_types_);
  actuatedDofNum_ = joint_names_.size();

  tfBroadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(get_node());

  // Load policy model and rl cfg
  if (!loadModel()) {
    RCLCPP_ERROR_STREAM(rclcpp::get_logger("rclcpp"), "[RLControllerBase] Failed to load the model. Ensure the path is correct and accessible.");
    return CallbackReturn::FAILURE;
  }
  if (!loadRLCfg()) {
    RCLCPP_ERROR_STREAM(rclcpp::get_logger("rclcpp"), "[RLControllerBase] Failed to load the rl config. Ensure the yaml is correct and accessible.");
    return CallbackReturn::FAILURE;
  }

  std::string packageSharePath = ament_index_cpp::get_package_share_directory("rl_controllers");
  std::string csvFilePath = packageSharePath + "/pkl_data/walk_data_all.csv";
  std::vector<std::vector<double>> mocap_data_leg_dof_pos = readCSV(csvFilePath);
  // Extract non-zero elements by known indices
  for (const auto &row : mocap_data_leg_dof_pos) {
    std::vector<double> selected_elements;
    for (size_t idx : non_zero_indices) {
      if (idx < row.size()) {  // Ensure index is within bounds
        selected_elements.push_back(row[idx]);
      }
    }
    ref_dof_pos.push_back(selected_elements);
  }
  trajectory_duration = (mocap_data_leg_dof_pos.size() - 1) / fps;
  trajectory_num_frames = mocap_data_leg_dof_pos.size();

  switchTime = rclcpp::Clock(RCL_ROS_TIME).now();
  standJointAngles_.resize(actuatedDofNum_);
  lieJointAngles_.resize(actuatedDofNum_);
  allJointPos_.resize(actuatedDofNum_);

  auto &StandState = standJointState;
  auto &LieState = lieJointState;

  lieJointAngles_ << LieState.idx01_left_hip_roll, LieState.idx02_left_hip_yaw, LieState.idx03_left_hip_pitch, LieState.idx04_left_tarsus, LieState.idx05_left_toe_pitch, LieState.idx06_left_toe_roll,
      LieState.idx07_right_hip_roll, LieState.idx08_right_hip_yaw, LieState.idx09_right_hip_pitch, LieState.idx10_right_tarsus, LieState.idx11_right_toe_pitch, LieState.idx12_right_toe_roll,
      LieState.idx13_left_arm_joint1, LieState.idx14_left_arm_joint2, LieState.idx15_left_arm_joint3, LieState.idx16_left_arm_joint4, LieState.idx17_left_arm_joint5, LieState.idx18_left_arm_joint6, LieState.idx19_left_arm_joint7,
      LieState.idx20_right_arm_joint1, LieState.idx21_right_arm_joint2, LieState.idx22_right_arm_joint3, LieState.idx23_right_arm_joint4, LieState.idx24_right_arm_joint5, LieState.idx25_right_arm_joint6, LieState.idx26_right_arm_joint7;

  standJointAngles_ << StandState.idx01_left_hip_roll, StandState.idx02_left_hip_yaw, StandState.idx03_left_hip_pitch,
      StandState.idx04_left_tarsus, StandState.idx05_left_toe_pitch, StandState.idx06_left_toe_roll,
      StandState.idx07_right_hip_roll, StandState.idx08_right_hip_yaw, StandState.idx09_right_hip_pitch,
      StandState.idx10_right_tarsus, StandState.idx11_right_toe_pitch, StandState.idx12_right_toe_roll,
      StandState.idx13_left_arm_joint1, StandState.idx14_left_arm_joint2,
      StandState.idx15_left_arm_joint3, StandState.idx16_left_arm_joint4,
      StandState.idx17_left_arm_joint5, StandState.idx18_left_arm_joint6,
      StandState.idx19_left_arm_joint7, StandState.idx20_right_arm_joint1,
      StandState.idx21_right_arm_joint2, StandState.idx22_right_arm_joint3,
      StandState.idx23_right_arm_joint4, StandState.idx24_right_arm_joint5,
      StandState.idx25_right_arm_joint6, StandState.idx26_right_arm_joint7;

  realJointPosPublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/real_joint_pos", 1);
  realJointVelPublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/real_joint_vel", 1);
  realJointTorquePublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/real_joint_torque", 1);

  rlPlannedJointPosPublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/rl_planned_joint_pos", 1);
  rlPlannedJointVelPublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/rl_planned_joint_vel", 1);
  rlPlannedTorquePublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/rl_planned_joint_torque", 1);

  realImuAngularVelPublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/imu_angular_vel", 1);
  realImuLinearAccPublisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/imu_linear_acc", 1);
  realImuEulerXyzPulbisher_ = get_node()->create_publisher<std_msgs::msg::Float64MultiArray>("data_analysis/imu_euler_xyz", 1);
  phasePublisher_ = get_node()->create_publisher<std_msgs::msg::Float64>("data_analysis/phase", 1);

  cmdVelSub_ = get_node()->create_subscription<geometry_msgs::msg::Twist>(
      "/cmd_vel", 1, std::bind(&RLControllerBase::cmdVelCallback, this, std::placeholders::_1));
  joyInfoSub_ = get_node()->create_subscription<sensor_msgs::msg::Joy>(
      "/joy", 1, std::bind(&RLControllerBase::joyInfoCallback, this, std::placeholders::_1));

  auto emergencyStopCallback = [this](const std_msgs::msg::Float32::SharedPtr /*msg*/) {
    emergency_stop = true;
    RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "Emergency Stop");
  };
  emgStopSub_ = get_node()->create_subscription<std_msgs::msg::Float32>(
      "/emergency_stop", 1, emergencyStopCallback);

  // start control
  auto startControlCallback = [this](const std_msgs::msg::Float32::SharedPtr /*msg*/) {
    // RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "Current Time s: " << rclcpp::Clock(RCL_ROS_TIME).now().seconds());
    // RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "Switch Time s: " << switchTime.seconds());
    // RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "Current Time nano: " << rclcpp::Clock(RCL_ROS_TIME).now());
    // RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "Switch Time nano: " << switchTime);

    rclcpp::Duration t(0, 500000000);
    auto currentTime = rclcpp::Clock(RCL_ROS_TIME).now();
    if (currentTime - switchTime > t) {
      if (!start_control) {
        start_control = true;
        standPercent_ = 0;
        for (size_t i = 0; i < hybridJointHandles_.size(); i++) {
          currentJointAngles_[i] = hybridJointHandles_[i]->getPosCurr();
        }
        mode_ = Mode::LIE;
        RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "Start Control");
      } else {
        start_control = false;
        mode_ = Mode::DEFAULT;
        RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "ShutDown Control");
      }
      switchTime = rclcpp::Clock(RCL_ROS_TIME).now();
    }
  };

  startCtrlSub_ = get_node()->create_subscription<std_msgs::msg::Float32>(
      "/start_control", 1, startControlCallback);

  // switch mode
  auto switchModeCallback = [this](const std_msgs::msg::Float32::SharedPtr /*msg*/) {
    rclcpp::Duration t(0, 500000000);
    auto currentTime = rclcpp::Clock(RCL_ROS_TIME).now();
    if (currentTime - switchTime > t) {
      if (start_control == true) {
        if (mode_ == Mode::STAND) {
          standPercent_ = 0;
          for (size_t i = 0; i < hybridJointHandles_.size(); i++) {
            currentJointAngles_[i] = hybridJointHandles_[i]->getPosCurr();
          }
          mode_ = Mode::LIE;
          RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "STAND2LIE");
        } else if (mode_ == Mode::LIE) {
          standPercent_ = 0;
          mode_ = Mode::STAND;
          RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "LIE2STAND");
        }
      }
      switchTime = rclcpp::Clock(RCL_ROS_TIME).now();
    }
  };
  switchModeSub_ = get_node()->create_subscription<std_msgs::msg::Float32>(
      "/switch_mode", 1, switchModeCallback);

  // walkMode
  auto walkModeCallback = [this](const std_msgs::msg::Float32::SharedPtr /*msg*/) {
    rclcpp::Duration t(0, 500000000);
    auto currentTime = rclcpp::Clock(RCL_ROS_TIME).now();
    if (currentTime - switchTime > t) {
      if (mode_ == Mode::STAND) {
        loopCount_ = 0;
        mode_ = Mode::WALK;
        RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "STAND2WALK");
      }
      switchTime = rclcpp::Clock(RCL_ROS_TIME).now();
    }
  };
  walkModeSub_ = get_node()->create_subscription<std_msgs::msg::Float32>("/walk_mode", 1, walkModeCallback);

  // positionMode
  auto positionModeCallback = [this](const std_msgs::msg::Float32::SharedPtr /*msg*/) {
    rclcpp::Duration t(0, 500000000);
    auto currentTime = rclcpp::Clock(RCL_ROS_TIME).now();
    if (currentTime - switchTime > t) {
      if (mode_ == Mode::WALK) {
        mode_ = Mode::STAND;
        RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "WALK2STAND");
      } else if (mode_ == Mode::DEFAULT) {
        standPercent_ = 0;
        for (size_t i = 0; i < hybridJointHandles_.size(); i++) {
          currentJointAngles_[i] = hybridJointHandles_[i]->getPosCurr();
        }
        mode_ = Mode::LIE;
        RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "DEF2LIE");
      }
      switchTime = rclcpp::Clock(RCL_ROS_TIME).now();
    }
  };
  positionCtrlSub_ = get_node()->create_subscription<std_msgs::msg::Float32>("/position_control", 1, positionModeCallback);

  RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "rl_controller initialized!!!!!!!!!");
  return CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn RLControllerBase::on_configure([[maybe_unused]] const rclcpp_lifecycle::State &previous_state) {
  return controller_interface::CallbackReturn::SUCCESS;
}

// Second
controller_interface::InterfaceConfiguration RLControllerBase::command_interface_configuration()
    const {
  // Initialize configuration
  controller_interface::InterfaceConfiguration conf = {config_type::INDIVIDUAL, {}};
  // Reserve space: number of joints × number of command interfaces
  conf.names.reserve(joint_names_.size() * command_interface_types_.size());
  // Iterate over all joint names and command interface types, and store them in conf.names
  for (const auto &joint_name : joint_names_) {
    for (const auto &interface_type : command_interface_types_) {
      conf.names.push_back(joint_name + "/" + interface_type);
    }
  }

  return conf;
}

controller_interface::InterfaceConfiguration RLControllerBase::state_interface_configuration() const {
  controller_interface::InterfaceConfiguration conf = {config_type::INDIVIDUAL, {}};

  conf.names.reserve(joint_names_.size() * state_interface_types_.size());
  for (const auto &joint_name : joint_names_) {
    for (const auto &interface_type : state_interface_types_) {
      conf.names.push_back(joint_name + "/" + interface_type);
    }
  }

  // ===== IMU state interfaces =====
  conf.names.push_back("imu/orientation.x");
  conf.names.push_back("imu/orientation.y");
  conf.names.push_back("imu/orientation.z"); 
  conf.names.push_back("imu/orientation.w");

  conf.names.push_back("imu/angular_velocity.x");
  conf.names.push_back("imu/angular_velocity.y");
  conf.names.push_back("imu/angular_velocity.z");

  conf.names.push_back("imu/linear_acceleration.x");
  conf.names.push_back("imu/linear_acceleration.y");
  conf.names.push_back("imu/linear_acceleration.z");

  return conf;
}

controller_interface::CallbackReturn RLControllerBase::on_activate(const rclcpp_lifecycle::State &) {
  // sim !!!
  std::map<std::string, std::vector<int>> state_interface_indices;
  for (int i = 0; i < static_cast<int>(state_interfaces_.size()); i++) {
    state_interface_indices[state_interfaces_[i].get_prefix_name()].push_back(i);
    RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "%s", state_interfaces_[i].get_name().c_str());
  }

  RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "size: " << state_interfaces_.size());

  std::map<std::string, std::vector<int>> command_interface_indices;
  for (int i = 0; i < static_cast<int>(command_interfaces_.size()); i++) {
    command_interface_indices[command_interfaces_[i].get_prefix_name()].push_back(i);
    RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "%s", command_interfaces_[i].get_name().c_str());
  }

  RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "command success");

  for (const auto &joint_name : joint_names_) {
    auto state_indices = state_interface_indices[joint_name][0];
    auto command_indices = command_interface_indices[joint_name][0];
    RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "%d", state_indices);
    auto joint_handle = std::make_unique<HybridJointHandle>(
        std::ref(state_interfaces_[state_indices]),          // Position feedback
        std::ref(state_interfaces_[state_indices + 1]),      // Velocity feedback
        std::ref(state_interfaces_[state_indices + 2]),      // Torque feedback
        std::ref(command_interfaces_[command_indices]),      // Position desired
        std::ref(command_interfaces_[command_indices + 1]),  // Velocity desired
        std::ref(command_interfaces_[command_indices + 2]),  // Torque desired
        std::ref(command_interfaces_[command_indices + 3]),  // Kp desired
        std::ref(command_interfaces_[command_indices + 4])   // Kd desired
    );
    hybridJointHandles_.push_back(std::move(joint_handle));
  }

  starting();

  return CallbackReturn::SUCCESS;
}

void RLControllerBase::starting() {
  // Update Status
  updateStateEstimation(get_node()->now(), rclcpp::Duration::from_seconds(0.002));
  currentJointAngles_.resize(actuatedDofNum_);

  // sim
  for (size_t i = 0; i < hybridJointHandles_.size(); i++) {
    currentJointAngles_[i] = hybridJointHandles_[i]->getPosCurr();
  }

  scalar_t durationSecs = 2.0;
  standDuration_ = durationSecs * 1000.0;
  standPercent_ = 0;
  mode_ = Mode::DEFAULT;
  loopCount_ = 0;
}

controller_interface::return_type RLControllerBase::update(
    const rclcpp::Time &time, const rclcpp::Duration &period) {
  // // RCLCPP_INFO_STREAM(rclcpp::get_logger("rclcpp"), "123");
  updateStateEstimation(time, period);
  // std::cout << " loopCount_" << loopCount_ << " standPercent_" << standPercent_ << " initJointAngles_[0]" << initJointAngles_[0]
  //         << "\n";

  switch (mode_) {
    case Mode::DEFAULT:
      handleDefaultMode();
      break;
    case Mode::LIE:
      handleLieMode();
      break;
    case Mode::STAND:
      handleStandMode();
      break;
    case Mode::WALK:
      handleWalkMode();
      break;
    default:
      RCLCPP_ERROR_STREAM(rclcpp::get_logger("rclcpp"), "Unexpected mode encountered: " << static_cast<int>(mode_));
      break;
  }

  if (emergency_stop) {
    for (size_t j = 0; j < hybridJointHandles_.size(); ++j) {
      hybridJointHandles_[j]->setCommand(0, 0, 0, 3, 0);
    }
  }

  if (emergency_stop && start_control) {
    emergency_stop = false;
    starting();
    start_control = false;
  }

  loopCount_++;

  size_t imu_offset = joint_names_.size() * state_interface_types_.size();
  imuData_.orientation.x = state_interfaces_[imu_offset + 0].get_value();
  imuData_.orientation.y = state_interfaces_[imu_offset + 1].get_value();
  imuData_.orientation.z = state_interfaces_[imu_offset + 2].get_value();
  imuData_.orientation.w = state_interfaces_[imu_offset + 3].get_value();

  imuData_.angular_velocity.x = state_interfaces_[imu_offset + 4].get_value();
  imuData_.angular_velocity.y = state_interfaces_[imu_offset + 5].get_value();
  imuData_.angular_velocity.z = state_interfaces_[imu_offset + 6].get_value();

  imuData_.linear_acceleration.x = state_interfaces_[imu_offset + 7].get_value();
  imuData_.linear_acceleration.y = state_interfaces_[imu_offset + 8].get_value();
  imuData_.linear_acceleration.z = state_interfaces_[imu_offset + 9].get_value();

  return controller_interface::return_type::OK;
}

void RLControllerBase::holdJointsAtZero(const std::vector<int> &indices) {
  constexpr double targetPosition = 0.0;
  const int jointCount = static_cast<int>(hybridJointHandles_.size());
  const int measuredCount = static_cast<int>(allJointPos_.size());

  for (int idx : indices) {
    if (idx < 0 || idx >= jointCount || idx >= measuredCount) {
      continue;
    }

    const std::string &partName = jointNames[idx];
    const double stiffness = getGainOrDefault(robotCfg_.controlCfg.stiffness, partName);
    const double damping = getGainOrDefault(robotCfg_.controlCfg.damping, partName);
    const double delta_pos = targetPosition - allJointPos_(idx);

    const double clamped_ref_pos = delta_pos > 0
                                       ? std::min(targetPosition, allJointPos_(idx) + kDeltaPosThreshold)
                                       : std::max(targetPosition, allJointPos_(idx) - kDeltaPosThreshold);

    hybridJointHandles_[idx]->setCommand(clamped_ref_pos, 0, stiffness, damping, 0);
  }
}

void RLControllerBase::handleDefaultMode() {
  for (int j = 0; j < actionsSize_; j++) {
    hybridJointHandles_[j]->setCommand(0, 0, 0, 0.1, 0);
  }

  holdJointsAtZero(joint_mapping_fixed);
  holdJointsAtZero(arm_joint_mapping);
}

void RLControllerBase::handleLieMode() {
  if (standPercent_ <= 1) {
    for (int j = 0; j < actionsSize_; j++) {
      if (j == 4 || j == 5 || j == 10 || j == 11) {
        scalar_t pos_des = currentJointAngles_[j] * (1 - standPercent_) + lieJointAngles_[j] * standPercent_;
        hybridJointHandles_[j]->setCommand(pos_des, 0, lie_kp_ankle_, lie_kd_ankle_, 0);
      } else {
        scalar_t pos_des = currentJointAngles_[j] * (1 - standPercent_) + lieJointAngles_[j] * standPercent_;
        hybridJointHandles_[j]->setCommand(pos_des, 0, lie_kp_large_, lie_kd_large_, 0);
      }
    }
    standPercent_ += 1 / standDuration_;
    standPercent_ = std::min(standPercent_, scalar_t(1));
  }

  holdJointsAtZero(joint_mapping_fixed);
  holdJointsAtZero(arm_joint_mapping);
}

void RLControllerBase::handleStandMode() {
  if (standPercent_ <= 1) {
    for (int j = 0; j < actionsSize_; j++) {
      if (j == 4 || j == 5 || j == 10 || j == 11) {
        scalar_t pos_des = lieJointAngles_[j] * (1 - standPercent_) + standJointAngles_[j] * standPercent_;
        hybridJointHandles_[j]->setCommand(pos_des, 0, stance_kp_ankle_, stance_kd_ankle_, 0);
      } else {
        scalar_t pos_des = lieJointAngles_[j] * (1 - standPercent_) + standJointAngles_[j] * standPercent_;
        hybridJointHandles_[j]->setCommand(pos_des, 0, stance_kp_large_, stance_kd_large_, 0);
      }
    }
    standPercent_ += 1 / standDuration_;
    standPercent_ = std::min(standPercent_, scalar_t(1));
  }

  holdJointsAtZero(joint_mapping_fixed);
  holdJointsAtZero(arm_joint_mapping);
}

controller_interface::CallbackReturn RLControllerBase::on_deactivate(const rclcpp_lifecycle::State &) {
  release_interfaces();

  return CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn RLControllerBase::on_cleanup(const rclcpp_lifecycle::State &) {
  return CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn RLControllerBase::on_error(const rclcpp_lifecycle::State &) {
  return CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn RLControllerBase::on_shutdown(const rclcpp_lifecycle::State &) {
  return CallbackReturn::SUCCESS;
}

void RLControllerBase::updateStateEstimation(const rclcpp::Time &time, const rclcpp::Duration &period [[maybe_unused]]) {
  vector_t jointPos(hybridJointHandles_.size()), jointVel(hybridJointHandles_.size()),
      jointTor(hybridJointHandles_.size()), output_torque(hybridJointHandles_.size()),
      pos_des_output(hybridJointHandles_.size()), vel_des_output(hybridJointHandles_.size());

  vector_t imuEulerXyz(3);
  quaternion_t quat;
  vector3_t angularVel, linearAccel;
  matrix3_t orientationCovariance, angularVelCovariance, linearAccelCovariance;

  for (size_t i = 0; i < hybridJointHandles_.size(); ++i) {
    jointPos(i) = hybridJointHandles_[i]->getPosCurr();
    allJointPos_(i) = hybridJointHandles_[i]->getPosCurr();
    jointVel(i) = hybridJointHandles_[i]->getVelCurr();
    jointTor(i) = hybridJointHandles_[i]->getTauCurr();

    pos_des_output(i) = hybridJointHandles_[i]->getPosDes();
    vel_des_output(i) = hybridJointHandles_[i]->getVelDes();
    output_torque(i) = hybridJointHandles_[i]->getFeedforward() +
                       hybridJointHandles_[i]->getKp() * (hybridJointHandles_[i]->getPosDes() - hybridJointHandles_[i]->getPosCurr()) +
                       hybridJointHandles_[i]->getKd() * (hybridJointHandles_[i]->getVelDes() - hybridJointHandles_[i]->getVelCurr());
  }

  // sim
  quat.x() = imuData_.orientation.x;
  quat.y() = imuData_.orientation.y;
  quat.z() = imuData_.orientation.z;
  quat.w() = imuData_.orientation.w;

  angularVel(0) = imuData_.angular_velocity.x;
  angularVel(1) = imuData_.angular_velocity.y;
  angularVel(2) = imuData_.angular_velocity.z;
  linearAccel(0) = imuData_.linear_acceleration.x;
  linearAccel(1) = imuData_.linear_acceleration.y;
  linearAccel(2) = imuData_.linear_acceleration.z;
  for (size_t i = 0; i < 9; ++i) {
    orientationCovariance(i) = imuData_.orientation_covariance[i];
    angularVelCovariance(i) = imuData_.angular_velocity_covariance[i];
    linearAccelCovariance(i) = imuData_.linear_acceleration_covariance[i];
  }

  vector_t selectedJointPos(12);
  for (size_t i = 0; i < 12; ++i) {
    selectedJointPos(i) = jointPos(i);  // Indices 1-12
  }
  // selectedJointPos(12) = jointPos(12); // Index 13
  // selectedJointPos(13) = jointPos(15); // Index 16
  // selectedJointPos(14) = jointPos(19); // Index 20
  // selectedJointPos(15) = jointPos(22); // Index 23

  vector_t selectedJointVel(12);
  for (size_t i = 0; i < 12; ++i) {
    selectedJointVel(i) = jointVel(i);  // Indices 1-12
  }
  // selectedJointVel(12) = jointVel(12); // Index 13
  // selectedJointVel(13) = jointVel(15); // Index 16
  // selectedJointVel(14) = jointVel(19); // Index 20
  // selectedJointVel(15) = jointVel(22); // Index 23
  propri_.jointPos = selectedJointPos;
  propri_.jointVel = selectedJointVel;
  propri_.baseAngVel = angularVel;

  vector3_t gravityVector(0, 0, -1);
  vector3_t zyx = quatToZyx(quat);
  matrix_t inverseRot = getRotationMatrixFromZyxEulerAngles(zyx).inverse();
  propri_.projectedGravity = inverseRot * gravityVector;
  propri_.baseEulerXyz = quatToXyz(quat);
  phase_ = time.seconds();

  for (size_t i = 0; i < 3; ++i) {
    imuEulerXyz(i) = propri_.baseEulerXyz[i];
  }

  realJointPosPublisher_->publish(createFloat64MultiArrayFromVector(jointPos));
  realJointVelPublisher_->publish(createFloat64MultiArrayFromVector(jointVel));
  realJointTorquePublisher_->publish(createFloat64MultiArrayFromVector(jointTor));

  realImuAngularVelPublisher_->publish(createFloat64MultiArrayFromVector(angularVel));
  realImuLinearAccPublisher_->publish(createFloat64MultiArrayFromVector(linearAccel));
  realImuEulerXyzPulbisher_->publish(createFloat64MultiArrayFromVector(imuEulerXyz));

  rlPlannedJointPosPublisher_->publish(createFloat64MultiArrayFromVector(pos_des_output));
  rlPlannedJointVelPublisher_->publish(createFloat64MultiArrayFromVector(vel_des_output));
  rlPlannedTorquePublisher_->publish(createFloat64MultiArrayFromVector(output_torque));
}

void RLControllerBase::cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr msg) {
  command_.x = msg->linear.x / 3.0;
  command_.y = 0.0;
  command_.yaw = msg->angular.z;
}

void RLControllerBase::joyInfoCallback(const sensor_msgs::msg::Joy::SharedPtr msg) {
  if (msg->header.frame_id.empty()) {
    return;
  }
  // memcpy(joyInfo.axes, msg.axes, sizeof(joyInfo.axes));
  // memcpy(joyInfo.buttons, msg.buttons, sizeof(joyInfo.buttons));
  for (int i = 0; i < static_cast<int>(msg->axes.size()); i++) {
    joyInfo.axes[i] = msg->axes[i];
    // std::cout << joyInfo.axes[i];
    // std::cout << std::endl;
  }
  for (int i = 0; i < static_cast<int>(msg->buttons.size()); i++) {
    joyInfo.buttons[i] = msg->buttons[i];
    // std::cout << joyInfo.buttons[i];
    // std::cout << std::endl;
  }
}

// Function to read CSV file and store data in a 2D vector
std::vector<std::vector<double>> RLControllerBase::readCSV(const std::string &filePath) {
  std::vector<std::vector<double>> data;
  std::ifstream file(filePath);
  std::string line;

  while (std::getline(file, line)) {
    std::stringstream ss(line);
    std::string value;
    std::vector<double> row;
    while (std::getline(ss, value, ',')) {
      row.push_back(std::stod(value));
    }
    data.push_back(row);
  }
  return data;
}
// Function to calculate frame blending indices and factor
void RLControllerBase::calcFrameBlend(double phase, int trajectory_num_frames, int &frame_idx0, int &frame_idx1, double &blend) {
  // Clip phase to be within 0.0 and 1.0
  phase = std::clamp(phase, 0.0, 1.0);
  // Calculate number of frames
  int num_frame = trajectory_num_frames - 1;
  // Calculate frame indices
  frame_idx0 = static_cast<int>(phase * num_frame);
  frame_idx1 = std::min(frame_idx0 + 1, num_frame);
  // Calculate blend factor
  blend = std::clamp((phase * num_frame) - frame_idx0, 0.0, 1.0);
}

}  // namespace legged

#include "pluginlib/class_list_macros.hpp"

PLUGINLIB_EXPORT_CLASS(
    legged::RLControllerBase, controller_interface::ControllerInterface)