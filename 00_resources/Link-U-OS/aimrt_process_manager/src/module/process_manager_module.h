// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "yaml-cpp/yaml.h"

#include "aimrt_module_cpp_interface/module_base.h"

#include "aimrt_module_cpp_interface/executor/executor.h"
#include "aimrt_module_c_interface/module_base.h"

#include "net/asio_tools.h"

namespace process_manager
{

class ConfigManager;
class ProcessManager;
class ProcessMonitor;
class HttpServer;
class ProcessManagerProxy;

class PMModule : public aimrt::ModuleBase
{
 public:
  PMModule() = default;
  ~PMModule() = default;

  aimrt::ModuleInfo Info() const override
  {
    return aimrt::ModuleInfo{.name = module_name_};
  }

  bool Initialize(aimrt::CoreRef core) override;

  bool Start() override;

  void Shutdown() override;

 private:
  aimrt::logger::LoggerRef GetLogger() { return core_.GetLogger(); }

 private:
  aimrt::CoreRef core_;
  aimrt::executor::ExecutorRef sm_executor_;

  std::shared_ptr<ConfigManager> config_mgr_;
  std::shared_ptr<ProcessManager> process_manager_;
  std::shared_ptr<ProcessMonitor> process_monitor_;

  std::shared_ptr<ProcessManagerProxy> proxy_;
  std::shared_ptr<HttpServer> http_server_;

  const std::string module_name_{"PMModule"};

};

}
