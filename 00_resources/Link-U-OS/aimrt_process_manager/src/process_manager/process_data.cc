// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process_data.h"

#include <fstream>
#include <functional>

#include "src/util/util_func.h"
#include "src/util/session_util.h"

namespace process_manager
{

ProcessData::ProcessData(const AppInfo& app_info, const EnvVar& env_var)
  : app_info_(app_info),
    env_list_(env_var) {
  executor_ = std::make_shared<Executor>(app_info, env_list_);
}

void ProcessData::Init() {
  executor_->Init();
}

void ProcessData::ResetRunningData() {
  {
    LOCK(data_mutex_);
    status_ = EmAppInfo_State::EmAppInfo_State_State_IDLE;
  }
  error_code_ = ProcessErrorCode::SUCCESS;
  intermediate_pid_.store(-1);
  app_pid_.store(-1);

  start_time_stamp_.store(0);
  process_start_time_.store(0);
  from_reload_.store(false);
  AIMRT_DEBUG("[{}]: Reset Running data...", app_info_.app_name);
}

void ProcessData::ResetStartupData() {
  // 通道单独维护, 启动完毕, 关闭通道
  if (domain_socket_channel_)
    domain_socket_channel_->Reset();

  if (executor_) {
    executor_->Reset();
    executor_->Init();
  }

  recv_start_success_flag_.store(false);
  recv_start_failed_flag_.store(false);

  AIMRT_DEBUG("[{}]: Reset Startup data...", app_info_.app_name);
}

void ProcessData::SetProcessStatus(EmAppInfo_State status, bool update_time) {
  status_ = status;
  if (status_ == EmAppInfo_State::EmAppInfo_State_State_RUNNING && update_time) {
    start_time_stamp_.store(GetCurrentNanoSecondTimestamp());
    // 保存/proc/xxx/stat 里面的时间戳
    int pid = GetAppPid();
    uint64_t process_start_time = SessionUtil::GetProcessStartTime(pid);
    SetProcessStartTime(process_start_time);
    AIMRT_INFO("[{}]: update process start time: {}, {}", app_info_.app_name, process_start_time, pid);
  }
}

bool ProcessData::SaveProcessStateFile() {
  std::string full_path = g_reload_process_path + "/" + app_info_.app_name + ".state";

  try
  {
    std::filesystem::path file_path(full_path);
    if (std::filesystem::exists(file_path)) {
      AIMRT_ERROR_P("[{}]: file_path is exist, remove it ...", app_info_.app_name);
      std::filesystem::remove(file_path);
    }
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR_P("[{}] catch exception: {}", app_info_.app_name, e.what());
    return false;
  }

  std::string data = CreateProcessStateStr();
  std::ofstream ofs(full_path, std::ios::binary);
  ofs.write(data.data(), data.size());
  ofs.close();
  return true;
}

bool ProcessData::RemoveProcessStateFile() {
  std::string full_path = g_reload_process_path + "/" + app_info_.app_name + ".state";

  try
  {
    std::filesystem::path file_path(full_path);
    if (!std::filesystem::exists(file_path)) {
      AIMRT_ERROR_P("[{}]: file_path {} is not exists ...", app_info_.app_name, full_path);
      return false;
    }
    std::filesystem::remove(file_path);
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR_P("[{}] catch exception: {}", app_info_.app_name, e.what());
    return false;
  }
  return true;
}

void ProcessData::RecvDomainSocketData(const DomainSocketStruct* st) {
  uint16_t cmd = ntohs(st->cmd);
  uint32_t len = ntohl(st->len);
  uint32_t read_len = len - sizeof(DomainSocketStruct);
  switch(cmd) {
    case DomainSocketCmd::APP_PID_INTE_TYPE:
    {
      if (read_len != sizeof(app_pid_)) {
        AIMRT_ERROR("invalid read_len: {}, in APP_PID_INTE_TYPE", read_len);
        break;
      }
      app_pid_ = ntohl(*reinterpret_cast<const int*>(st->payload));
      AIMRT_INFO("recv DomainSocketDtata, Update real app_pid: {}, [{}]", app_pid_.load(), app_info_.app_name);
    } break;
    case DomainSocketCmd::APP_START_SUCCESS_FLAG:
    {
      if (::strncmp(app_start_success_str_.data(), st->payload, read_len) == 0) {
        AIMRT_INFO("Recv DomainSocketDtata, Start App [{}] success.", app_info_.app_name);
        recv_start_success_flag_.store(true);
      } else {
        AIMRT_ERROR("recv invalid start app flag: {}, len: {}, app_name: {}", st->payload, read_len, app_info_.app_name);
      }
    } break;
    case DomainSocketCmd::APP_START_FAILED_FLAG:
    {
      if (::strncmp(app_start_failed_str_.data(), st->payload, read_len) == 0) {
        AIMRT_WARN("Recv DomainSocketDtata, Start App [{}] failed.", app_info_.app_name);
        recv_start_failed_flag_.store(true);
      } else {
        AIMRT_ERROR("recv invalid start app flag: {}, len: {}, app_name: {}", st->payload, read_len, app_info_.app_name);
      }
    } break;
    default:
      break;
  }
}

ProcessErrorCode ProcessData::WatchStartSuccessFlag(int timeout_ms) {
  int sleep_internal = timeout_ms / 10;
  uint64_t end_time = GetCurrentMilliSecondTimestamp() + timeout_ms;

  ProcessErrorCode code = ProcessErrorCode::SUCCESS;
  while (true) {
    if (recv_start_success_flag_.load()) {
      break;
    } else if (recv_start_failed_flag_.load()) {
      code = ProcessErrorCode::DOMAIN_SOCKET_RECV_FAILED;
      break;
    } else {
      std::this_thread::sleep_for(std::chrono::milliseconds(sleep_internal));
      uint64_t now_time = GetCurrentMilliSecondTimestamp();
      if (now_time > end_time) {
        code = ProcessErrorCode::DOMAIN_SOCKET_RECV_TIMEOUT;
        break;
      }
    }
  }
  return code;
}

std::string ProcessData::CreateProcessStateStr() {
  std::size_t hash_num = SessionUtil::HashProcessState(GetAppPid(), GetProcessStartTime());
  AIMRT_INFO("[{}] create hash_str: {}", app_info_.app_name, hash_num);

  std::string data;
  data += app_info_.app_name;
  data += "\n";
  data += GetLocalSecondTimestampStr(GetStartTimeStamp());
  data += "\n";
  data += std::to_string(GetStartTimeStamp());
  data += "\n";
  data += std::to_string(GetAppPid());
  data += "\n";
  data += std::to_string(hash_num);
  data += "\n";
  return data;
}

}
