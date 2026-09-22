// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process_manager_module.h"

#include "src/config_manager/config_mgr.h"
#include "src/process_manager/process_mgr.h"
#include "src/process_manager/process_monitor.h"
#include "process_manager_proxy.h"

#include "src/module/http_server/http_server.h"

#include "src/util/future_multi_thread_mgr.h"
#include "src/util/global.h"

namespace process_manager
{

bool PMModule::Initialize(aimrt::CoreRef core) {
  // Save aimrt framework handle
  core_ = core;
  SetLogger(GetLogger());

  tzset(); /* Populates 'timezone' global.  define in getTimeZone util/localtime.h */

  try {
    // Read cfg
    const aimrt::configurator::ConfiguratorRef configurator = core_.GetConfigurator();
    if (!configurator) {
      AIMRT_INFO("Init failed. Empty module yaml configuration");
      return false;
    }

    YAML::Node cfg_node = YAML::LoadFile(std::string(configurator.GetConfigFilePath()));

    config_mgr_ = std::make_shared<ConfigManager>();
    if (!config_mgr_->LoadProcessManagerCfg(cfg_node)) {
      AIMRT_ERROR("load cfg_node failed. stop");
      return false;
    }

    sm_executor_ = core_.GetExecutorManager().GetExecutor("sm_rpc_worker");

    // init process_manager
    process_manager_ = std::make_shared<ProcessManager>(config_mgr_);
    if (!process_manager_->Init()) {
      return false;
    }

    // init process_monitor
    process_monitor_ = std::make_shared<ProcessMonitor>(process_manager_);

    // init Process_manager proxy
    proxy_ = std::make_shared<ProcessManagerProxy>(process_manager_, process_monitor_);

    // init http_server
    http_server_ = std::make_shared<HttpServer>(config_mgr_, core_, sm_executor_, *proxy_);
    if (!http_server_->Initialize()) {
      return false;
    }

  } catch (const std::exception& e) {
    AIMRT_HL_ERROR(core_.GetLogger(), "Init failed, {}", e.what());
    return false;
  }

  AIMRT_HL_INFO(core_.GetLogger(), "Init succeeded.");

  return true;
}

bool PMModule::Start() {
  if (!http_server_->Start()) {
    return false;
  }

  FutureMultiThreadMgr mgr;
  for (auto & default_app : config_mgr_->GetProcessOption().default_app_list) {
    mgr.PushTask(
      [this, default_app]() -> ProcessErrorCode {
        return process_manager_->StartApp(default_app);
      },
      [default_app, this](ProcessErrorCode code) {
        if (code != ProcessErrorCode::SUCCESS) {
          AIMRT_WARN("Start App: {} failed, error: {}", default_app, code);
        }
      }
    );
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  mgr.WaitTaskFinish();

  process_monitor_->Start();

  AIMRT_INFO("process_manager Started succeeded.");
  return true;
}

void PMModule::Shutdown() {
  if (http_server_) {
    http_server_->Shutdown();
  }

  if (process_monitor_) {
    process_monitor_->Shutdown();
  }

  if (process_manager_) {
    process_manager_->Stop();
  }

  AIMRT_INFO("process_manager module Shutdown succeeded.");
  return;
}

}
