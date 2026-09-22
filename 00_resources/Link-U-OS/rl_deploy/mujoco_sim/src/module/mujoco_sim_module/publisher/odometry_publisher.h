// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include "mujoco_sim_module/global.h"
#include "mujoco_sim_module/publisher/publisher_base.h"
#include "mujoco_sim_module/publisher/utils.h"

#include "aimrt_module_ros2_interface/channel/ros2_channel.h"

namespace aimrt_mujoco_sim::mujoco_sim_module::publisher {

class OdometryRos2Publisher : public PublisherBase {
 public:
  struct Options {
    std::string bind_site;
    std::string bind_framequat;
    std::string bind_framepos;
  };

  OdometryRos2Publisher() = default;
  ~OdometryRos2Publisher() override = default;

  void Initialize(YAML::Node options_node) override;
  std::string_view Type() const noexcept override { return "odometry_ros2"; }
  void PublishSensorData() override;

  void SetMj(mjModel* m, mjData* d) override;
  void Start() override {}
  void Shutdown() override {}

  void SetPublisherHandle(aimrt::channel::PublisherRef publisher_handle) override { publisher_ = publisher_handle; }
  void SetExecutor(aimrt::executor::ExecutorRef executor) override { executor_ = executor; };
  void SetFreq(uint32_t freq) override { channel_frq_ = freq; };

 protected:
  void InitializeBase(YAML::Node options_node);
  void RegisterSensorAddr();
  void CopySensorData(int addr, auto& dest, size_t n);

  struct SensorAddrGroup {
    int32_t framequat_addr;
    int32_t framepos_addr;
  };

  struct SensorStateGroup {
    struct {
      double w, x, y, z;
    } orientation;
    struct {
      double x, y, z;
    } position;
  };

  Options options_;
  mjModel* m_ = nullptr;
  mjData* d_ = nullptr;
  aimrt::channel::PublisherRef publisher_;
  aimrt::executor::ExecutorRef executor_;
  uint32_t channel_frq_ = 1000;
  double avg_interval_base_ = 1.0;
  double avg_interval_ = 0;
  uint32_t counter_ = 0;
  SensorAddrGroup sensor_addr_group_;
};
}  // namespace aimrt_mujoco_sim::mujoco_sim_module::publisher