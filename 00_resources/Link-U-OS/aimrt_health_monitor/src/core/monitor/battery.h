// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "aimdk/protocol/hal/bms/hal_bms_channel.pb.h"
#include "src/core/interface/i_monitor.h"
#include "yaml-cpp/yaml.h"
namespace aima::monitor {
class battery : public IMonitor {
 private:
  int battery_low_percent_ = 30;
  int battery_low_2_percent_ = 15;
  int battery_low_limit_percent_ = 5;

  std::shared_mutex r_w_mutex_;
  std::shared_ptr<const aimdk::protocol::BmsStateChannel> last_battery_info_ = nullptr;

 public:
  battery() = default;
  ~battery() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;
  void PubBatteryData(const std::shared_ptr<const aimdk::protocol::BmsStateChannel>& msg);
};
// 注册
REGISTER_MONITOR_IMPL(battery);
}  // namespace aima::monitor
