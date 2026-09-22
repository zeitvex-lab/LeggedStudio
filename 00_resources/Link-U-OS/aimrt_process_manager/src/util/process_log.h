// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <unordered_map>

#include "src/common/util/log_util.h"
#include "src/util/global.h"

#if __GLIBC__ == 2 && __GLIBC_MINOR__ < 30
  #include <sys/syscall.h>
  #define gettid() syscall(SYS_gettid)
#endif

namespace process_manager
{

struct DomainSocketStruct;

class ProcessSimpleLogger {
 public:
  static uint32_t GetLogLevel() { return 0; }

  static void Log(uint32_t lvl,
                  uint32_t line,
                  const char* file_name,
                  const char* function_name,
                  const char* log_data,
                  size_t log_data_size);

  static void CollectLog(const DomainSocketStruct* st);
};

extern ProcessSimpleLogger g_process_simple_logger;

inline std::string_view GetTimeStr();

std::string generate_dated_filename();
void safe_log(const std::string& log_str, bool add_time_prefix = true);

// fork之后需要进行初始化操作
bool InitProcessLogger(const std::string& app_name);
void RemoveProcessLogger();

/// Log with the specified logger handle
#define AIMRT_HANDLE_LOG(__lgr__, __lvl__, __fmt__, ...)                        \
  do {                                                                          \
    const auto& __cur_lgr__ = __lgr__;                                          \
    if (__lvl__ >= __cur_lgr__.GetLogLevel()) {                                 \
      std::string __log_str__ = ::aimrt_fmt::format(__fmt__, ##__VA_ARGS__);    \
      constexpr auto __location__ = std::source_location::current();            \
      __cur_lgr__.Log(                                                          \
          __lvl__, __location__.line(), __location__.file_name(), __FUNCTION__, \
          __log_str__.c_str(), __log_str__.size());                             \
    }                                                                           \
  } while (0)


#define AIMRT_TRACE_P(__fmt__, ...)               \
  do                                              \
  {                                               \
    if (getpid() == g_process_manager_pid) {      \
      AIMRT_TRACE(__fmt__,  ##__VA_ARGS__);       \
    } else {                                      \
      AIMRT_HANDLE_LOG(g_process_simple_logger, aimrt::common::util::kLogLevelTrace, __fmt__, ##__VA_ARGS__);  \
    }                                                                                                          \
  } while(false);


#define AIMRT_DEBUG_P(__fmt__, ...)               \
  do                                              \
  {                                               \
    if (getpid() == g_process_manager_pid) {      \
      AIMRT_DEBUG(__fmt__,  ##__VA_ARGS__);       \
    } else {                                      \
      AIMRT_HANDLE_LOG(g_process_simple_logger, aimrt::common::util::kLogLevelDebug, __fmt__, ##__VA_ARGS__);  \
    }                                                                                                          \
  } while(false);



#define AIMRT_INFO_P(__fmt__, ...)                \
  do                                              \
  {                                               \
    if (getpid() == g_process_manager_pid) {      \
      AIMRT_INFO(__fmt__,  ##__VA_ARGS__);        \
    } else {                                      \
      AIMRT_HANDLE_LOG(g_process_simple_logger, aimrt::common::util::kLogLevelInfo, __fmt__, ##__VA_ARGS__);   \
    }                                                                                                          \
  } while(false);

#define AIMRT_WARN_P(__fmt__, ...)                \
  do                                              \
  {                                               \
    if (getpid() == g_process_manager_pid) {      \
      AIMRT_WARN(__fmt__,  ##__VA_ARGS__);        \
    } else {                                      \
      AIMRT_HANDLE_LOG(g_process_simple_logger, aimrt::common::util::kLogLevelWarn, __fmt__, ##__VA_ARGS__);   \
    }                                                                                                          \
  } while(false);


#define AIMRT_ERROR_P(__fmt__, ...)               \
  do                                              \
  {                                               \
    if (getpid() == g_process_manager_pid) {      \
      AIMRT_ERROR(__fmt__,  ##__VA_ARGS__);       \
    } else {                                      \
      AIMRT_HANDLE_LOG(g_process_simple_logger, aimrt::common::util::kLogLevelError, __fmt__, ##__VA_ARGS__);  \
    }                                                                                                          \
  } while(false);



#define AIMRT_FATA_P(__fmt__, ...)                \
  do                                              \
  {                                               \
    if (getpid() == g_process_manager_pid) {      \
      AIMRT_FATA(__fmt__,  ##__VA_ARGS__);        \
    } else {                                      \
      AIMRT_HANDLE_LOG(g_process_simple_logger, aimrt::common::util::kLogLevelFatal, __fmt__, ##__VA_ARGS__);  \
    }                                                                                                          \
  } while(false);

}
