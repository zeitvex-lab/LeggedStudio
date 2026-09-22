// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/interface/i_monitor.h"
#include <nlohmann/json.hpp>

namespace aima::monitor {

class disk_stats : public IMonitor {
 public:
  disk_stats() = default;
  ~disk_stats() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;

 private:
  uint64_t warning_temp_threshold_{100};
  std::string disk_name_{"/dev/nvme0n1"};
  uint64_t last_overtemp_time_{0};
  uint64_t overtemp_duration_threshold_{5000};  // 5 seconds
};

REGISTER_MONITOR_IMPL(disk_stats);
}  // namespace aima::monitor
