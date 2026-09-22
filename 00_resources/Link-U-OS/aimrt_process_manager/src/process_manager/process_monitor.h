// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <thread>
#include <chrono>
#include <map>

#include "aimdk/protocol/em/api.aimrt_rpc.pb.h"
#include "aimdk/protocol/em/api.pb.h"

#include "process_data.h"
#include "src/util/process_state.h"

namespace process_manager
{

struct MonitorAppInfo{
  std::string app_name;
  int32_t pid;
  EmAppInfo_State state;
  uint64_t time_stamp;
  bool from_reload;
};

class ProcessData;
class ProcessManager;

class ProcessMonitor
{
 public:
  ProcessMonitor(std::shared_ptr<ProcessManager> process_manager);

  ~ProcessMonitor() {}

  bool Start();

  bool Shutdown();

  bool GetAppInfo(const std::string& app_name, MonitorAppInfo& rsp);

  bool GetAllAppInfo(std::vector<MonitorAppInfo>& rsp);

  bool GetUnexpectedKillAppList(std::vector<std::string>& list);

 private:
  void MonitorLoop();

 private:

  std::shared_ptr<ProcessManager> process_manager_;
  const std::map<std::string, std::shared_ptr<ProcessData>>& process_name_to_data_map_;

  std::atomic<bool> stop_{false};
  std::shared_ptr<std::thread> monitor_thread_;
};

}
