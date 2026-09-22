// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "global.h"

#include "domain_socket.h"

namespace process_manager
{

aimrt::logger::LoggerRef global_logger_ref;
void SetLogger(aimrt::logger::LoggerRef logger_ref) { global_logger_ref = logger_ref; }
aimrt::logger::LoggerRef GetLogger() { return global_logger_ref; }


// 当前主进程的pid
int g_process_manager_pid;

const std::string g_domain_socket_path{"/agibot/sys/em"};
const std::string g_reload_process_path{"/agibot/sys/proc/process/"};

// 处理多进程的日志打印
const std::string g_logger_socket_name{"multi_process_log.sock"};
// 主进程处理额外增加的日志打印
std::shared_ptr<Server> g_log_server_ptr;


// 额外保存domain_socket日志异常, 或调试过程中, 子进程产生的日志
const std::string g_std_log_dir{"/agibot/log/process_manager"};
std::string g_std_log_name;
bool g_std_log_enable{false};
int g_max_std_log_num;


// 定义全局的时区偏移量, 在程序初始化时进行填充
time_t g_timezone;


}
