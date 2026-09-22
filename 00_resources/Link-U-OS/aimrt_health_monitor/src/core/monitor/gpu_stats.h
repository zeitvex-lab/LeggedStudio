// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/interface/i_monitor.h"

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
// do nothing for x86_64
#else

namespace aima::monitor {

using GPUPowerMode = aimdk::protocol::GPUPowerMode;
struct GpuStatsInfo {
  float gpu_usage;
  float gpu_mem_usage;
  float gpu_temp;
  GPUPowerMode gpu_power_mode;
};

class gpu_stats : public IMonitor {
 private:
  void get_gpu_info(GpuStatsInfo& gpu_info);
  float get_gpu_usage(const std::string& tegrastats_str);
  float get_gpu_mem_usage(const std::string& tegrastats_str);
  float get_gpu_temp(const std::string& tegrastats_str);
  GPUPowerMode get_gpu_power_mode(const std::string& tegrastats_str);

  GpuStatsInfo gpu_current_;

 public:
  gpu_stats() = default;
  ~gpu_stats() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;

  void PubGpuData(const aimdk::protocol::GpuUsage& msg);
  int ExecuteCmd(const std::string &cmd, std::string &result);
};

REGISTER_MONITOR_IMPL(gpu_stats);
}  // namespace aima::monitor

#endif    // __x86_64__ || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
