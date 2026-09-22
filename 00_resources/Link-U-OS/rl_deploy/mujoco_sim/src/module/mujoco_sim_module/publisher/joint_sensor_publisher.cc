// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "mujoco_sim_module/publisher/joint_sensor_publisher.h"
#include <joint_msgs/msg/detail/joint_state__struct.hpp>
#include "mujoco_sim_module/common/xmodel_reader.h"

namespace YAML {
template <>
struct convert<aimrt_mujoco_sim::mujoco_sim_module::publisher ::JointSensorPublisherBase::Options> {
  using Options = aimrt_mujoco_sim::mujoco_sim_module::publisher ::JointSensorPublisherBase::Options;

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
        auto joint_node_options = Options::Joint();
        joint_node_options.name = joint_node["name"].as<std::string>();
        joint_node_options.bind_joint = joint_node["bind_joint"].as<std::string>();

        rhs.joints.emplace_back(std::move(joint_node_options));
      }
    }
    return true;
  }
};
}  // namespace YAML

namespace aimrt_mujoco_sim::mujoco_sim_module::publisher {

void JointSensorPublisherBase ::SetMj(mjModel* m, mjData* d) {
  m_ = m;
  d_ = d;
}

void JointSensorPublisherBase::RegisterSensorAddr() {
  for (const auto& joint : options_.joints) {
    sensor_addr_vec_.emplace_back(SensorAddrGroup{
        .jointpos_addr = common::GetJointposIdByJointName(m_, joint.bind_joint).value_or(-1),
        .jointvel_addr = common::GetJointvelIdByJointName(m_, joint.bind_joint).value_or(-1),
        .jointactuatorfrc_addr = common::GetJointactfrcIdByJointName(m_, joint.bind_joint).value_or(-1)});

    name_vec_.emplace_back(joint.name);
  }

  joint_num_ = sensor_addr_vec_.size();
}

void JointSensorPublisherBase::InitializeBase(YAML::Node options_node) {
  if (options_node && !options_node.IsNull())
    options_ = options_node.as<Options>();

  avg_interval_base_ = GetAvgIntervalBase(channel_frq_);

  RegisterSensorAddr();

  options_node = options_;
}

void HandSensorPublisher::Initialize(YAML::Node options_node) {
  state_offset_ = options_node["state_offset"].as<std::vector<double>>();
  state_ratio_ = options_node["state_ratio"].as<std::vector<double>>();

  InitializeBase(options_node);

  AIMRT_CHECK_ERROR_THROW(aimrt::channel::RegisterPublishType<aimdk::protocol::HandStateChannel>(publisher_),
                          "Register publish type failed.");
}

void HandSensorPublisher::PublishSensorData() {
  static constexpr uint32_t ONE_MB = 1024 * 1024;

  if (counter_++ < avg_interval_) return;

  std::unique_ptr<SensorStateGroup[]> state_array(new SensorStateGroup[joint_num_]);

  // if not define specific sensor , its value is set to 0.0
  for (size_t i = 0; i < joint_num_; i++) {
    const auto& addr = sensor_addr_vec_[i];
    state_array[i].jointpos_state = addr.jointpos_addr >= 0 ? d_->sensordata[addr.jointpos_addr] : 0.0;
    state_array[i].jointvel_state = addr.jointvel_addr >= 0 ? d_->sensordata[addr.jointvel_addr] : 0.0;
    state_array[i].jointactuatorfrc_state = addr.jointactuatorfrc_addr >= 0 ? d_->sensordata[addr.jointactuatorfrc_addr] : 0.0;
  }

  executor_.Execute([this, state_array = std::move(state_array)]() {
    aimdk::protocol::HandStateChannel hand_state;

    auto left = hand_state.mutable_data()->mutable_left()->mutable_agi_hand()->mutable_finger()->mutable_pos();
    auto right = hand_state.mutable_data()->mutable_right()->mutable_agi_hand()->mutable_finger()->mutable_pos();

    left->set_thumb_pos_0(state_offset_[0] + state_ratio_[0] * state_array[0].jointpos_state);
    left->set_thumb_pos_1(state_offset_[1] + state_ratio_[1] * state_array[1].jointpos_state);
    left->set_index_pos(state_offset_[2] + state_ratio_[2] * state_array[2].jointpos_state);
    left->set_middle_pos(state_offset_[3] + state_ratio_[3] * state_array[3].jointpos_state);
    left->set_ring_pos(state_offset_[4] + state_ratio_[4] * state_array[4].jointpos_state);
    left->set_pinky_pos(state_offset_[5] + state_ratio_[5] * state_array[5].jointpos_state);

    right->set_thumb_pos_0(state_offset_[0] + state_ratio_[0] * state_array[6].jointpos_state);
    right->set_thumb_pos_1(state_offset_[1] + state_ratio_[1] * state_array[7].jointpos_state);
    right->set_index_pos(state_offset_[2] + state_ratio_[2] * state_array[8].jointpos_state);
    right->set_middle_pos(state_offset_[3] + state_ratio_[3] * state_array[9].jointpos_state);
    right->set_ring_pos(state_offset_[4] + state_ratio_[4] * state_array[10].jointpos_state);
    right->set_pinky_pos(state_offset_[5] + state_ratio_[5] * state_array[11].jointpos_state);

    aimrt::channel::Publish(publisher_, hand_state);
  });

  avg_interval_ += avg_interval_base_;

  // avoid overflow
  if (counter_ > ONE_MB) {
    avg_interval_ -= ONE_MB;
    counter_ -= ONE_MB;
  }
}

#ifdef AIMRT_MUJOCO_SIM_BUILD_WITH_ROS2
void JointSensorRos2Publisher::Initialize(YAML::Node options_node) {
  InitializeBase(options_node);

  AIMRT_CHECK_ERROR_THROW(aimrt::channel::RegisterPublishType<joint_msgs::msg::JointState>(publisher_),
                          "Register publish type failed.");
}

void JointSensorRos2Publisher::PublishSensorData() {
  static constexpr uint32_t ONE_MB = 1024 * 1024;

  if (counter_++ < avg_interval_) return;

  std::unique_ptr<SensorStateGroup[]> state_array(new SensorStateGroup[joint_num_]);

  // if not define specific sensor , its value is set to 0.0
  for (size_t i = 0; i < joint_num_; i++) {
    const auto& addr = sensor_addr_vec_[i];
    state_array[i].jointpos_state = addr.jointpos_addr >= 0 ? d_->sensordata[addr.jointpos_addr] : 0.0;
    state_array[i].jointvel_state = addr.jointvel_addr >= 0 ? d_->sensordata[addr.jointvel_addr] : 0.0;
    state_array[i].jointactuatorfrc_state = addr.jointactuatorfrc_addr >= 0 ? d_->sensordata[addr.jointactuatorfrc_addr] : 0.0;
  }

  executor_.Execute([this, state_array = std::move(state_array)]() {
    joint_msgs::msg::JointState joint_state;

    auto timestamp = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    joint_state.header.stamp.sec = timestamp / 1e9;
    joint_state.header.stamp.nanosec = timestamp % static_cast<uint64_t>(1e9);
    joint_state.header.frame_id = "joint_sensor_ros2";

    joint_state.joints.resize(joint_num_);
    for (int i = 0; i < joint_num_; ++i) {
      joint_msgs::msg::State state;
      state.name = name_vec_[i];
      state.position = state_array[i].jointpos_state;
      state.velocity = state_array[i].jointvel_state;
      state.effort = state_array[i].jointactuatorfrc_state;
      joint_state.joints[i] = state;
    }

    aimrt::channel::Publish(publisher_, joint_state);
  });

  avg_interval_ += avg_interval_base_;

  // avoid overflow
  if (counter_ > ONE_MB) {
    avg_interval_ -= ONE_MB;
    counter_ -= ONE_MB;
  }
}
#endif
}  // namespace aimrt_mujoco_sim::mujoco_sim_module::publisher