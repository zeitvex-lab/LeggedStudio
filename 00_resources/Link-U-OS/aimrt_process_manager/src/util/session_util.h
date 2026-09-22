// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <dirent.h>
#include <unistd.h>
#include <sys/types.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <string>
#include <csignal>

#include "global.h"

namespace process_manager {

class SessionUtil {
 public:
  // 工具：把 /proc/<pid>/stat 中的 session 字段读出来
  static pid_t GetSessionFromStat(pid_t pid);

  static uint64_t GetProcessStartTime(pid_t pid);

  static std::string GetProcessCmdLine(pid_t pid);

  // 返回与给定 session_id 同一 session 的所有进程
  static bool GetProcessesInSession(pid_t session_id, std::vector<pid_t>& result);

  static bool TrySendSignalToAllProcess(int session_id, int signal);

  static void TryTermSession(int session_id);

  static void TryKillSession(int session_id);

  static bool SessionHasProcess(int session_id);

  static bool ProcessExists(const std::string app_name, int pid, uint64_t process_start_time);

  static std::size_t HashProcessState(int pid, uint64_t process_start_time);
};

}
