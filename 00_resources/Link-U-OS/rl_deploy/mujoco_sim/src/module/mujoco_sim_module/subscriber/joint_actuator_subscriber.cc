// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "mujoco_sim_module/subscriber/joint_actuator_subscriber.h"

#include <cstddef>
#include "mujoco_sim_module/common/xmodel_reader.h"

namespace YAML {
template <>
struct convert<aimrt_mujoco_sim::mujoco_sim_module::subscriber::JointActuatorSubscriberBase::Options> {
  using Options = aimrt_mujoco_sim::mujoco_sim_module::subscriber::JointActuatorSubscriberBase::Options;
  static Node encode(const Options& rhs) {
    Node node;

    node["joints"] = YAML::Node();
    for (const auto& joint : rhs.joints) {
      Node joint_node;
      joint_node["name"] = joint.name;
      joint_node["bind_joint"] = joint.bind_joint;
      node["joints"].push_back(joint_node);
    }

    return node;
  }

  static bool decode(const Node& node, Options& rhs) {
    if (node["joints"] && node["joints"].IsSequence()) {
      for (const auto& joint_node : node["joints"]) {
        auto joint_node_options = Options::Joint{
            .name = joint_node["name"].as<std::string>(),
            .bind_joint = joint_node["bind_joint"].as<std::string>()};

        rhs.joints.emplace_back(std::move(joint_node_options));
      }
    }
    return true;
  }
};
}  // namespace YAML

namespace aimrt_mujoco_sim::mujoco_sim_module::subscriber {
void JointActuatorSubscriberBase::SetMj(mjModel* m, mjData* d) {
  m_ = m;
  d_ = d;
}

void JointActuatorSubscriberBase::ApplyCtrlData() {
  auto* current_command_array = command_array_.exchange(nullptr);
  if (current_command_array != nullptr) {
    // new data, update control value
    for (size_t i = 0; i < joint_num_; ++i) {
      d_->ctrl[actuator_addr_vec_[i]] = current_command_array[i];
    }

    delete[] current_command_array;
  }
}

void JointActuatorSubscriberBase::RegisterActuatorAddr() {
  for (auto const& joint : options_.joints) {
    int32_t actuator_id = common::GetJointActIdByJointName(m_, joint.bind_joint).value_or(-1);

    actuator_addr_vec_.emplace_back(actuator_id);
    joint_names_vec_.emplace_back(joint.name);
    joint_actuator_type_vec_.emplace_back(common::GetJointActTypeByJointName(m_, joint.bind_joint).value_or(""));

    auto joint_id = m_->actuator_trnid[static_cast<int32_t>(actuator_id * 2)];
    actuator_bind_joint_sensor_addr_vec_.emplace_back(ActuatorBindJointSensorAddr{
        .pos_addr = m_->jnt_qposadr[joint_id],
        .vel_addr = m_->jnt_dofadr[joint_id],
    });
  }

  joint_num_ = actuator_addr_vec_.size();
}

void JointActuatorSubscriberBase::InitializeBase(YAML::Node options_node) {
  if (options_node && !options_node.IsNull())
    options_ = options_node.as<Options>();

  RegisterActuatorAddr();

  options_node = options_;
}

void HandActuatorSubscriber::Initialize(YAML::Node options_node) {
  command_offset_ = options_node["command_offset"].as<std::vector<double>>();
  command_ratio_ = options_node["command_ratio"].as<std::vector<double>>();

  InitializeBase(options_node);
  AIMRT_CHECK_ERROR_THROW(aimrt::channel::Subscribe<aimdk::protocol::HandCommandChannel>(
                              subscriber_,
                              std::bind(&HandActuatorSubscriber::EventHandle, this, std::placeholders::_1)),
                          "Subscribe failed.");
}
void HandActuatorSubscriber::EventHandle(const std::shared_ptr<const aimdk::protocol::HandCommandChannel>& commands) {
  if (stop_flag_) [[unlikely]]
    return;

  auto* new_command_array = new double[12];
  auto left_finger_pos = commands->data().left().agi_hand().finger().pos();
  auto right_finger_pos = commands->data().right().agi_hand().finger().pos();

  new_command_array[0] = command_offset_[0] + command_ratio_[0] * left_finger_pos.thumb_pos_0();
  new_command_array[1] = command_offset_[1] + command_ratio_[1] * left_finger_pos.thumb_pos_1();
  new_command_array[2] = command_offset_[2] + command_ratio_[2] * left_finger_pos.index_pos();
  new_command_array[3] = command_offset_[3] + command_ratio_[3] * left_finger_pos.middle_pos();
  new_command_array[4] = command_offset_[4] + command_ratio_[4] * left_finger_pos.ring_pos();
  new_command_array[5] = command_offset_[5] + command_ratio_[5] * left_finger_pos.pinky_pos();

  new_command_array[6] = command_offset_[0] + command_ratio_[0] * right_finger_pos.thumb_pos_0();
  new_command_array[7] = command_offset_[1] + command_ratio_[1] * right_finger_pos.thumb_pos_1();
  new_command_array[8] = command_offset_[2] + command_ratio_[2] * right_finger_pos.index_pos();
  new_command_array[9] = command_offset_[3] + command_ratio_[3] * right_finger_pos.middle_pos();
  new_command_array[10] = command_offset_[4] + command_ratio_[4] * right_finger_pos.ring_pos();
  new_command_array[11] = command_offset_[5] + command_ratio_[5] * right_finger_pos.pinky_pos();

  auto* old_command_array = command_array_.exchange(new_command_array);
  delete[] old_command_array;
}

#ifdef AIMRT_MUJOCO_SIM_BUILD_WITH_ROS2
void JointActuatorRos2Subscriber::Initialize(YAML::Node options_node) {
  InitializeBase(options_node);

  AIMRT_CHECK_ERROR_THROW(aimrt::channel::Subscribe<joint_msgs::msg::JointCommand>(
                              subscriber_,
                              std::bind(&JointActuatorRos2Subscriber::EventHandle, this, std::placeholders::_1)),
                          "Subscribe failed.");
}
void JointActuatorRos2Subscriber::EventHandle(const std::shared_ptr<const joint_msgs::msg::JointCommand>& commands) {
  if (stop_flag_) [[unlikely]]
    return;

  auto* new_command_array = new double[joint_num_];

  for (size_t ii = 0; ii < joint_num_; ++ii) {
    const auto& joint_options = options_.joints[ii];
    const auto command = commands->joints[ii];

    auto itr = std::ranges::find(joint_names_vec_, command.name);
    if (itr == joint_names_vec_.end()) [[unlikely]] {
      AIMRT_WARN("Invalid msg for topic '{}', msg: {}, Joint name '{}' is not matched.",
                 subscriber_.GetTopic(), joint_msgs::msg::to_yaml(*commands), command.name);

      delete[] new_command_array;
      return;
    }
    uint32_t joint_idx = std::distance(joint_names_vec_.begin(), itr);

    if (joint_actuator_type_vec_[joint_idx] == "position") {
      new_command_array[joint_idx] = command.position;
    } else if (joint_actuator_type_vec_[joint_idx] == "velocity") {
      new_command_array[joint_idx] = command.velocity;
    } else if (joint_actuator_type_vec_[joint_idx] == "motor") {
      // motor
      double state_posiotin = d_->qpos[actuator_bind_joint_sensor_addr_vec_[joint_idx].pos_addr];
      double state_velocity = d_->qvel[actuator_bind_joint_sensor_addr_vec_[joint_idx].vel_addr];

      new_command_array[joint_idx] = command.effort +
                                     command.stiffness * (command.position - state_posiotin) +
                                     command.damping * (command.velocity - state_velocity);
    } else {
      AIMRT_WARN("Invalid joint actuator type '{}'.", joint_actuator_type_vec_[joint_idx]);
    }
  }

  auto* old_command_array = command_array_.exchange(new_command_array);
  delete[] old_command_array;
}
#endif
}  // namespace aimrt_mujoco_sim::mujoco_sim_module::subscriber