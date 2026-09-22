// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <map>


namespace process_manager
{

enum ProcessErrorCode {
  // 错误代码按数值排序
  SUCCESS = 0,  // 执行成功
  UNKNOWN_APP_NAME = 10,
  REPEAT_START_COMMAND = 100,  // 重复的启动指令
  PRPEAT_STOP_COMMAND = 101,   // 重复的停止指令
  PROCESS_STATUS_BUSY = 102,   // 状态繁忙
  PROCESS_NOT_STARTED = 103,   // 程序未启动
  SET_ENV_CFG_FAILED = 104,    // 设置环境变量异常
  PROCESS_ALREADY_RUNNING = 105,  // 程序仍然在运行

  DOMAIN_SOCKET_RECV_TIMEOUT = 200,  //
  DOMAIN_SOCKET_POLL_ERROR = 201,    //
  DOMAIN_SOCKET_RECV_ERROR_MSG = 202,
  DOMAIN_SOCKET_SEND_ERROR = 203,
  DOMAIN_SOCKET_CLIENT_CONNECT_ERROR = 204,
  DOMAIN_SOCKET_RECV_FAILED = 205,

  SET_USER_ERROR = 301,
  SET_ENV_ERROR = 302,
  SET_STDOUT_STDERR_ERROR = 303,
  SET_SESSION_ERROR = 304,
  EXECUTOR_CHECK_ERROR = 305,

  WAITPID_RET_ERROR = 401,
  WAITPID_EXIT = 402,
  WAITPID_SIGNALED = 403,
  WAITPID_STOPPED = 404,
  WAITPID_CONTINUED = 405,

  MONITOR_GAT_APP_INFO_ERROR = 501,


  INTERNAL_ERROR = 1000,       // 内部异常
};

inline std::string ProcessErrorCodeToString(ProcessErrorCode code)
{
  switch(code) {
    case ProcessErrorCode::SUCCESS:
      return "success";
    case ProcessErrorCode::UNKNOWN_APP_NAME:
      return "unknown_app_name";
    case ProcessErrorCode::REPEAT_START_COMMAND:
      return "repeat start command";
    case ProcessErrorCode::PRPEAT_STOP_COMMAND:
      return "repeat stop command";
    case ProcessErrorCode::PROCESS_STATUS_BUSY:
      return "process status busy";
    case ProcessErrorCode::PROCESS_NOT_STARTED:
      return "process not started";
    case ProcessErrorCode::SET_ENV_CFG_FAILED:
      return "set env cfg failed";
    case ProcessErrorCode::PROCESS_ALREADY_RUNNING:
      return "process already running";
    case ProcessErrorCode::DOMAIN_SOCKET_RECV_TIMEOUT:
      return "domain socket recv timeout, start process failed. please check process log...";
    case ProcessErrorCode::DOMAIN_SOCKET_POLL_ERROR:
      return "domain socket poll error";
    case ProcessErrorCode::DOMAIN_SOCKET_RECV_ERROR_MSG:
      return "domain socket recv error msg";
    case ProcessErrorCode::DOMAIN_SOCKET_SEND_ERROR:
      return "domain socket send error";
    case ProcessErrorCode::DOMAIN_SOCKET_CLIENT_CONNECT_ERROR:
      return "domain socket client connect error";
    case ProcessErrorCode::DOMAIN_SOCKET_RECV_FAILED:
      return "domain socket recv failed, start process failed. please check process log...";
    case ProcessErrorCode::SET_USER_ERROR:
      return "set user error";
    case ProcessErrorCode::SET_ENV_ERROR:
      return "set env error";
    case ProcessErrorCode::SET_STDOUT_STDERR_ERROR:
      return "set stdout stderr error";
    case ProcessErrorCode::SET_SESSION_ERROR:
      return "set session error";
    case ProcessErrorCode::EXECUTOR_CHECK_ERROR:
      return "executor check error";
    case ProcessErrorCode::WAITPID_RET_ERROR:
      return "waitpid ret error";
    case ProcessErrorCode::WAITPID_EXIT:
      return "waitpid exit";
    case ProcessErrorCode::WAITPID_SIGNALED:
      return "waitpid signaled";
    case ProcessErrorCode::WAITPID_STOPPED:
      return "waitpid stopped";
    case ProcessErrorCode::WAITPID_CONTINUED:
      return "waitpid continued";
    case ProcessErrorCode::MONITOR_GAT_APP_INFO_ERROR:
      return "monitor get app info error";
    case ProcessErrorCode::INTERNAL_ERROR:
      return "internal error";
    default:
      break;
  }
  return "";
}

}
