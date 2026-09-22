// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process_mgr.h"

#include <fstream>
#include <sstream>
#include <iostream>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include <poll.h>
#include <errno.h>

#include <future>

#include "src/config_manager/config_mgr.h"
#include "src/util/process_error_code.h"
#include "executor.h"
#include "process_monitor.h"

#include "src/util/session_util.h"
#include "src/util/process_log.h"
#include "src/util/util_func.h"
#include "src/util/localtime.h"
#include "src/util/future_multi_thread_mgr.h"

namespace process_manager
{

bool ProcessManager::Init() {
  g_std_log_enable = config_mgr_->GetWorkOption().std_safe_log_enable;
  g_max_std_log_num = config_mgr_->GetWorkOption().max_std_safe_log_num;
  g_std_log_name = generate_dated_filename();
  AIMRT_INFO("create std_log: {}", g_std_log_name);

  if (!CreateFileDir(g_domain_socket_path) || !CreateFileDir(g_reload_process_path)) {
    AIMRT_ERROR("create base dir failed.");
    return false;
  }

  // 初始化时区偏移量, 应该为 -28800, 即东8区
  g_timezone = getTimeZone();
  AIMRT_INFO("g_timezone: {}", g_timezone);

  auto run_func = [this] {
    pthread_setname_np(pthread_self(), "domain_socket_io");
    try {
      io_ctx_ptr_->run();
    } catch (const std::exception& e) {
      AIMRT_ERROR("io_ctx run failed. {}", e.what());
    }
  };

  for (int32_t ii = 0; ii < config_mgr_->GetWorkOption().domain_socket_thread_num; ++ii) {
    threads_.emplace_back(run_func);
  }

  for (const auto& [app_name, app_info]: config_mgr_->GetProcessOption().app_name_to_info_map) {
    auto process_data = std::make_shared<ProcessData>(app_info, config_mgr_->GetEnv());
    process_data->domain_socket_channel_ =
      std::make_shared<DomainSocketChannel>(*io_ctx_ptr_, app_name, std::bind(&ProcessData::RecvDomainSocketData, process_data.get(), std::placeholders::_1));
    process_data->Init();

    process_name_to_data_map_[app_name] = std::move(process_data);
  }

  LoadProcessStateFile();

  // 清理旧的 log domain_socket 文件
  std::filesystem::path log_ds_file_path(g_domain_socket_path + "/" + g_logger_socket_name);
  if (std::filesystem::exists(log_ds_file_path)) {
    std::filesystem::remove(log_ds_file_path);
  }

  g_process_manager_pid = getpid();
  g_log_server_ptr = std::make_shared<Server>(*io_ctx_ptr_, log_ds_file_path.string(), g_logger_socket_name);
  g_log_server_ptr->StartDaemonAccept(std::bind(&ProcessSimpleLogger::CollectLog, std::placeholders::_1));

  running_.store(true);

  return true;
}

void ProcessManager::Stop() {
  // 正常退出前, 关闭所有进程
  // StopAllProcess();

  running_.store(false);
  work_guard_.reset();

  io_ctx_ptr_->stop();
  AIMRT_INFO("Begin Stop log server...");
  g_log_server_ptr->Stop();
  AIMRT_INFO("Finish Stop log server...");

  for (auto& pair : process_name_to_data_map_) {
    pair.second->ResetRunningData();
  }
  process_name_to_data_map_.clear();
  AIMRT_INFO("Finish Stop data_map...");

  for (auto itr = threads_.begin(); itr != threads_.end();) {
    if (itr->joinable()) itr->join();
    threads_.erase(itr++);
  }
  AIMRT_INFO("Finish Stop...");
}

/**
 * 错误日志的打印和设置返回错误码, 建议尽可能放在一起, 同 StopApp
*/
ProcessErrorCode ProcessManager::StartApp(const std::string& app_name) {
  auto iter = process_name_to_data_map_.find(app_name);
  if (iter == process_name_to_data_map_.end()) {
    AIMRT_ERROR("[{}]: unknown app_name in start_app", app_name);
    return ProcessErrorCode::UNKNOWN_APP_NAME;
  }

  auto process_data = iter->second;

  {
    LOCK(process_data->data_mutex_);
    switch(process_data->GetProcessStatus()) {
      case EmAppInfo_State::EmAppInfo_State_State_STARTING:
      case EmAppInfo_State::EmAppInfo_State_State_RUNNING:
      {
        AIMRT_WARN("[{}]: Repeat request. ignore Start command", app_name);
        return ProcessErrorCode::REPEAT_START_COMMAND;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_STOPPING:
      {
        AIMRT_ERROR("[{}]: Process status is busy. ignore Start command", app_name);
        return ProcessErrorCode::PROCESS_STATUS_BUSY;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_IDLE:
      case EmAppInfo_State::EmAppInfo_State_State_EXITED:
      {
        AIMRT_INFO("[{}]: Ready to Starting app", app_name);
        process_data->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_STARTING);
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS:
      {
        AIMRT_INFO("[{}]: app is killed, ready to start again now...", app_name);
        process_data->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_STARTING);
      } break;
      default:
      {
        AIMRT_ERROR("[{}]: Invalid internal processStatus...", app_name);
        return ProcessErrorCode::INTERNAL_ERROR;
      } break;
    }
  }

  process_data->SetProcessErrorCode(ProcessErrorCode::SUCCESS);
  return StartIntermediateProcess(process_data);
}

ProcessErrorCode ProcessManager::StopApp(const std::string& app_name) {
  auto iter = process_name_to_data_map_.find(app_name);
  if (iter == process_name_to_data_map_.end()) {
    AIMRT_ERROR("[{}]: unknown app_name in stop_app", app_name);
    return ProcessErrorCode::UNKNOWN_APP_NAME;
  }

  auto process_data = iter->second;

  {
    LOCK(process_data->data_mutex_);
    switch(process_data->GetProcessStatus()) {
      case EmAppInfo_State::EmAppInfo_State_State_RUNNING:
      {
        AIMRT_INFO("[{}]: Ready to Stop app", app_name);
        process_data->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_STOPPING);
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_STARTING:
      {
        AIMRT_ERROR("[{}]: Process status is busy. ignore Stop command", app_name);
        return ProcessErrorCode::PROCESS_STATUS_BUSY;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_IDLE:
      {
        AIMRT_ERROR("[{}]: Process is not started. ignore Stop command", app_name);
        return ProcessErrorCode::PROCESS_NOT_STARTED;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_EXITED:
      case EmAppInfo_State::EmAppInfo_State_State_STOPPING:
      {
        AIMRT_ERROR("[{}]: Repeat request. ignore Stop command", app_name);
        return ProcessErrorCode::PRPEAT_STOP_COMMAND;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS:
      {
        AIMRT_WARN("[{}]: app is killed, ignore stop action...", app_name);
        return ProcessErrorCode::PRPEAT_STOP_COMMAND;
      } break;
      default:
      {
        AIMRT_ERROR("[{}]: Invalid internal processStatus...", app_name);
        return ProcessErrorCode::INTERNAL_ERROR;
      } break;
    }
  }

  process_data->SetProcessErrorCode(ProcessErrorCode::SUCCESS);
  return StopProcess(process_data);
}

ProcessErrorCode ProcessManager::StartIntermediateProcess(std::shared_ptr<ProcessData> ptr) {
  ptr->executor_->PrintExecutorArgs();
  ptr->domain_socket_channel_->InitChannelSrv();
  ptr->domain_socket_channel_->InitChannelClient();

  // 创建中间进程
  pid_t intermediate_pid = fork();
  if (intermediate_pid == 0) {
    InitProcessLogger(ptr->app_info_.app_name);

    AIMRT_INFO_P("[{}]: fork intermediate pid: {}", ptr->app_info_.app_name, getpid());
    auto code = StartAppProcess(ptr);
    if (code == ProcessErrorCode::SUCCESS) {
      auto code = ptr->domain_socket_channel_->SendStartMsg(DomainSocketCmd::APP_START_SUCCESS_FLAG,
                                                ptr->app_start_success_str_.data(),
                                                ptr->app_start_success_str_.size());
      if (code != ProcessErrorCode::SUCCESS) {
        AIMRT_ERROR_P("[{}]: SendStartMsg failed: {}", ptr->app_info_.app_name, code);
      }
    } else {
      ptr->domain_socket_channel_->SendStartMsg(DomainSocketCmd::APP_START_FAILED_FLAG,
                                                      ptr->app_start_failed_str_.data(),
                                                      ptr->app_start_failed_str_.size());
      AIMRT_ERROR_P("[{}]: StartAppProcess failed, ErrorCode: {} {}", ptr->app_info_.app_name, code, ProcessErrorCodeToString(code));
      ptr->SetProcessErrorCode(code);
    }

    // 保证通道数据一定发送完毕
    ptr->domain_socket_channel_->ShutdownClient();

    AIMRT_INFO_P("[{}]: intermediate_pid ready exit: {}", ptr->app_info_.app_name, getpid());
    RemoveProcessLogger();

    // 处理结束后, 立即退出
    /**
     * 发现::exit(0) 在某些退出时, 在__pthread_clockjoin_ex 析构中, 会触发一个崩溃, 所以暂时直接用 _exit(0)来退出
     * 规避应用层一些资源释放问题, 具体原因未知, 可能是框架内部插件异常导致的, 只有在使用ros2 插件时有出现.
     * */
    /**
     * fork 之后不能执行 fflush(NULL) 函数，在父进程std::ostream::flush()刷新日志时， 执行frok, 再执行fflush(NULL)
     * 有低概率造成死锁
    */
    ::_exit(0);
  } else {
    // 关闭clannel client端:
    ptr->domain_socket_channel_->CleanClient();

    AIMRT_INFO("[{}]: parent watch Intermediate pid: {}", ptr->app_info_.app_name, intermediate_pid);
    ptr->SetIntermediatePid(intermediate_pid);

    auto code = ptr->WatchStartSuccessFlag(5000);
    switch (code)
    {
      case ProcessErrorCode::SUCCESS:
      {
        {
          LOCK(ptr->data_mutex_);
          ptr->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_RUNNING);
        }
        ptr->SaveProcessStateFile();
        AIMRT_INFO("[{}]: Start Process success. Intermediate pid: {}, app pid: {}", ptr->app_info_.app_name, intermediate_pid, ptr->GetAppPid());
      } break;
      case ProcessErrorCode::DOMAIN_SOCKET_RECV_TIMEOUT:
      case ProcessErrorCode::DOMAIN_SOCKET_RECV_FAILED:
      default:
      {
        AIMRT_ERROR("[{}]: Start Process failed. Recv Intermediate process Channnel msg: {} {}, {}", ptr->app_info_.app_name, code, ProcessErrorCodeToString(code), intermediate_pid);
        /**
         * 目前使用启动后, 默认设置状态为 RUNNING_IN_PASS, 让aima-cli 工具可以展示所有启动节点的最终状态
        */
        LOCK(ptr->data_mutex_);
        ptr->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS);
        // 需要手动更新启动时间
        ptr->SetTimeStamp(GetCurrentNanoSecondTimestamp());
        ptr->SetProcessErrorCode(code);
        break;
      }
    }

    // 回收中间子进程, 仅记录状态
    do
    {
      int status;
      pid_t wp = ::waitpid(intermediate_pid, &status, 0);  // 阻塞等待
      if (wp == -1) {
        AIMRT_ERROR("[{}]: waitpid error, ret is -1.  {}", ptr->app_info_.app_name, intermediate_pid);
        break;
      }

      if (WIFEXITED(status)) {
        int exit_status = WEXITSTATUS(status);
        if (exit_status == 0) {
          AIMRT_INFO("[{}]: wait intermediate_process exited. {}", ptr->app_info_.app_name, intermediate_pid);
        } else {
          AIMRT_WARN("[{}]: intermediate_process exited, status: {} {}", ptr->app_info_.app_name, exit_status, intermediate_pid);
        }
      } else if (WIFSIGNALED(status)) {
          AIMRT_WARN("[{}]: intermediate_process {} killed by signal: {}", ptr->app_info_.app_name, intermediate_pid, WTERMSIG(status));
      } else if (WIFSTOPPED(status)) {
          AIMRT_WARN("[{}]: intermediate_process {} stopped by signal: {}", ptr->app_info_.app_name, intermediate_pid, WSTOPSIG(status));
      } else if (WIFCONTINUED(status)) {
          AIMRT_WARN("[{}]: intermediate_process {} resumed", ptr->app_info_.app_name, intermediate_pid);
      } else {
        AIMRT_WARN("[{}]: intermediate_process {} status {} is unusual....",  ptr->app_info_.app_name, wp, status);
      }
    } while (false);

    // 清理启动的过程数据
    ptr->ResetStartupData();
  }

  return ptr->GetProcessErrorCode();
}

// fork 真正需要执行的业务进程
ProcessErrorCode ProcessManager::StartAppProcess(std::shared_ptr<ProcessData> ptr) {
  // 校验可执行程序path是否正常
  auto code = ptr->executor_->ExecutorValidate();
  if (code != ProcessErrorCode::SUCCESS) {
    AIMRT_ERROR_P("[{}]: ExecutorValidate app_pid failed", ptr->app_info_.app_name);
    return code;
  }

  pid_t app_pid = fork();
  if (app_pid == 0) {
    InitProcessLogger(ptr->app_info_.app_name + "_real");

    AIMRT_INFO_P("[{}]: create app_pid: {}", ptr->app_info_.app_name, getpid());
    code = ptr->executor_->PrepareExecution();
    if (code != ProcessErrorCode::SUCCESS) {
      AIMRT_ERROR_P("[{}]: PrepareExecution failed. app_name: ", ptr->app_info_.app_name);
      ::exit(1);
    }

    ptr->executor_->StartExec();
    AIMRT_ERROR_P("[{}]: StartExec return, please check...", ptr->app_info_.app_name);
    ::exit(1);
  } else {
    // 如何通知父进程? 使用domain socket
    // 而不是直接赋值:     //ptr->app_pid_ = app_pid;
    pid_t app_pid_data = htonl(app_pid);
    ptr->domain_socket_channel_->SendStartMsg(DomainSocketCmd::APP_PID_INTE_TYPE,
                                              reinterpret_cast<char*>(&app_pid_data), sizeof(pid_t));
    AIMRT_INFO_P("[{}]: Intermediate pid: {}, app_pid: {}", ptr->app_info_.app_name, getpid(), app_pid);

    // wait 1s
    int max_wait = 1000;
    int total_wait = 0;
    while(running_.load()) {
      int status;
      pid_t ret;
      ret = ::waitpid(app_pid, &status, WNOHANG);  // 非阻塞等待
      if (ret == -1) {
        AIMRT_ERROR_P("[{}]: waitpid return false. {}", ptr->app_info_.app_name, strerror(errno));
        ptr->SetProcessErrorCode(ProcessErrorCode::WAITPID_RET_ERROR);
        break;
      } else if (ret == 0) {
        if (total_wait ++ > max_wait) {
          AIMRT_DEBUG_P("[{}]: Child still running", ptr->app_info_.app_name);
          break;
        }
      } else {
        // ret > 0, 子进程状态变化
        if (WIFEXITED(status)) {
            AIMRT_ERROR_P("[{}]: Child  {} exited with status: {}", ptr->app_info_.app_name, ret, WEXITSTATUS(status));
            ptr->SetProcessErrorCode(ProcessErrorCode::WAITPID_EXIT);
        } else if (WIFSIGNALED(status)) {
            AIMRT_ERROR_P("[{}]: Child {} killed by signal: {}", ptr->app_info_.app_name, ret, WTERMSIG(status));
            ptr->SetProcessErrorCode(ProcessErrorCode::WAITPID_SIGNALED);
        } else if (WIFSTOPPED(status)) {
            AIMRT_ERROR_P("[{}]: Child {} stopped by signal: {}", ptr->app_info_.app_name, ret, WSTOPSIG(status));
            ptr->SetProcessErrorCode(ProcessErrorCode::WAITPID_STOPPED);
        } else if (WIFCONTINUED(status)) {
            AIMRT_ERROR_P("[{}]: Child {} resumed", ptr->app_info_.app_name, ret);
            ptr->SetProcessErrorCode(ProcessErrorCode::WAITPID_CONTINUED);
        } else {
          AIMRT_ERROR_P("[{}]: Child  {} status {} is unusual....",  ptr->app_info_.app_name, ret, status);
        }
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  return ptr->GetProcessErrorCode();
}

// 直接等待一个超时时间
ProcessErrorCode ProcessManager::StopProcess(std::shared_ptr<ProcessData> ptr) {
  int app_pid = ptr->GetAppPid();
  AIMRT_INFO("[{}]: Ready to stop app,  pid: {}", ptr->app_info_.app_name, app_pid);
  SessionUtil::TryTermSession(app_pid);
  int timeout_ms = ptr->app_info_.guard_option.delay_ms;

  int now_ms = GetCurrentMilliSecondTimestamp();
  do
  {
    if (!SessionUtil::SessionHasProcess(app_pid)) {
      LOCK(ptr->data_mutex_);
      ptr->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_EXITED);
      AIMRT_INFO("[{}]: Kill App_name success. ", ptr->app_info_.app_name);
      break;
    }

    int this_time = GetCurrentMilliSecondTimestamp();
    if (this_time > now_ms + timeout_ms) {
      AIMRT_INFO("[{}]: [STILL RUNNING] force kill session_id: {}", ptr->app_info_.app_name, app_pid);
      SessionUtil::TryKillSession(app_pid);
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  } while (true);

  // reset
  ptr->ResetRunningData();
  ptr->RemoveProcessStateFile();

  return ptr->GetProcessErrorCode();
}

ProcessErrorCode ProcessManager::SetEnvCfg(const std::string& app_name, const std::string& key, const std::string& val) {
  auto iter = process_name_to_data_map_.find(app_name);
  if (iter == process_name_to_data_map_.end()) {
    AIMRT_ERROR("[{}]: unknown app_name in SetEnvCfg", app_name);
    return ProcessErrorCode::UNKNOWN_APP_NAME;
  }

  bool ret = iter->second->UpdateExecutorEnvCfg(key, val);
  if (!ret) {
    AIMRT_ERROR("[{}]: SetEnvCfg failed, key: {}, val: {}", app_name, key, val);
    return ProcessErrorCode::SET_ENV_CFG_FAILED;
  }

  return ProcessErrorCode::SUCCESS;
}

ProcessErrorCode ProcessManager::ResetApp(const std::string& app_name) {
  auto iter = process_name_to_data_map_.find(app_name);
  if (iter == process_name_to_data_map_.end()) {
    AIMRT_ERROR("[{}]: unknown app_name in ResetApp", app_name);
    return ProcessErrorCode::UNKNOWN_APP_NAME;
  }

  iter->second->ResetStartupData();
  iter->second->ResetRunningData();
  return ProcessErrorCode::SUCCESS;
}

void ProcessManager::LoadProcessStateFile() {
  try
  {
    std::filesystem::path reload_path(g_reload_process_path);

    std::vector<std::filesystem::path> rm_list;
    for (auto &entry : std::filesystem::directory_iterator(reload_path)) {
      if (entry.is_regular_file()) {
        std::string fname_str = entry.path().filename().string();

        AIMRT_INFO("load process_state file: {}", fname_str);
        ProcessReloadInfo info;
        if (!ParseProcessState(entry.path().string(), info)) {
          AIMRT_ERROR("parse failed. will remove...");
          rm_list.emplace_back(entry.path());
          continue;
        }

        auto iter = process_name_to_data_map_.find(info.app_name);
        if (iter == process_name_to_data_map_.end()) {
          AIMRT_ERROR("[{}]: unknown app_name in data_map. will remove...", info.app_name);
          rm_list.emplace_back(entry.path());
          continue;
        }

        uint64_t process_start_time = SessionUtil::GetProcessStartTime(info.pid);
        if (0 == process_start_time) {
          AIMRT_WARN("[{}]: pid is not exists {}. process_start_time is 0. will remove..", info.app_name, info.pid);
          rm_list.emplace_back(entry.path());
          continue;
        }

        size_t hash_val = SessionUtil::HashProcessState(info.pid, process_start_time);
        if (info.hash_val != hash_val) {
          AIMRT_WARN("[{}]: hash is not same, {}, in file is {}, now is {}. will remove..", info.app_name, info.pid, info.hash_val, hash_val);
          rm_list.emplace_back(entry.path());
          continue;
        }

        iter->second->SetAppPid(info.pid);
        iter->second->SetProcessStatus(EmAppInfo_State::EmAppInfo_State_State_RUNNING, false);
        iter->second->SetTimeStamp(info.time_stamp);
        iter->second->SetReloadFlag(true);
        iter->second->SetProcessStartTime(process_start_time);
      }
    }

    for (auto& path : rm_list) {
      std::filesystem::remove(path);
    }
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("catch exception {}", e.what());
  }
}

bool ProcessManager::ParseProcessState(const std::string& file_path, ProcessReloadInfo& info) {
  std::ifstream ifs(file_path);
  std::string app_name, start_time, time_stamp, pid, hash_str;
  std::getline(ifs, app_name);
  std::getline(ifs, start_time);
  std::getline(ifs, time_stamp);
  std::getline(ifs, pid);
  std::getline(ifs, hash_str);
  info.app_name = app_name;
  info.start_time = start_time;

  try
  {
    info.time_stamp = std::stoull(time_stamp);
    info.pid = std::stol(pid);
    info.hash_val = std::stoull(hash_str);

    AIMRT_INFO("[{}] parse process stat: pid: {}, start_time: {}", app_name, pid, start_time);
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("Parse Error, file_path: {}, {}. time_stamp: {}, pid: {}, hash_str: {}", file_path, e.what(), time_stamp, pid, hash_str);
    return false;
  }
  return true;
}

void ProcessManager::StopAllProcess() {
  std::vector<MonitorAppInfo> running_app_list;
  for (const auto& [name, ptr] : process_name_to_data_map_) {
    LOCK(ptr->data_mutex_);
    if (ptr->GetProcessStatus() == EmAppInfo_State::EmAppInfo_State_State_RUNNING) {
      MonitorAppInfo info;
      info.app_name = name;
      info.pid = ptr->GetAppPid();
      info.state = ptr->GetProcessStatus();
      info.time_stamp = ptr->GetStartTimeStamp();
      info.from_reload = ptr->GetReloadFlag();
      running_app_list.emplace_back(std::move(info));
    }
  }

  FutureMultiThreadMgr mgr;
  for (auto& app_info : running_app_list) {
    std::string app_name = app_info.app_name;
    int app_pid = app_info.pid;
    mgr.PushTask(
      [this, app_name, app_pid]() -> ProcessErrorCode {
        AIMRT_INFO("[{}]: try term session_id: {}", app_name, app_pid);
        SessionUtil::TryTermSession(app_pid);
        return ProcessErrorCode::SUCCESS;
      },
      [app_name, this](ProcessErrorCode code) {
        if (code != ProcessErrorCode::SUCCESS) {
          AIMRT_ERROR("Stop all list: {} failed. {} {}", app_name, code, ProcessErrorCodeToString(code));
        }
      }
    );
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  mgr.WaitTaskFinish();
}

}
