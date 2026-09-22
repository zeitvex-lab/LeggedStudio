// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>
#include <memory>
#include <string>

#include "aimrt_core_plugin_interface/aimrt_core_plugin_base.h"
#include "aimrt_module_cpp_interface/executor/executor.h"
#include "aimrt_module_cpp_interface/executor/timer.h"
#include "core/aimrt_core.h"
#include "data_manager.h"
#include "global.h"
#include "service.h"

namespace aimrt::plugins::viz_plugin {

class AimrtVizPlugin : public aimrt::AimRTCorePluginBase {
 public:
  struct ProcessResourceInfo {
    uint64_t pid;                    // thread ID
    uint64_t mem_usage;              // current process memory usage (kb)
    float mem_usage_ratio;           // current process memory usage ratio
    float cpu_usage_ratio;           // current process CPU usage ratio
    uint64_t thread_count;           // current process thread count
    std::string cpu_sched_policy;    // current process scheduling policy
    int cpu_sched_priority;          // current process scheduling priority
    std::vector<int> bounding_cpus;  // CPUs bound to the current process
  };

  struct Options {
    std::string node_name;
    std::string soc;
    std::string service_name;
    std::string executor;
    uint64_t update_interval_ms = 1000;  // ms
  };

 public:
  std::string_view Name() const noexcept override { return "viz_plugin"; }
  bool Initialize(aimrt::runtime::core::AimRTCore* core_ptr) noexcept override;
  void Shutdown() noexcept override;
  void RegisterRpcService();

 private:
  std::vector<std::function<void()>> pre_start_hook_task_vec_;
  std::shared_ptr<DataManager> data_manager_ptr_;
  std::unique_ptr<VizServiceImpl> viz_service_impl_ptr_;

  executor::ExecutorRef executor_ref_;
  std::shared_ptr<aimrt::executor::TimerBase> update_timer_;

  aimrt::runtime::core::AimRTCore* core_ptr_ = nullptr;
  bool init_flag_ = false;

  Options options_;

 private:
  void Doinit();
};

}  // namespace aimrt::plugins::viz_plugin