// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <mutex>
#include <filesystem>

#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>

#include "src/config_manager/config_mgr.h"
#include "src/util/process_error_code.h"

#include "src/util/global.h"

namespace process_manager
{

// 默认需要传递给子进程的当前shell的环境变量
#define BASE_PRESERVE_ENV "ROS_LOCALHOST_ONLY,ROS_DOMAIN_ID,LOG_PATH,LD_LIBRARY_PATH,DISABLE_MQTT_NGINX"


class Executor {
 public:
  Executor(const AppInfo& info, const EnvVar& env_var)
    : info_(info), env_var_(env_var) {}
  ~Executor() {}

  // 重置状态
  void Reset();

  // 初始化
  bool Init();

  // 支持运行期间修改环境配置, 支持io 重定向配置
  bool UpdateEnvCfg(const std::string& key, const std::string& val);

  ProcessErrorCode ExecutorValidate();

  ProcessErrorCode PrepareExecution();

  // 正常情况下不会返回
  bool StartExec();

  // 在父进程中执行
  void PrintExecutorArgs();

 private:
  bool CheckExecutor(const std::filesystem::path& path);

  void MergeAppEnv();

  void MergeArgsList();

  bool SetUser();
  bool SetEnv();
  bool SetStdoutStdErr();
  bool SetSession();

  void CleanFdFromParent();

 private:
  const AppInfo& info_;
  const EnvVar& env_var_;

  const std::string base_preserve_env_{BASE_PRESERVE_ENV};

  std::string stdout_path_;
  std::string stderr_path_;

  EnvVar merge_env_var_;

  std::vector<std::string> prepare_args_list_;
};

}
