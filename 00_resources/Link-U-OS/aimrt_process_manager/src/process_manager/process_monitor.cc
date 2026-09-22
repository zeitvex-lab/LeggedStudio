// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process_monitor.h"

#include "process_mgr.h"
#include "src/util/global.h"
#include "src/util/session_util.h"
#include "src/util/process_state.h"

namespace process_manager
{

ProcessMonitor::ProcessMonitor(std::shared_ptr<ProcessManager> process_manager)
  : process_manager_(process_manager),
    process_name_to_data_map_(process_manager->GetProcessDataMap())
{
}


bool ProcessMonitor::Start() {
  stop_.store(false);
  monitor_thread_ = std::make_shared<std::thread>(std::thread([this]() { MonitorLoop(); }));
  return true;
}

bool ProcessMonitor::Shutdown() {
  stop_.store(true);
  if (monitor_thread_) {
    if (monitor_thread_->joinable()) {
      monitor_thread_->join();
    }
    monitor_thread_.reset();
  }
  return true;
}

bool ProcessMonitor::GetAppInfo(const std::string& app_name, MonitorAppInfo& rsp) {
  auto iter = process_name_to_data_map_.find(app_name);
  if (iter == process_name_to_data_map_.end()) {
    AIMRT_ERROR("invalid app_name: {}", app_name);
    return false;
  }

  LOCK(iter->second->data_mutex_);
  rsp.app_name = app_name;
  rsp.pid = iter->second->GetAppPid();
  rsp.state = iter->second->GetProcessStatus();
  rsp.time_stamp = iter->second->GetStartTimeStamp();
  rsp.from_reload = iter->second->GetReloadFlag();
  return true;
}

bool ProcessMonitor::GetAllAppInfo(std::vector<MonitorAppInfo>& rsp) {
  for (const auto& [name, ptr] : process_name_to_data_map_) {
    LOCK(ptr->data_mutex_);
    MonitorAppInfo info;
    info.app_name = name;
    info.pid = ptr->GetAppPid();
    info.state = ptr->GetProcessStatus();
    info.time_stamp = ptr->GetStartTimeStamp();
    info.from_reload = ptr->GetReloadFlag();
    rsp.emplace_back(std::move(info));
  }
  return true;
}

bool ProcessMonitor::GetUnexpectedKillAppList(std::vector<std::string>& list) {
  for (const auto& [name, ptr] : process_name_to_data_map_) {
    LOCK(ptr->data_mutex_);
    if (EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS == ptr->GetProcessStatus()) {
      list.emplace_back(name);
    }
  }
  return true;
}

void ProcessMonitor::MonitorLoop() {
  // 只处理 running -> idel 的流转
  while (!stop_.load()) {
    for (const auto& [str, ptr] : process_name_to_data_map_) {
      // 短暂停顿
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
      LOCK(ptr->data_mutex_);
      if (EmAppInfo_State::EmAppInfo_State_State_RUNNING == ptr->GetProcessStatus()) {
        int app_pid = ptr->GetAppPid();
        if (!SessionUtil::ProcessExists(str, app_pid, ptr->GetProcessStartTime())) {
          AIMRT_WARN("[{}]: app_id is lost, maybe process is killed. {}", str, app_pid);
          // 发现意外被kill, 只标记, 不进行状态清理, 保持和之前旧的版本, 监控逻辑一致
          ptr->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS);
          ptr->RemoveProcessStateFile();
        }
      }
    }
    std::this_thread::sleep_for(std::chrono::seconds(5));
  }
}

}
