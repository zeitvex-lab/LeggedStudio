// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <iostream>
#include "src/core/interface/i_monitor.h"

namespace aima::monitor {

struct NET_IO_COUNTER {
  char name[32];                                      // 网卡名称
  uint64_t download_bytes;                            // 下行字节数
  uint64_t upload_bytes;                              // 上行字节数
  std::chrono::steady_clock::time_point steady_time;  // 记录的时间戳
};

class network : public IMonitor {
 private:
  void get_net_counter(std::map<std::string, NET_IO_COUNTER>& net_interfaces);
  std::pair<double, double> cal_up_down_speed(const NET_IO_COUNTER& c1, const NET_IO_COUNTER& c2);
  bool GetNetworkStatus() const;

  std::map<std::string, NET_IO_COUNTER> network_last_;
  std::map<std::string, NET_IO_COUNTER> network_current_;

  std::optional<bool> last_network_status_{false};

 public:
  network() = default;
  ~network() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;
  void PubNetworkData(const aimdk::protocol::NetworkUsage& msg);
};

REGISTER_MONITOR_IMPL(network);

}  // namespace aima::monitor
