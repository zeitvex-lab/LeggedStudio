// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <sstream>
#include "aimrt_module_cpp_interface/logger/logger.h"

namespace process_manager
{

void SetLogger(aimrt::logger::LoggerRef logger_ref);
aimrt::logger::LoggerRef GetLogger();

class Server;

// 当前主进程的pid
extern int g_process_manager_pid;

extern const std::string g_domain_socket_path;
extern const std::string g_reload_process_path;

// 处理多进程的日志打印
extern const std::string g_logger_socket_name;
// 主进程处理额外增加的日志打印
extern std::shared_ptr<Server> g_log_server_ptr;


// 记录额外增加的日志打印
extern const std::string g_std_log_dir;
extern std::string g_std_log_name;
extern bool g_std_log_enable;
extern int g_max_std_log_num;

// 定义全局的时区偏移量, 在程序初始化时进行填充
extern time_t g_timezone;

}
