// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <mutex>

#include "src/config_manager/config_mgr.h"
#include "src/util/process_error_code.h"

#include "executor.h"
#include "src/util/domain_socket.h"
#include "src/util/domain_socket_channel.h"
#include "src/util/global.h"
#include "src/util/util_func.h"
#include "src/util/session_util.h"
#include "src/util/process_state.h"

#include "aimdk/protocol/em/api.pb.h"

namespace process_manager
{

#define LOCK(mutex) std::lock_guard<decltype(mutex)> _(mutex)

class DomainSocketChannel;

class ProcessData
{
 public:
  ProcessData(const AppInfo& app_info, const EnvVar& env_var);

  ~ProcessData() {}

  // Before Start APP
  void Init();

  // 重置进程运行期间的数据
  void ResetRunningData();

  // 重置启动过程的数据, 启动结束就需要立即清理
  void ResetStartupData();

  bool UpdateExecutorEnvCfg(const std::string& key, const std::string& val) { return executor_->UpdateEnvCfg(key, val); }


  // Update
  void SetProcessStatus(EmAppInfo_State status, bool update_time = true);

  void SetProcessErrorCode(ProcessErrorCode code) { error_code_ = code; }

  void SetIntermediatePid(int pid) { intermediate_pid_.store(pid); }

  void SetReloadFlag(bool flag) { from_reload_.store(flag); }

  bool SaveProcessStateFile();

  bool RemoveProcessStateFile();

  // use in reload
  void SetAppPid(int pid) { app_pid_.store(pid); }

  void SetTimeStamp(uint64_t time) {  start_time_stamp_.store(time); }

  void SetProcessStartTime(uint64_t time) { process_start_time_.store(time); }

  // Get
  EmAppInfo_State GetProcessStatus() { return status_; }

  ProcessErrorCode GetProcessErrorCode() { return error_code_; }

  uint64_t GetStartTimeStamp() { return start_time_stamp_.load(); }

  int GetAppPid() { return app_pid_.load(); }

  int GetIntermediatePid() { return intermediate_pid_.load(); }

  bool GetReloadFlag() { return from_reload_.load(); }

  uint64_t GetProcessStartTime() { return process_start_time_.load(); }

 public:
  void RecvDomainSocketData(const DomainSocketStruct* st);

  ProcessErrorCode WatchStartSuccessFlag(int timeout_ms);

  std::string CreateProcessStateStr();

 public:
  const AppInfo& app_info_;
  const EnvVar env_list_;

  // 用于锁定所有对于 EmAppInfo_State 变量的读写
  std::mutex data_mutex_;

  std::shared_ptr<DomainSocketChannel> domain_socket_channel_;
  std::shared_ptr<Executor> executor_;

  // domain_socket channel data:
  const std::string app_start_success_str_{"SUCCESS"};
  const std::string app_start_failed_str_{"FAILED"};

 private:
  std::atomic<int> intermediate_pid_{-1};

  // domain_socket channel data:
  std::atomic<int> app_pid_{-1};

  std::atomic<bool> recv_start_success_flag_{false};
  std::atomic<bool> recv_start_failed_flag_{false};

  // 所有对 status_ 的操作都必须加锁
  EmAppInfo_State status_{EmAppInfo_State::EmAppInfo_State_State_IDLE};
  ProcessErrorCode error_code_{ProcessErrorCode::SUCCESS};

  // start time stamp, 用于 aima-cli 展示
  std::atomic<uint64_t> start_time_stamp_{0};

  std::atomic<bool> from_reload_{false};

  // 记录 /proc/xxx/stat 里面的starttime, 用于判断进程是否存在
  std::atomic<uint64_t> process_start_time_{0};
};

}
