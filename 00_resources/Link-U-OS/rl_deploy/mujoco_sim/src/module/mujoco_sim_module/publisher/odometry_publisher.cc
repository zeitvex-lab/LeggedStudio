// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "tf2_msgs/msg/tf_message.hpp"

#include "mujoco_sim_module/common/xmodel_reader.h"
#include "mujoco_sim_module/publisher/odometry_publisher.h"

namespace YAML {
template <>
struct convert<aimrt_mujoco_sim::mujoco_sim_module::publisher::OdometryRos2Publisher::Options> {
  using Options = aimrt_mujoco_sim::mujoco_sim_module::publisher::OdometryRos2Publisher::Options;
  static Node encode(const Options& rhs) {
    Node node;

    node["bind_site"] = rhs.bind_site;
    node["bind_framequat"] = rhs.bind_framequat;
    node["bind_framepos"] = rhs.bind_framepos;

    return node;
  }

  static bool decode(const Node& node, Options& rhs) {
    if (!node.IsMap()) return false;

    rhs.bind_site = node["bind_site"].as<std::string>();

    if (node["bind_framequat"]) {
      rhs.bind_framequat = node["bind_framequat"].as<std::string>();
    }
    if (node["bind_framepos"]) {
      rhs.bind_framepos = node["bind_framepos"].as<std::string>();
    }

    return true;
  }
};
}  // namespace YAML

namespace aimrt_mujoco_sim::mujoco_sim_module::publisher {
void OdometryRos2Publisher::SetMj(mjModel* m, mjData* d) {
  m_ = m;
  d_ = d;
}

void OdometryRos2Publisher::RegisterSensorAddr() {
  sensor_addr_group_.framequat_addr = common::GetSensorIdBySensorName(m_, options_.bind_framequat).value_or(-1);
  sensor_addr_group_.framepos_addr = common::GetSensorIdBySensorName(m_, options_.bind_framepos).value_or(-1);
}

void OdometryRos2Publisher::CopySensorData(int addr, auto& dest, size_t n) {
  if (addr >= 0) {
    std::memcpy(&dest, &d_->sensordata[addr], n * sizeof(double));
  }
}

void OdometryRos2Publisher::InitializeBase(YAML::Node options_node) {
  if (options_node && !options_node.IsNull())
    options_ = options_node.as<Options>();
  avg_interval_base_ = GetAvgIntervalBase(channel_frq_);
  RegisterSensorAddr();
  options_node = options_;
}

void OdometryRos2Publisher::Initialize(YAML::Node options_node) {
  InitializeBase(options_node);
  AIMRT_CHECK_ERROR_THROW(aimrt::channel::RegisterPublishType<tf2_msgs::msg::TFMessage>(publisher_),
                          "Register publish type failed.");
}

void OdometryRos2Publisher::PublishSensorData() {
  static constexpr uint32_t ONE_MB = 1024 * 1024;
  if (counter_++ < avg_interval_) return;
  auto state_array = std::make_unique<SensorStateGroup>();

  CopySensorData(sensor_addr_group_.framequat_addr, state_array->orientation, 4);
  CopySensorData(sensor_addr_group_.framepos_addr, state_array->position, 3);

  executor_.Execute([this, state_array = std::move(state_array)]() {
    tf2_msgs::msg::TFMessage msg;
    msg.transforms.resize(1);
    msg.transforms[0].header.stamp = rclcpp::Clock().now();
    msg.transforms[0].header.frame_id = "odom";
    msg.transforms[0].child_frame_id = "base_link";
    msg.transforms[0].transform.translation.x = state_array->position.x;
    msg.transforms[0].transform.translation.y = state_array->position.y;
    msg.transforms[0].transform.translation.z = state_array->position.z;
    msg.transforms[0].transform.rotation.x = state_array->orientation.x;
    msg.transforms[0].transform.rotation.y = state_array->orientation.y;
    msg.transforms[0].transform.rotation.z = state_array->orientation.z;
    msg.transforms[0].transform.rotation.w = state_array->orientation.w;
    aimrt::channel::Publish(publisher_, msg);
  });
  avg_interval_ += avg_interval_base_;
  if (counter_ > ONE_MB) {
    avg_interval_ -= ONE_MB;
    counter_ -= ONE_MB;
  }
}
}  // namespace aimrt_mujoco_sim::mujoco_sim_module::publisher