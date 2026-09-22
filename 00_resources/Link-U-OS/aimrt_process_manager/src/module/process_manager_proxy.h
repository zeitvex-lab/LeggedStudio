// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>

#include "aimrt_module_cpp_interface/core.h"
#include "aimrt_module_cpp_interface/co/task.h"

#include "src/util/process_error_code.h"

namespace process_manager
{

class ProcessManager;
class ProcessMonitor;

class MonitorAppInfo;

class ProcessManagerProxy
{
 public:
  ProcessManagerProxy(std::shared_ptr<ProcessManager> process_mgr, std::shared_ptr<ProcessMonitor> process_monitor);
  ~ProcessManagerProxy() = default;

  void Shotdown();

  ProcessErrorCode StartApp(const std::string& name);
  ProcessErrorCode StopApp(const std::string& name);

  ProcessErrorCode GetAppInfo(const std::string& name, MonitorAppInfo& info);
  ProcessErrorCode GetAllAppInfo(std::vector<MonitorAppInfo>& infos);

  ProcessErrorCode StopAllApps();

  ProcessErrorCode SetEnvCfg(const std::string& name, const std::string& key, const std::string& val);

  ProcessErrorCode ResetApp(const std::string& name);

  ProcessErrorCode GetUnexpectedKillAppList(std::vector<std::string>& list);

 private:
  std::shared_ptr<ProcessManager> process_manager_;
  std::shared_ptr<ProcessMonitor> process_monitor_;
};

}
