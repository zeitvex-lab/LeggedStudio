// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>

#include "aimdk/protocol/hds/process/process_heartbeat_channel.pb.h"
#include "src/interface/aimrt_core_plugin_interface/aimrt_core_plugin_base.h"
#include "src/ctx/ctx.h"
#include "plugin/common/core_proxy.h"
#include <thread>
#include "./data_manager.h"

namespace aimrte::plugin::monitor
{
class MonitorPlugin : public aimrt::AimRTCorePluginBase
{
 public:
  struct Options {
    std::string executor{"default_monitor_executor"};
    std::string node_name{"anonymity"};
  };

  struct ProcessResourceInfo {
    uint64_t pid;                    // 进程ID
    uint64_t mem_usage;              // 当前进程内存使用量(kb)
    float mem_usage_ratio;           // 当前进程内存使用率
    float cpu_usage_ratio;           // 当前进程cpu使用率
    uint64_t thread_count;           // 当前进程线程数
    std::string cpu_sched_policy;    // 当前进程调度策略
    int cpu_sched_priority;          // 当前进程调度优先级
    std::vector<int> bounding_cpus;  // 当前进程绑定的cpu
  };

  std::unordered_map<std::string, std::string> plugin_cfg_;

 private:
  aimrt::runtime::core::AimRTCore* core_ptr_ = nullptr;
  std::shared_ptr<aimrte::core::Context> ctx_ptr_;
  std::atomic_bool runFlag_{false};
  aimrt::CoreRef core_ref_;
  DataManager data_manager_;
  Options options_;
  std::shared_ptr<CoreProxy> core_proxy_;
  ctx::Executor executor_;
  ctx::Publisher<aimdk::protocol::ProcessHeartbeatChannel> heartbeat_publisher_;

  ProcessResourceInfo self_process_res_info_;
  std::mutex self_process_res_info_mutex_;

 private:
  void RegisterMonitorChannelBackend();
  void RegisterMonitorRpcBackend();
  void RegisterChannelFilter();
  void RegisterRpcFilter();
  void DoInitliaze();

  aimrt::co::Task<void> HeartBeat();
  aimrt::co::Task<void> CollectResourceInfo();

 public:
  MonitorPlugin(/* args */) = default;
  ~MonitorPlugin() override = default;
  std::string_view Name() const noexcept override { return "monitor_plugin"; }
  bool Initialize(aimrt::runtime::core::AimRTCore* core_ptr) noexcept override;
  void Shutdown() noexcept override;
};

}  // namespace aimrte::plugin::monitor
