#include "rl_controllers/AcController.h"
#include <algorithm>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <filesystem>
#include "rl_controllers/RotationTools.h"

namespace legged {

void AcController::handleWalkMode() {
  if (loopCount_ % robotCfg_.controlCfg.decimation == 0) {
    computeObservation();
    computeActions();
    // limit action range
    scalar_t actionMin = -robotCfg_.clipActions;
    scalar_t actionMax = robotCfg_.clipActions;
    std::transform(actions_.begin(), actions_.end(), actions_.begin(),
                   [actionMin, actionMax](scalar_t value) { return std::clamp(value, actionMin, actionMax); });
  }

  // set action
  for (int i = 0; i < actionsSize_; i++) {
    const int jointIndex = leg_joint_mapping[i];
    const std::string partName = jointNames[jointIndex];
    scalar_t pos_des = actions_[i] * robotCfg_.controlCfg.actionScale + defaultJointAngles_(jointIndex);
    double stiffness = robotCfg_.controlCfg.stiffness.at(partName);  // get stiffness from parameter server
    double damping = robotCfg_.controlCfg.damping.at(partName);      // get damping from parameter server
    hybridJointHandles_[jointIndex]->setCommand(pos_des, 0, stiffness, damping, 0);
    lastActions_(i, 0) = actions_[i];
  }

  holdJointsAtZero(joint_mapping_fixed);
  holdJointsAtZero(arm_joint_mapping);
}

bool AcController::loadModel() {
  std::string policyFilePath;
  if (!get_node()->get_parameter("policyFile", policyFilePath)) {
    RCLCPP_ERROR_STREAM(rclcpp::get_logger("rlccpp"), "Get policy path fail from param server, some error occur!");
    return false;
  }

  const auto logger = rclcpp::get_logger("rlccpp");
  const std::string package_share_directory = ament_index_cpp::get_package_share_directory("rl_controllers");
  const std::filesystem::path fullPolicyFilePath = std::filesystem::path(package_share_directory) / policyFilePath;

  if (!std::filesystem::exists(fullPolicyFilePath)) {
    RCLCPP_ERROR_STREAM(logger, "ONNX policy file does not exist: " << fullPolicyFilePath.string());
    return false;
  }

  policyFilePath_ = fullPolicyFilePath.string();
  RCLCPP_INFO_STREAM(logger, "Load Onnx model from path : " << policyFilePath_);

  // create env
  onnxEnvPrt_.reset(new Ort::Env(ORT_LOGGING_LEVEL_WARNING, "LeggedOnnxController"));
  // create session
  Ort::SessionOptions sessionOptions;
  sessionOptions.SetInterOpNumThreads(1);
  sessionPtr_ = std::make_unique<Ort::Session>(*onnxEnvPrt_, policyFilePath_.c_str(), sessionOptions);
  // get input and output info
  inputNames_.clear();
  outputNames_.clear();
  inputShapes_.clear();
  outputShapes_.clear();
  Ort::AllocatorWithDefaultOptions allocator;
  RCLCPP_INFO_STREAM(logger, "ONNX input count: " << sessionPtr_->GetInputCount()
                                                  << ", output count: " << sessionPtr_->GetOutputCount());
  for (int i = 0; i < static_cast<int>(sessionPtr_->GetInputCount()); i++) {
    auto inputnamePtr = sessionPtr_->GetInputNameAllocated(i, allocator);
    inputNodeNameAllocatedStrings.push_back(std::move(inputnamePtr));
    inputNames_.push_back(inputNodeNameAllocatedStrings.back().get());
    inputShapes_.push_back(sessionPtr_->GetInputTypeInfo(i).GetTensorTypeAndShapeInfo().GetShape());
    RCLCPP_DEBUG_STREAM(logger, "Input Name [" << i << "]: " << inputNames_.back());
  }
  for (int i = 0; i < static_cast<int>(sessionPtr_->GetOutputCount()); i++) {
    auto outputnamePtr = sessionPtr_->GetOutputNameAllocated(i, allocator);
    outputNodeNameAllocatedStrings.push_back(std::move(outputnamePtr));
    outputNames_.push_back(outputNodeNameAllocatedStrings.back().get());
    outputShapes_.push_back(sessionPtr_->GetOutputTypeInfo(i).GetTensorTypeAndShapeInfo().GetShape());
    RCLCPP_DEBUG_STREAM(logger, "Output Name [" << i << "]: " << outputNames_.back());
  }

  RCLCPP_INFO_STREAM(logger, "Load Onnx model successfully !!!");
  return true;
}

bool AcController::loadRLCfg() {
  RLRobotCfg::LegInitState& legInitState = robotCfg_.initState;
  RLRobotCfg::ArmInitState& armInitState = robotCfg_.arminitState;
  RLRobotCfg::ControlCfg& controlCfg = robotCfg_.controlCfg;
  RLRobotCfg::ObsScales& obsScales = robotCfg_.obsScales;

  int error = 0;
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx01_left_hip_roll", legInitState.idx01_left_hip_roll));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx02_left_hip_yaw", legInitState.idx02_left_hip_yaw));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx03_left_hip_pitch", legInitState.idx03_left_hip_pitch));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx04_left_tarsus", legInitState.idx04_left_tarsus));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx05_left_toe_pitch", legInitState.idx05_left_toe_pitch));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx06_left_toe_roll", legInitState.idx06_left_toe_roll));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx13_left_arm_joint1", armInitState.idx13_left_arm_joint1));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx14_left_arm_joint2", armInitState.idx14_left_arm_joint2));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx15_left_arm_joint3", armInitState.idx15_left_arm_joint3));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx16_left_arm_joint4", armInitState.idx16_left_arm_joint4));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx17_left_arm_joint5", armInitState.idx17_left_arm_joint5));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx18_left_arm_joint6", armInitState.idx18_left_arm_joint6));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx19_left_arm_joint7", armInitState.idx19_left_arm_joint7));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx07_right_hip_roll", legInitState.idx07_right_hip_roll));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx08_right_hip_yaw", legInitState.idx08_right_hip_yaw));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx09_right_hip_pitch", legInitState.idx09_right_hip_pitch));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx10_right_tarsus", legInitState.idx10_right_tarsus));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx11_right_toe_pitch", legInitState.idx11_right_toe_pitch));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_joint_angle.idx12_right_toe_roll", legInitState.idx12_right_toe_roll));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx20_right_arm_joint1", armInitState.idx20_right_arm_joint1));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx21_right_arm_joint2", armInitState.idx21_right_arm_joint2));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx22_right_arm_joint3", armInitState.idx22_right_arm_joint3));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx23_right_arm_joint4", armInitState.idx23_right_arm_joint4));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx24_right_arm_joint5", armInitState.idx24_right_arm_joint5));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx25_right_arm_joint6", armInitState.idx25_right_arm_joint6));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.init_state.default_arm_joint_angle.idx26_right_arm_joint7", armInitState.idx26_right_arm_joint7));

  error += static_cast<int>(!get_node()->get_parameters("LeggedRobotCfg.control.stiffness", controlCfg.stiffness));
  error += static_cast<int>(!get_node()->get_parameters("LeggedRobotCfg.control.damping", controlCfg.damping));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.control.action_scale", controlCfg.actionScale));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.control.decimation", controlCfg.decimation));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.control.cycle_time", controlCfg.cycle_time));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.clip_scales.clip_observations", robotCfg_.clipObs));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.clip_scales.clip_actions", robotCfg_.clipActions));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.obs_scales.lin_vel", obsScales.linVel));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.obs_scales.ang_vel", obsScales.angVel));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.obs_scales.dof_pos", obsScales.dofPos));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.obs_scales.dof_vel", obsScales.dofVel));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.obs_scales.height_measurements", obsScales.heightMeasurements));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.normalization.obs_scales.quat", obsScales.quat));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.size.actions_size", actionsSize_));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.size.observations_size", observationSize_));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.size.num_hist", num_hist_));

  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.mode.sw_mode", sw_mode_));
  error += static_cast<int>(!get_node()->get_parameter("LeggedRobotCfg.mode.cmd_threshold", cmd_threshold_));

  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.lie_kp_large", lie_kp_large_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.lie_kd_large", lie_kd_large_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.lie_kp_ankle", lie_kp_ankle_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.lie_kd_ankle", lie_kd_ankle_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.stance_kp_large", stance_kp_large_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.stance_kd_large", stance_kd_large_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.stance_kp_ankle", stance_kp_ankle_));
  error += static_cast<int>(!get_node()->get_parameter("init_pos_control.stance_kd_ankle", stance_kd_ankle_));

  actions_.resize(actionsSize_);
  observations_.resize(observationSize_ * num_hist_);

  command_.x = 0;
  command_.y = 0;
  command_.yaw = 0;
  baseLinVel_.setZero();
  basePosition_.setZero();
  std::vector<scalar_t> defaultJointAngles{
      robotCfg_.initState.idx01_left_hip_roll, robotCfg_.initState.idx02_left_hip_yaw, robotCfg_.initState.idx03_left_hip_pitch,
      robotCfg_.initState.idx04_left_tarsus, robotCfg_.initState.idx05_left_toe_pitch, robotCfg_.initState.idx06_left_toe_roll,
      robotCfg_.initState.idx07_right_hip_roll, robotCfg_.initState.idx08_right_hip_yaw, robotCfg_.initState.idx09_right_hip_pitch,
      robotCfg_.initState.idx10_right_tarsus, robotCfg_.initState.idx11_right_toe_pitch, robotCfg_.initState.idx12_right_toe_roll,
      robotCfg_.arminitState.idx13_left_arm_joint1, robotCfg_.arminitState.idx14_left_arm_joint2, robotCfg_.arminitState.idx15_left_arm_joint3, robotCfg_.arminitState.idx16_left_arm_joint4,
      robotCfg_.arminitState.idx17_left_arm_joint5, robotCfg_.arminitState.idx18_left_arm_joint6, robotCfg_.arminitState.idx19_left_arm_joint7,
      robotCfg_.arminitState.idx20_right_arm_joint1, robotCfg_.arminitState.idx21_right_arm_joint2, robotCfg_.arminitState.idx22_right_arm_joint3, robotCfg_.arminitState.idx23_right_arm_joint4,
      robotCfg_.arminitState.idx24_right_arm_joint5, robotCfg_.arminitState.idx25_right_arm_joint6, robotCfg_.arminitState.idx26_right_arm_joint7};
  lastActions_.resize(actionsSize_);
  lastActions_.setZero();

  const int inputSize = num_hist_ * observationSize_;
  proprioHistoryBuffer_.resize(inputSize);
  proprioHistoryBuffer_.setZero();
  defaultJointAngles_.resize(actuatedDofNum_);
  defaultJointAnglesActuated_.resize(actionsSize_);

  for (int i = 0; i < actuatedDofNum_; i++) {
    defaultJointAngles_(i) = defaultJointAngles[i];
  }
  for (int i = 0; i < actionsSize_; i++) {
    defaultJointAnglesActuated_(i) = defaultJointAngles[leg_joint_mapping[i]];
  }

  return (error == 0);
}

void AcController::computeActions() {
  // create input tensor object
  std::vector<Ort::Value> inputValues;
  inputValues.push_back(Ort::Value::CreateTensor<tensor_element_t>(memoryInfo, observations_.data(), observations_.size(),
                                                                   inputShapes_[0].data(), inputShapes_[0].size()));
  // run inference
  Ort::RunOptions runOptions;
  std::vector<Ort::Value> outputValues = sessionPtr_->Run(runOptions, inputNames_.data(), inputValues.data(), 1, outputNames_.data(), 1);

  for (int i = 0; i < actionsSize_; i++) {
    actions_[i] = *(outputValues[0].GetTensorMutableData<tensor_element_t>() + i);
  }
}

void AcController::computeObservation() {
  // command = [sin_phase, cos_phase, cmd_x, cmd_y, cmd_yaw]
  vector_t command(5);

  if (sw_mode_) {
    cmd_norm_ = std::sqrt(command_.x * command_.x + command_.y * command_.y + command_.yaw * command_.yaw);
    if (cmd_norm_ <= cmd_threshold_) {
      auto now = rclcpp::Clock(RCL_ROS_TIME).now();
      double now_sec = now.seconds();
      current_time_ = now_sec;
      phase_ = 0;
      phase_start_time_ = now_sec;  // Record the current time as the start time
    } else {
      auto now = rclcpp::Clock(RCL_ROS_TIME).now();
      double now_sec = now.seconds();

      // Calculate phase increment based on the elapsed time since phase was reset
      phase_ = now_sec - phase_start_time_;
    }
  }
  // Normalize phase to [0, 1)
  phase_ = std::fmod(phase_ / robotCfg_.controlCfg.cycle_time, 1.0);
  calcFrameBlend(phase_, trajectory_num_frames, frame_idx0, frame_idx1, blend);
  ref_dof_pos_low = ref_dof_pos[frame_idx0];
  ref_dof_pos_high = ref_dof_pos[frame_idx1];
  ref_dof_pos_cal.clear();
  ref_dof_pos_cal.resize(ref_dof_pos[0].size());
  for (size_t i = 0; i < ref_dof_pos[0].size(); i++) {
    ref_dof_pos_cal[i] = (1 - blend) * ref_dof_pos_low[i] + blend * ref_dof_pos_high[i];
  }
  vector_t ref_pos_cal(actionsSize_);
  for (int i = 0; i < actionsSize_; ++i) {
    if (phase_ == 0.0) {
      ref_pos_cal[i] = 0.0;
    } else {
      ref_pos_cal[i] = ref_dof_pos_cal[i];
    }
  }
  std_msgs::msg::Float64 phase_msg;
  phase_msg.data = phase_;
  phasePublisher_->publish(phase_msg);

  command[0] = sin(2 * M_PI * phase_);
  command[1] = cos(2 * M_PI * phase_);
  command[2] = command_.x;
  command[3] = command_.y;
  command[4] = command_.yaw;

  // actions
  vector_t actions(lastActions_);

  RLRobotCfg::ObsScales& obsScales = robotCfg_.obsScales;
  matrix_t commandScaler = Eigen::DiagonalMatrix<scalar_t, 3>(obsScales.linVel, obsScales.linVel, obsScales.angVel);

  vector_t proprioObs(observationSize_);

  proprioObs << command,                                                    // 5
      (propri_.jointPos - defaultJointAnglesActuated_) * obsScales.dofPos,  // 12
      propri_.jointVel * obsScales.dofVel,                                  // 12
      actions,                                                              // 12
      propri_.baseAngVel * obsScales.angVel,                                // 3
      propri_.baseEulerXyz * obsScales.quat;                                // 3

  if (isfirstRecObs_) {
    const int actionOffset = 5 + 12 + 12;  // command + jointPos + jointVel
    const int actionCount = actionsSize_;
    for (int i = 0; i < actionCount; ++i) {
      const int obsIndex = actionOffset + i;
      if (obsIndex < proprioObs.rows()) {
        proprioObs(obsIndex, 0) = 0.0;
      }
    }

    for (int i = 0; i < num_hist_; i++) {
      proprioHistoryBuffer_.segment(i * observationSize_, observationSize_) = proprioObs.cast<tensor_element_t>();
    }
    isfirstRecObs_ = false;
  }

  proprioHistoryBuffer_.head(proprioHistoryBuffer_.size() - observationSize_) =
      proprioHistoryBuffer_.tail(proprioHistoryBuffer_.size() - observationSize_);
  proprioHistoryBuffer_.tail(observationSize_) = proprioObs.cast<tensor_element_t>();
  // clang-format on

  for (int i = 0; i < (observationSize_ * num_hist_); i++) {
    observations_[i] = static_cast<tensor_element_t>(proprioHistoryBuffer_[i]);
    // if(i < observationSize_)
    // std::cout << i << "obs:::" << observations_[i] << std::endl;
  }
  // for (size_t i = 0; i < obs.size(); i++) {
  //   observations_[i] = static_cast<tensor_element_t>(obs(i));
  // }
  // Limit observation range
  scalar_t obsMin = -robotCfg_.clipObs;
  scalar_t obsMax = robotCfg_.clipObs;
  std::transform(observations_.begin(), observations_.end(), observations_.begin(),
                 [obsMin, obsMax](scalar_t x) { return std::max(obsMin, std::min(obsMax, x)); });
}

}  // namespace legged

#include "pluginlib/class_list_macros.hpp"

PLUGINLIB_EXPORT_CLASS(
    legged::AcController, controller_interface::ControllerInterface)
