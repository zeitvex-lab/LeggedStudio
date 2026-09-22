// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <sys/types.h>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>

#include "global.h"
#include "util.h"

namespace aimrt::plugins::viz_plugin {

class ProcessInfoManager {
 public:
  void Initialize(std::string pid);
  void DoUpdate(NodeDynamicInfo &node_dynamic_info);
  int32_t GetGuardThreadTid(std::string &name);

 private:
  uint64_t GetMemoryUsageKb();
  uint64_t GetMemoryTotal();
  uint64_t GetThreadCount();
  float GetCpuUsagePercent();
  int32_t GetSchedulerPriority();

 private:
  int64_t prev_utime_ = -1, prev_stime_ = -1;
  int64_t last_time_ = 0;
  std::string pid_;
  uint64_t mem_total_ = 0;
};

}  // namespace aimrt::plugins::viz_plugin