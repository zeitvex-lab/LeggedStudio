// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process_manager_proxy.h"

#include "src/process_manager/process_mgr.h"
#include "src/process_manager/process_monitor.h"

#include "src/util/future_multi_thread_mgr.h"
#include "src/util/global.h"

namespace process_manager
{

ProcessManagerProxy::ProcessManagerProxy(std::shared_ptr<ProcessManager> process_mgr, std::shared_ptr<ProcessMonitor> process_monitor)
  : process_manager_(process_mgr),
    process_monitor_(process_monitor) {
}


void ProcessManagerProxy::Shotdown() {
}


ProcessErrorCode ProcessManagerProxy::StartApp(const std::string& name) {
  return process_manager_->StartApp(name);
}

ProcessErrorCode ProcessManagerProxy::StopApp(const std::string& name) {
  return process_manager_->StopApp(name);
}

ProcessErrorCode ProcessManagerProxy::GetAppInfo(const std::string& name, MonitorAppInfo& info) {
  auto ret = process_monitor_->GetAppInfo(name, info);
  if (ret)
    return ProcessErrorCode::SUCCESS;
  else
    return ProcessErrorCode::MONITOR_GAT_APP_INFO_ERROR;
}

ProcessErrorCode ProcessManagerProxy::GetAllAppInfo(std::vector<MonitorAppInfo>& infos) {
  auto ret = process_monitor_->GetAllAppInfo(infos);
  if (ret)
    return ProcessErrorCode::SUCCESS;
  else
    return ProcessErrorCode::MONITOR_GAT_APP_INFO_ERROR;
}

ProcessErrorCode ProcessManagerProxy::StopAllApps() {
  std::vector<MonitorAppInfo> infos;
  // 可能存在使用历史infos数据 进行操作的可能.
  auto ret = process_monitor_->GetAllAppInfo(infos);
  if (!ret) {
    AIMRT_ERROR("Get All app info list is failed.");
    return ProcessErrorCode::MONITOR_GAT_APP_INFO_ERROR;
  }

  FutureMultiThreadMgr mgr;
  for (auto& info : infos) {
    if (info.state == EmAppInfo_State::EmAppInfo_State_State_RUNNING) {
      std::string app_name = info.app_name;
      AIMRT_INFO("aima-cli: Stop App list: {}", info.app_name);
      mgr.PushTask(
        [this, app_name]() -> ProcessErrorCode {
          return process_manager_->StopApp(app_name);
        },
        [app_name, this](ProcessErrorCode code) {
          if (code != ProcessErrorCode::SUCCESS) {
            AIMRT_ERROR("Stop all list: {} failed. {} {}", app_name, code, ProcessErrorCodeToString(code));
          }
        }
      );
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
  }
  mgr.WaitTaskFinish();

  // 默认直接返回成功
  return ProcessErrorCode::SUCCESS;
}

ProcessErrorCode ProcessManagerProxy::SetEnvCfg(const std::string& name, const std::string& key, const std::string& val) {
  return process_manager_->SetEnvCfg(name, key, val);
}

ProcessErrorCode ProcessManagerProxy::ResetApp(const std::string& name) {
  return process_manager_->ResetApp(name);
}

ProcessErrorCode ProcessManagerProxy::GetUnexpectedKillAppList(std::vector<std::string>& list) {
  auto ret = process_monitor_->GetUnexpectedKillAppList(list);
  if (ret)
    return ProcessErrorCode::SUCCESS;
  else
    return ProcessErrorCode::MONITOR_GAT_APP_INFO_ERROR;
}

}
