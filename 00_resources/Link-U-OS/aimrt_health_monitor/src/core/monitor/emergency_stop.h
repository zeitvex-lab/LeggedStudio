// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/interface/i_monitor.h"

namespace aima::monitor {
class EmergencyStop : public IMonitor {
 private:
  std::string estop_reason_ = "unknown";
  std::atomic_bool is_estop_ = false;
  std::atomic_bool crash_bar_trigger_{false};

 public:
  EmergencyStop() = default;
  ~EmergencyStop() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;
};
REGISTER_MONITOR_IMPL(EmergencyStop);
}  // namespace aima::monitor
