// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <iostream>
#include "src/core/interface/i_monitor.h"

namespace aima::monitor {

class memory : public IMonitor {
 private:
  float max_usage_{90};

 private:
  const std::tuple<int, int, int, int> get_memory_usage();

 public:
  memory() = default;
  ~memory() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;

  void PubMemData(const aimdk::protocol::MemoryUsage& msg);
};
REGISTER_MONITOR_IMPL(memory);
}  // namespace aima::monitor
