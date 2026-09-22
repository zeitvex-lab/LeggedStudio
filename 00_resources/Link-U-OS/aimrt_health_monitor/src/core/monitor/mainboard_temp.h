// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/interface/i_monitor.h"
#include "yaml-cpp/yaml.h"

namespace aima::monitor {
class mainboard_temp : public IMonitor {
 private:
  int mainboard_temp_low_percent_ = 20;

 public:
  mainboard_temp() = default;
  ~mainboard_temp() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  float GetMainboardTemp();
  void DiagnoseOnce() override;
};
// 注册
REGISTER_MONITOR_IMPL(mainboard_temp);
}  // namespace aima::monitor
