// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "i_monitor.h"

namespace aima::monitor {
bool IMonitor::Initialize(const YAML::Node& config, Res& res)
{
  rate_ = config["rate"].as<float>();
  name_ = config["name"].as<std::string>();
  res_ = res;
  return Initialize(config["params"]);
}

float IMonitor::GetRate() const { return rate_; }

std::string IMonitor::GetName() const { return name_; }

MonitorRegister* MonitorRegister::Instance() {
  static MonitorRegister instance;
  return &instance;
}
}  // namespace aima::monitor