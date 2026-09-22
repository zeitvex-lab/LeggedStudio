// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <sys/types.h>
#include <string>
#include <vector>
#include "src/core/interface/i_monitor.h"

namespace aima::monitor {

class ProcessInfo {
 public:
  ProcessInfo(const std::string& app_name, const std::string& pid);
  ~ProcessInfo() = default;

  int32_t GetGuardThreadTid(std::string &name);
  std::string GetAppName() const;
  std::string GetPid() const;

  uint64_t GetMemoryUsageKb();
  uint64_t GetMemoryTotal();
  float GetMemoryUsagePercent();
  uint64_t GetThreadCount();
  float GetCpuUsagePercent();
  int32_t GetSchedulerPriority();

 private:
  int64_t prev_utime_ = -1, prev_stime_ = -1;
  int64_t last_time_ = 0;
  std::string app_name_;
  std::string pid_;
  uint64_t mem_total_ = 0;
};

class process : public IMonitor {
 public:
  process() = default;
  ~process() = default;

  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;
  void PubProcessData(const aimdk::protocol::ProcessList& msg);

private:
  std::vector<std::string> app_names_;
  std::vector<ProcessInfo> app_infos_;
};

REGISTER_MONITOR_IMPL(process);

}  // namespace aima::monitor