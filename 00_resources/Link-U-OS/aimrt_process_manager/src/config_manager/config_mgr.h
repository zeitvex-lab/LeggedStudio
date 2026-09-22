// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>
#include <map>
#include <vector>
#include <cstdint>

#include "yaml-cpp/yaml.h"

namespace process_manager
{

using EnvVar = std::map<std::string, std::string>;

class ConfigManager
{
 public:
  struct GuardOption {
    uint32_t delay_ms{10000};  // 默认为10s
    int32_t max_retries{-1};
    std::string policy;
  };

  struct AppInfo {
    uint64_t user_uid;
    uint64_t user_gid;
    std::string app_name;
    std::string app_file_path;
    bool use_sudo{false};
    std::vector<std::string> args_list;
    std::vector<std::string> path_env;   // PATH 环境变量的内容
    EnvVar env_map;                      // 配置文件传入的宏定义信息
    GuardOption guard_option;  // 后期会废弃
    std::string stdout_path;
    std::string stderror_path;
  };

  // 预留扩展信息
  struct ProcessOption{
    std::string work_dir;
    uint64_t user_uid;
    uint64_t user_gid;
    std::string env_file;
    std::vector<std::string> default_app_list;

    std::map<std::string, AppInfo> app_name_to_info_map;
  };

  struct WorkOption{
    // aima_cli
    int32_t aima_req_thread_num;
    std::string aima_listen_ip{"127.0.0.1"};
    uint16_t aima_req_port{50080};

    // node_control
    int32_t node_control_thread_num;
    std::string node_control_listen_ip{"192.168.100.100"};
    uint16_t node_control_port{56999};
    // 标记是否为master节点
    bool master_node{true};

    // domain_socket
    int domain_socket_thread_num;

    // util
    bool std_safe_log_enable{false};  // 产生额外日志文件的日志打印开关
    int max_std_safe_log_num{50};     // 日志文件的最大保存数量
  };

 public:
  ConfigManager() {}
  ~ConfigManager() {}

  bool LoadProcessManagerCfg(const YAML::Node& cfg_node);

  const EnvVar& GetEnv() const { return env_list_; }

  const ProcessOption& GetProcessOption() const { return option_; }

  const WorkOption& GetWorkOption() const { return work_option_; };

 private:
  bool LoadRunAgibotCfg(const std::string& run_agibot_file);

  bool LoadWorkCfg(const YAML::Node& work_node);

  bool LoadModuleCfg(const YAML::Node& model_node);

  std::vector<std::string> SplitPath(std::string_view path, char delimiter = ':');

  void PrintOption();

 private:
  std::string cfg_file_path_;
  ProcessOption option_;
  EnvVar env_list_;

  WorkOption work_option_;
};

using AppInfo = ConfigManager::AppInfo;
using ProcessOption = ConfigManager::ProcessOption;

}
