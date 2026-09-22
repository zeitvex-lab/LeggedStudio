// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "session_util.h"

#include <fstream>

namespace process_manager {


// 工具：把 /proc/<pid>/stat 中的 session 字段读出来
pid_t SessionUtil::GetSessionFromStat(pid_t pid)
{
  FILE* fp = nullptr;
  char path[64];
  snprintf(path, sizeof(path), "/proc/%d/stat", pid);

  if (!(fp = fopen(path, "r"))) {
      return -1;          // 进程已消失或权限不足
  }

  // man proc: pid, comm, state, ppid, pgrp, session, ...
  int sid = -1;
  // 用格式串跳过前 5 个字段，直接读第 6 个字段(session)
  if (fscanf(fp, "%*d %*s %*c %*d %*d %d", &sid) != 1) {
      sid = -1;
  }
  fclose(fp);
  return static_cast<pid_t>(sid);
}

// 把 /proc/<pid>/stat 中的 starttime 10毫秒精度级的时间戳字段读出来
uint64_t SessionUtil::GetProcessStartTime(pid_t pid) {
  FILE* fp = nullptr;
  char path[64];
  snprintf(path, sizeof(path), "/proc/%d/stat", pid);

  if (!(fp = fopen(path, "r"))) {
    return 0;
  }

  long long unsigned int starttime = 0;
  // 取第 22 字段
  if (fscanf(fp, "%*d %*s %*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %*u %*u %*d %*d %*d %*d %*d %*u %llu", &starttime) != 1) {
    starttime = 0;
  }
  fclose(fp);
  return starttime;
}

std::string SessionUtil::GetProcessCmdLine(pid_t pid) {
  std::ifstream fs("/proc/" + std::to_string(pid) + "/cmdline", std::ios::binary);
  if (!fs)
      return "";

  std::ostringstream tmp;
  tmp << fs.rdbuf();
  std::string raw_str = tmp.str();
  if (raw_str.empty())
      return "";

  // 替换 \0
  std::replace(raw_str.begin(), raw_str.end(), '\0', ' ');

  return raw_str;
}

// 返回与给定 session_id 同一 session 的所有进程
bool SessionUtil::GetProcessesInSession(pid_t session_id, std::vector<pid_t>& result)
{
    DIR* dir = opendir("/proc");
    if (!dir) {
        AIMRT_ERROR("Get Session list failed, session_id: {}, {}", session_id, std::string("opendir /proc failed: ") + strerror(errno));
        return false;
    }

    struct dirent* ent;
    while ((ent = readdir(dir)) != nullptr) {
        // 只看纯数字的目录名，即 PID
        char* end = nullptr;
        long pid_l = strtol(ent->d_name, &end, 10);
        // 不是数字目录
        if (*end != '\0')
          continue;
        pid_t pid = static_cast<pid_t>(pid_l);

        pid_t sid = GetSessionFromStat(pid);
        if (sid == session_id) {
            result.push_back(pid);
        }
    }
    closedir(dir);

    return true;
}

bool SessionUtil::TrySendSignalToAllProcess(int session_id, int signal) {
  std::vector<pid_t> result_pid;
  if (!GetProcessesInSession(session_id, result_pid)) {
    return false;
  }

  for (auto& session : result_pid) {
    if (::kill(session, signal) == -1) {
      AIMRT_ERROR("kill session failed. {}. signal: {}.", session, signal);
      return false;
    }
  }
  return true;
}

void SessionUtil::TryTermSession(int session_id) {
  if (::kill(-session_id, SIGTERM) == -1) {
    AIMRT_WARN("kill SIGTERM -session_id {} failed, try to kill each one", session_id);

    TrySendSignalToAllProcess(session_id, SIGTERM);
  }
}

void SessionUtil::TryKillSession(int session_id) {
  if (!TrySendSignalToAllProcess(session_id, SIGKILL)) {
    AIMRT_WARN("Kill -9 all Process failed...try again...");
    TryKillSession(session_id);
  }
}

bool SessionUtil::SessionHasProcess(int session_id) {
  std::vector<pid_t> result_pid;
  if (!GetProcessesInSession(session_id, result_pid)) {
    return false;
  }

  return !result_pid.empty();
}


// 判断当前进程是否存活, pid存在, 且和state里面的启动时间戳一致
bool SessionUtil::ProcessExists(const std::string app_name, int pid, uint64_t process_start_time) {
  uint64_t start_time_new = GetProcessStartTime(pid);
  if (0 == start_time_new) {
    AIMRT_WARN("[{}]: pid: {}. start_time_new is 0. old_start_time: {}. may be process is killed...", app_name, pid, process_start_time);
    return false;
  }

  if (start_time_new != process_start_time) {
    AIMRT_WARN("[{}]: pid: {}. start_time_new is {}, old_start_time: {}, invaild... may be process is killed...", app_name, pid, start_time_new, process_start_time);
    return false;
  }

  return true;
}

template <class... Ts>
std::size_t hash_vals(const Ts&... vs) {
  std::size_t seed = 0;
  ((seed ^= std::hash<std::decay_t<Ts>>{}(vs) + 0x9e3779b9 + (seed << 6) + (seed >> 2)), ...);
  return seed;
}

std::size_t SessionUtil::HashProcessState(int pid, uint64_t process_start_time) {
  // 将 /proc/xxx/stat 里面的时间戳, 和 /proc/xxx/cmdline 里面的内容 计算hash
  std::string cmdline = SessionUtil::GetProcessCmdLine(pid);
  return hash_vals(process_start_time, cmdline);
}

}
