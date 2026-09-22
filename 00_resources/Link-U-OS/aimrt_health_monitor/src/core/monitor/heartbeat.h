// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/interface/i_monitor.h"
#include <mutex>
#include <unordered_map>

namespace aima::monitor {
class heartbeat : public IMonitor {
 public:
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;

  void DiagnoseOnce() override;
  void PubAppHeartbeat(const aimdk::protocol::AppHeartBeatList &msg);

  uint8_t ShcedPolicy(const std::string &policy);

 private:
  std::mutex mutex_;
  std::unordered_map<std::string, std::shared_ptr<aimdk::protocol::ProcessHeartbeatChannel>> heartbeats_;   // node_name => heartbeat
};

REGISTER_MONITOR_IMPL(heartbeat);

}   // namespace aima::monitor
