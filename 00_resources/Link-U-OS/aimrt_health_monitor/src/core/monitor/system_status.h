// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "aimdk/protocol/hds/system_status.pb.h"
#include "src/core/interface/i_monitor.h"
#include "src/ctx/ctx.h"
#include "src/prelude/prelude.h"

namespace aima::monitor {
class system_status : public IMonitor {
 public:
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;

  void DiagnoseOnce() override;

 private:
  void UpdateSystemStatus(const aimdk::protocol::SystemStatusChannel& msg);
  // 上报云端各资源状态
  void ReportCpuUsage();
  void ReportGpuUsage();
  void ReportMemoryUsage();
  void ReportDiskUsage();
  void ReportProcessState();

  aimdk::protocol::SystemStatusChannel system_status_;
  size_t event_counter_{0};
};

REGISTER_MONITOR_IMPL(system_status);

}  // namespace aima::monitor