// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process_log.h"

#include <stdint.h>
#include <arpa/inet.h>

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <regex>
#include <string>
#include <vector>

#include "localtime.h"
#include "domain_socket.h"

namespace process_manager
{

ProcessSimpleLogger g_simple_logger;

// 保存子进程创建的domain_socket fd, 用于向父进程发送日志
// 子进程默认是单线程, 使用 thread_local 变量保存
thread_local int child_process_domain_fd{0};

// 子进程内部使用, 规避使用localtime_r的函数, 因为有可能其内部的全局锁, 会导致进程死锁
inline std::string_view GetTimeStr() {
  timespec ts{};
  clock_gettime(CLOCK_REALTIME, &ts);

  time_t utc_sec = ts.tv_sec;   // 使用utc时间, 在nolocks_localtime里面会针对时区 g_timezeon 进行处理
  tm   tm{};
  nolocks_localtime(&tm, utc_sec, g_timezone, 0);
  int ms = ts.tv_nsec / 1000000;

  thread_local char buf[32] = {0};
  snprintf(buf, sizeof(buf), "%04d-%02d-%02d %02d:%02d:%02d.%03d",
            (tm.tm_year + 1900) % 10000u ,
            (tm.tm_mon + 1) % 100u,
            (tm.tm_mday) % 100u,
            (tm.tm_hour % 100u),
            (tm.tm_min % 100u),
            (tm.tm_sec % 100u),
            (ms % 1000u));
  return std::string_view(buf);
}

struct SafeLogEntry {
  std::filesystem::path  file_path;
  uint64_t ts; // 12 位时间戳数字
};

// std_202510221903.log
std::string generate_dated_filename() {
  std::filesystem::path log_path(g_std_log_dir);

  std::time_t t = std::time(nullptr);
  std::tm tm_info;
  localtime_r(&t, &tm_info);
  std::ostringstream oss;
  oss << std::setw(4) << (tm_info.tm_year + 1900)
      << std::setw(2) << std::setfill('0') << (tm_info.tm_mon + 1) << std::setw(2) << std::setfill('0') << tm_info.tm_mday << std::setw(2)
      << std::setfill('0') << tm_info.tm_hour << std::setw(2) << std::setfill('0') << tm_info.tm_min;
  std::string date_str = oss.str();

  try
  {
    const std::regex pattern(R"(^std_(\d{12})\.log$)");
    std::vector<SafeLogEntry> vec;
    if (std::filesystem::exists(log_path) && std::filesystem::is_directory(log_path)) {
      for (auto &entry : std::filesystem::directory_iterator(log_path)) {
        if (entry.is_regular_file()) {
          std::string fname_str = entry.path().filename().string();

          std::smatch m;
          if (!std::regex_match(fname_str, m, pattern)) continue;

          // m[0] 表示整个匹配字符串, m[1] 表示时间戳数字
          vec.emplace_back(SafeLogEntry{entry.path(), std::stoull(m[1].str())});
        }
      }

      if (vec.size() > (size_t)g_max_std_log_num) {
        // 按数字升序
        std::sort(vec.begin(), vec.end(),
                  [](const SafeLogEntry& a, const SafeLogEntry& b) {
                      return a.ts < b.ts;
                  });
        std::size_t delete_size = vec.size() - g_max_std_log_num;
        vec.erase(vec.begin() + delete_size, vec.end());
        // 删除最早的文件, 保留最终 g_max_std_log_num_ 个
        for (auto & entry : vec) {
          std::filesystem::remove(entry.file_path);
          AIMRT_INFO("remove old log file: {}", entry.file_path.filename().string());
        }
      }
    }
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("Handle old dated file is error: {}", e.what());
  }

  std::string new_filename = "std_" + date_str + ".log";
  std::filesystem::path new_filepath = log_path / new_filename;
  return new_filepath.string();
}

/*
  并发安全写日志：O_APPEND + 单次 write()，保证整行原子追加
  用于保存一部分在多进程日志初始化过程中的异常日志, 以及作为多进程日志的补充, 便于子进程日志打印异常后的问题分析

  待domain_socket 的多进程日志落盘稳定后, 会关闭常规的多进程日志打印, 只保留异常场景的输出 2025-10-22
*/
// 仅在子进程中执行
void std_safe_log(const std::string& _log_str, bool add_time_prefix = true)
{
  std::string log_str = _log_str;
    if (add_time_prefix) {
      std::string time_str = ::aimrt_fmt::format(
        "[{}]",
        GetTimeStr());
      log_str = time_str + log_str;
    }
    log_str += "\n";
    /* 必须以 O_APPEND 打开，否则失去原子性 */
    int fd = open(g_std_log_name.c_str(), O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) {
      fprintf(stderr, "[process_manager] open file failed. %s\n", g_std_log_name.c_str());
    }

    int len = log_str.length();
    /* 一次 write 系统调用落盘；≤4 KB 时内核保证原子追加 */
    if (write(fd, log_str.c_str(), len) != len) {
      fprintf(stderr, "[process_manager] write failed. str: %s\n", log_str.c_str());
    }
    close(fd);
}

// 仅在子进程中执行
void ProcessSimpleLogger::Log(uint32_t lvl,
                uint32_t line,
                const char* file_name,
                const char* function_name,
                const char* log_data,
                size_t log_data_size) {

  static constexpr uint32_t kLvlNameArraySize = 6;
  lvl = lvl >= kLvlNameArraySize ? (kLvlNameArraySize - 1) : lvl;

  uint32_t pid = getpid();
  std::string log_str = ::aimrt_fmt::format(
      "--[{}][{}][{} @{}] ***CHILD*** {}",
      GetTimeStr(),
      pid,
      line,
      function_name,
      std::string_view(log_data, log_data_size));

  // 额外进行打印
  if (g_std_log_enable) {
    if (lvl >= aimrt::common::util::kLogLevelInfo) {
      std_safe_log(log_str, false);
    }
  }

  DomainSocketStruct* log_struct = FormatStruct(lvl, log_str.data(), log_str.size());

  size_t n = ::write(child_process_domain_fd, reinterpret_cast<char*>(log_struct), log_str.size() + sizeof(DomainSocketStruct));
  if (n < 0) {
    // 如果发送失败, 则打印到标准错误中
    std::string log = ::aimrt_fmt::format("send log failed... fd: {}, pid: {}", child_process_domain_fd, pid);
    std_safe_log(log);
  }

  // 手动析构
  delete [] reinterpret_cast<char*>(log_struct);
}


void ProcessSimpleLogger::CollectLog(const DomainSocketStruct* st) {
  uint16_t cmd = ntohs(st->cmd);
  uint32_t len = ntohl(st->len);
  uint32_t read_len = len - sizeof(DomainSocketStruct);
  switch(cmd) {
    case DomainSocketCmd::TRACE_LOG : {
      AIMRT_TRACE("{}", std::string_view(st->payload, read_len));
    } break;
    case DomainSocketCmd::DEBUG_LOG: {
      AIMRT_DEBUG("{}", std::string_view(st->payload, read_len));
    } break;
    case DomainSocketCmd::INFO_LOG: {
      AIMRT_INFO("{}", std::string_view(st->payload, read_len));
    } break;
    case DomainSocketCmd::WARN_LOG: {
      AIMRT_WARN("{}", std::string_view(st->payload, read_len));
    } break;
    case DomainSocketCmd::ERROR_LOG: {
      AIMRT_ERROR("{}", std::string_view(st->payload, read_len));
    } break;
    case DomainSocketCmd::FATAL_LOG: {
      AIMRT_FATAL("{}", std::string_view(st->payload, read_len));
    } break;
    default:
      break;
  }
}

// 仅在子进程中执行
bool InitProcessLogger(const std::string& app_name) {
  int sock = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (sock < 0) {
    std_safe_log("socker create failed..." + app_name);
    return false;
  }

  sockaddr_un addr{};
  addr.sun_family = AF_UNIX;
  std::string logger_socket_file_path = g_domain_socket_path + "/" + g_logger_socket_name;
  strncpy(addr.sun_path, logger_socket_file_path.c_str(), sizeof(addr.sun_path) - 1);

  if (connect(sock, (sockaddr*)&addr, sizeof(addr)) < 0) {
    std_safe_log("connect failed..." + app_name);
    return false;
  }

  child_process_domain_fd = sock;

  std_safe_log("init process logger success..." + app_name);
  return true;
}

// 仅在子进程中执行
void RemoveProcessLogger() {
  // 保证fd发送完毕
  ::shutdown(child_process_domain_fd, SHUT_WR);
  ::close(child_process_domain_fd);
  child_process_domain_fd = 0;
}

}
