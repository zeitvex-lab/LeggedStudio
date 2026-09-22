// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "config_mgr.h"

#include <filesystem>
#include <fstream>

#include "src/common/util/string_util.h"

#include "src/util/global.h"


namespace process_manager
{

bool ConfigManager::LoadProcessManagerCfg(const YAML::Node& cfg_node) {
  if (!cfg_node["run_agibot_file"].IsDefined()) {
    AIMRT_ERROR("Init failed. empty run_agibot_file configuration");
    return false;
  }

  std::string run_agibot_file = cfg_node["run_agibot_file"].as<std::string>();
  if (!LoadRunAgibotCfg(run_agibot_file)) {
    return false;
  }

  if (!LoadModuleCfg(cfg_node)) {
    return false;
  }

  return true;
}

bool ConfigManager::LoadRunAgibotCfg(const std::string& run_agibot_file)
{
  YAML::Node ori_root_options_node;
  try
  {
    cfg_file_path_ = std::filesystem::canonical(std::filesystem::absolute(run_agibot_file));
    AIMRT_INFO("Cfg file path: {}", run_agibot_file);

    std::ifstream file_stream(cfg_file_path_);

    if (!file_stream) [[unlikely]] {
      AIMRT_ERROR("Can not open cfg file '{}'.", cfg_file_path_);
      return false;
    }

    std::stringstream file_data;
    file_data << file_stream.rdbuf();
    // 替换环境变量,之后统一进行解析

    std::string file_data_str = aimrt::common::util::ReplaceEnvVars(file_data.str());
    AIMRT_DEBUG("cfg: {}", file_data_str);

    ori_root_options_node = YAML::Load(file_data_str);

    // 基本校验
    if (!ori_root_options_node.IsMap()) return false;

    const auto& root_cfg = ori_root_options_node["process_manager"];
    if (!root_cfg) return false;

    option_.work_dir = root_cfg["work_dir"].as<std::string>();
    option_.user_uid = root_cfg["agi_user_uid"].as<uint64_t>();
    option_.user_gid = root_cfg["agi_user_gid"].as<uint64_t>();
    option_.env_file = root_cfg["env_file"].as<std::string>();

    option_.default_app_list = root_cfg["default_apps"].as<std::vector<std::string>>();


    // 获取PATH 的环境变量信息
    const char* env_path = std::getenv("PATH");
    if (env_path == nullptr) {
      AIMRT_ERROR("getenv PATH failed. return nullptr.");
      return false;
    }
    std::vector<std::string> path_env = SplitPath(env_path);
    AIMRT_INFO("Get PATH item size: {}", path_env.size());


    const auto& apps = root_cfg["apps"];
    for (const auto& app : apps) {
      AppInfo  info;
      std::string info_name;
      info.app_name = info_name = app.first.as<std::string>();
      info.user_gid = option_.user_gid;
      info.user_uid = option_.user_uid;
      info.path_env = path_env;

      const auto& content = app.second;
      info.app_file_path = content["path"].as<std::string>();
      info.use_sudo = content["sudo"].as<bool>(false);
      info.args_list = content["args"].as<std::vector<std::string>>(std::vector<std::string>());

      const auto& envs = content["env"];
      for (const auto& env : envs) {
        info.env_map.emplace(env.first.as<std::string>(), env.second.as<std::string>());
      }
      const auto& guards = content["restart"];
      if (guards) {
        info.guard_option.delay_ms = guards["delay_ms"].as<uint32_t>();
        info.guard_option.max_retries = guards["max_retries"].as<int32_t>();
        info.guard_option.policy = guards["policy"].as<std::string>();
      }
      info.stdout_path = content["stdout"].as<std::string>("");
      info.stderror_path = content["stderror"].as<std::string>("");
      option_.app_name_to_info_map.emplace(info_name, std::move(info));
    }
    AIMRT_INFO("load app_info {}", option_.app_name_to_info_map.size());

    // 校验 default_app 能否在 app_name_to_info中找到
    for (const auto& app_name : option_.default_app_list) {
      auto iter = option_.app_name_to_info_map.find(app_name);
      if (iter == option_.app_name_to_info_map.end()) {
        AIMRT_ERROR("can't find app_name: {} in app info", app_name);
        return false;
      }
    }

    if (!LoadWorkCfg(ori_root_options_node["worker_info"])) {
      return false;
    }
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("LoadRunAgibotCfg catch exception: {}, run_agibot_file: {}", e.what(), run_agibot_file);
    return false;
  }

  try
  {
    std::string env_file = std::filesystem::canonical(std::filesystem::absolute(option_.env_file));
    AIMRT_INFO("Cfg env_file path: {}", env_file);

    std::ifstream file_stream(env_file);

    if (!file_stream) [[unlikely]] {
      AIMRT_ERROR("Can not open env_file file '{}'.", env_file);
      return false;
    }

    std::stringstream file_data;
    file_data << file_stream.rdbuf();
    // 替换环境变量,之后统一进行解析

    std::string file_data_str = aimrt::common::util::ReplaceEnvVars(file_data.str());
    AIMRT_DEBUG("cfg: {}", file_data_str);

    const auto& env_node = YAML::Load(file_data_str);

    // 基本校验
    if (!env_node.IsMap()) return false;

    const auto& env_root_cfg = env_node["envs"];
    if (!env_root_cfg) return false;

    for (const auto& env : env_root_cfg) {
      env_list_.emplace(env.first.as<std::string>(), env.second.as<std::string>());
    }
    AIMRT_INFO("load envs {}", env_list_.size());
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("LoadEnvCfg catch exception: {}, env_file: {}", e.what(), option_.env_file);
  }

  return true;
}

std::vector<std::string> ConfigManager::SplitPath(std::string_view path, char delimiter) {
  std::vector<std::string> paths;
  size_t start = 0;
  size_t end = path.find(delimiter);

  while (end != std::string_view::npos) {
      if (end != start) { // 忽略空路径
          paths.emplace_back(path.substr(start, end - start));
      }
      start = end + 1;
      end = path.find(delimiter, start);
  }

  if (start < path.size()) {
      paths.emplace_back(path.substr(start));
  }

  return paths;
}

bool ConfigManager::LoadWorkCfg(const YAML::Node& work_node) {
  const auto& aima_req_cfg = work_node["aima_req_worker"];
  if (!aima_req_cfg) return false;

  work_option_.aima_req_thread_num = aima_req_cfg["thread_num"].as<int32_t>(2);
  work_option_.aima_req_port = aima_req_cfg["listen_port"].as<uint16_t>(50080);
  work_option_.aima_listen_ip = aima_req_cfg["listen_ip"].as<std::string>("127.0.0.1");

  AIMRT_INFO("aima_req, thread_num: {}, ip: {}, port: {}", work_option_.aima_req_thread_num, work_option_.aima_listen_ip, work_option_.aima_req_port);

  const auto& node_control_cfg = work_node["node_control_worker"];
  if (!node_control_cfg) return false;

  work_option_.node_control_thread_num = node_control_cfg["thread_num"].as<int32_t>(1);
  work_option_.node_control_port = node_control_cfg["listen_port"].as<uint16_t>(56999);
  work_option_.node_control_listen_ip = node_control_cfg["listen_ip"].as<std::string>("192.168.100.100");
  work_option_.master_node = node_control_cfg["master_node"].as<bool>(true);

  AIMRT_INFO("node_control_cfg, thread_num: {}, ip: {}, port: {}", work_option_.node_control_thread_num, work_option_.node_control_listen_ip, work_option_.node_control_port);
  AIMRT_INFO("node_control_cfg: master_node: {}", work_option_.master_node ? "true" : "false");

  return true;
}

bool ConfigManager::LoadModuleCfg(const YAML::Node& module_node) {
  try
  {
    work_option_.domain_socket_thread_num = module_node["domain_socket_thread_num"].as<int32_t>(8);
    AIMRT_INFO("domain_socket thread num: {}", work_option_.domain_socket_thread_num);

    work_option_.std_safe_log_enable = module_node["std_safe_log_enable"].as<bool>(false);
    AIMRT_INFO("std_safe log enable: {}", (work_option_.std_safe_log_enable ? "True" : "False"));

    work_option_.max_std_safe_log_num = module_node["max_std_safe_log_num"].as<int32_t>(50);
    AIMRT_INFO("max std log num: {}", work_option_.max_std_safe_log_num);
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("LoadModuleCfg failed, {}", e.what());
    return false;
  }

  return true;
}

void ConfigManager::PrintOption()
{
}


}
