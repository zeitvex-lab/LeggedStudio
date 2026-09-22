// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/interface/i_monitor.h"
#include "src/core/res.h"
#include "src/module/module_base.h"

#include <unordered_map>

namespace aima::monitor {
class HealthMonitorModule : public aimrte::ctx::ModuleBase {
 protected:
  void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override;
  bool OnInitialize() override;
  bool OnStart() override;
  void OnShutdown() override;

 private:
  YAML::Node config_;
  Res res_;
  std::unordered_map<std::string, std::unique_ptr<IMonitor>> monitor_map_;
  aimrt::co::AsyncScope scope_;
};
}
