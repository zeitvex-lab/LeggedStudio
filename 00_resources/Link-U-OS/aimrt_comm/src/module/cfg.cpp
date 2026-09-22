// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.


#include <cstdlib>
#include <filesystem>
#include <fstream>
#include "gflags/gflags.h"
#include "src/common/util/string_util.h"
#include "src/sys/internal/fs.h"

#include "./cfg.h"
#include "./cfg/env.h"
#include "cfg/utils.h"

namespace aimrte::cfg
{
Ch operator|(const Ch lhs, const Ch rhs)
{
  return static_cast<Ch>(static_cast<std::uint64_t>(lhs) | static_cast<std::uint64_t>(rhs));
}

Rpc operator|(const Rpc lhs, const Rpc rhs)
{
  return static_cast<Rpc>(static_cast<std::uint64_t>(lhs) | static_cast<std::uint64_t>(rhs));
}
}  // namespace aimrte::cfg

namespace aimrte::cfg::details
{
void AddFilter(std::optional<std::vector<Filter>>& filters, const Filter filter)
{
  if (not filters.has_value())
    filters.emplace();

  filters->push_back(filter);
}
}  // namespace aimrte::cfg::details

namespace aimrte
{
DEFINE_string(cfg_file_path, "", "Startup config file path");
DEFINE_bool(no_dump_cfg_file, false, "Do not dump config file");
DEFINE_string(process_name, "", "Process name, which is related to process's log, param, var directories etc.");
DEFINE_string(deployment_file_path, "", "Deployment file path");

static std::string GetProcessName(std::string given_name)
{
  // 进程名称优先级： ${EM_APP_NAME} > --process_name > 代码定义 > 可执行性文件名
  if (std::string env_name = sys::config::EMAppName(); not env_name.empty())
    given_name = std::move(env_name);
  else if (not FLAGS_process_name.empty())
    given_name = FLAGS_process_name;

  if (given_name.empty()) {
    if (std::ifstream comm_file("/proc/self/comm"); comm_file.is_open()) {
      comm_file >> given_name;
    }

    given_name += "_UNNAMED";
  }

  setenv(cfg::details::ENV_PROCESS_NAME.data(), given_name.data(), 1);
  return given_name;
}

static std::string GetDeploymentFilePath()
{
  if (not FLAGS_deployment_file_path.empty()) {
    return FLAGS_deployment_file_path;
  } else {
    return "../config/deployment/deployment.yaml";
  }
}

Cfg::Cfg(const std::vector<std::string>& vargs, std::string process_name)
{
  const auto argc = static_cast<int>(vargs.size());
  auto argv       = new (std::nothrow) char*[argc];

  if (argv == nullptr)
    throw std::bad_alloc();

  AIMRTE(defer(delete[] argv));

  for (int idx = 0; idx < argc; ++idx) {
    const std::string& arg = vargs[idx];
    char* arg_ptr = argv[idx] = new (std::nothrow) char[arg.size() + 1];

    if (arg_ptr == nullptr) {
      for (int jdx = 0; jdx < idx; ++jdx)
        delete[] argv[jdx];

      throw std::bad_alloc();
    }

    std::memcpy(arg_ptr, arg.data(), arg.size());
    arg_ptr[arg.size()] = '\0';
  }

  AIMRTE(defer(
    for (int idx = 0; idx < argc; ++idx) {
      delete[] argv[idx];
    }));

  Construct(argc, argv, std::move(process_name));
}

Cfg::Cfg(int argc, char** argv, std::string process_name)
{
  Construct(argc, argv, std::move(process_name));
}

Cfg& Cfg::SetBackendTopic(const std::string& method, const std::string& topic_name, const std::vector<cfg::Ch>& enable_backends)
{
  if (method == "record") {
    (*this).aimrt_config_.channel.sub_topics_options.push_back({.topic_name = topic_name, .enable_backends = enable_backends});
  } else if (method == "playback") {
    (*this).aimrt_config_.channel.pub_topics_options.push_back({.topic_name = topic_name, .enable_backends = enable_backends});
  }
  return *this;
}

Cfg& Cfg::WithDefaultTimeoutExecutor()
{
  TryAddDefaultTimeoutExecutor();
  return *this;
}

void Cfg::TryAddDefaultTimeoutExecutor()
{
  for (cfg::details::ExeBackend& i : aimrt_config_.executor.executors) {
    if (trait::get_index<cfg::exe::time_wheel, decltype(i)>::value == i.index() and std::get<cfg::exe::time_wheel>(i).name == DEFAULT_TIMEOUT_TIME_WHEEL) {
      return;
    }
  }

  (*this)[cfg::Exe::asio_thread] += {
    .name = std::string(DEFAULT_TIMEOUT_EXECUTOR),
  };
  (*this)[cfg::Exe::time_wheel] += {
    .name    = DEFAULT_TIMEOUT_TIME_WHEEL,
    .options = {{
      .bind_executor = std::string(DEFAULT_TIMEOUT_EXECUTOR),
    }},
  };
}

void Cfg::Construct(int argc, char** argv, std::string process_name)
{
  // 先处理启动参数，确保所有变量得到初始化
  if (argc != 0)
    gflags::ParseCommandLineFlags(&argc, &argv, true);

  // 配置进程相关的内容
  process_name_                            = GetProcessName(std::move(process_name));
  aimrt_config_.configurator.temp_cfg_path = ::fmt::format("{}/cfg", sys::internal::GetTempProcessRoot(process_name_));
  aimrt_config_.main_thread.name           = process_name_;

  // 处理输入的参数
  if (argc == 0)
    return;

  core_.cfg_file_path        = FLAGS_cfg_file_path;
  core_.dump_cfg_file        = not FLAGS_no_dump_cfg_file;
  core_.dump_cfg_file_path   = FLAGS_cfg_file_path.empty() ? ::fmt::format("{}/{}.dump", aimrt_config_.configurator.temp_cfg_path, process_name_) : FLAGS_cfg_file_path + ".dump";
  core_.deployment_file_path = GetDeploymentFilePath();
}

static YAML::Node GetModuleConfigYamlFromRootFile(const std::string& root_file_path, const std::string& module_name)
{
  YAML::Node cfg_file = YAML::LoadFile(root_file_path);

  // 检查是否在 module 中定义了自定义的用户配置路径，如果有，则以它的结果返回
  if (const YAML::Node n{cfg_file["aimrt"]["module"]["modules"]}; n.IsSequence()) {
    for (const YAML::Node& n_i : n) {
      if (n_i["name"].as<std::string>() != module_name)
        continue;

      if (const YAML::Node n_path{n_i["cfg_file_path"]}; n_path.IsDefined())
        return YAML::LoadFile(n_path.as<std::string>());
    }
  }

  // 检查本根文件中是否定义了该模块的配置，有则返回它
  if (const YAML::Node n{cfg_file[module_name]}; n.IsDefined())
    return n;

  // 找不到对应模块的配置，返回空
  return {};
}

static YAML::Node GetDeploymentYaml(const std::string& deployment_file_path)
{
  std::ifstream file(deployment_file_path);
  if (file.is_open()) {
    try {
      YAML::Node deployment_cfg = YAML::LoadFile(deployment_file_path);
      return deployment_cfg;
    } catch (const YAML::Exception& e) {
      AIMRTE_ERROR("Failed to load deployment config file: {}, error: {}", deployment_file_path, e.what());
      return {};
    }
  } else {
    AIMRTE_ERROR("Deployment config file does not exist or cannot be accessed: {}", deployment_file_path);
    return {};
  }
}

YAML::Node Cfg::GetModuleConfigYaml(const std::string& module_name) const
{
  auto module_yaml_cfg = [&]() -> YAML::Node {
    // 若给定了外部的配置，优先从该配置中寻找
    if (not core_.cfg_file_path.empty()) {
      if (const YAML::Node ret = GetModuleConfigYamlFromRootFile(core_.cfg_file_path, module_name); ret.IsDefined() and not ret.IsNull())
        return ret;
    }

    // 查找本配置对象的 module 内容中，是否设置了自定义的用户配置路径，
    // 是则以它的结果返回
    for (const cfg::details::ModuleConfig& i : aimrt_config_.module.modules) {
      if (i.name == module_name and i.cfg_file_path.has_value())
        return YAML::LoadFile(i.cfg_file_path.value());
    }

    // 查找本配置对象是否被直接设置了模块参数，
    // 是则以它作为结果返回
    if (const YAML::Node n{modules_config_[module_name]}; not cfg::details::IsUndefined(n))
      return n;

    // 找不到该模块参数，返回空
    return {};
  }();

  if (module_yaml_cfg.IsNull() or not module_yaml_cfg.IsDefined())
    return module_yaml_cfg = YAML::Null;

  return YAML::Load(aimrt::common::util::ReplaceEnvVars(Dump(module_yaml_cfg)));
}

YAML::Node Cfg::GetMutableModuleConfigYaml(const std::string& module_name)
{
  YAML::Node mod_cfg = modules_config_[module_name];

  if (cfg::details::IsUndefined(mod_cfg)) {
    if (const YAML::Node n = GetModuleConfigYaml(module_name); not cfg::details::IsUndefined(n))
      mod_cfg = n;
  }

  return mod_cfg;
}

YAML::Node Cfg::GetModuleDeploymentInfo() const
{
  auto is_process_name_match = [&](const std::string& name) -> bool {
    return name == process_name_ || name + "_UNNAMED" == process_name_;
  };

  auto check_executable_match = [&](const YAML::Node& executable_node) -> bool {
    if (executable_node.IsScalar()) {
      return is_process_name_match(executable_node.as<std::string>());
    } else if (executable_node.IsSequence()) {
      for (const auto& exec_item : executable_node) {
        if (is_process_name_match(exec_item.as<std::string>())) {
          return true;
        }
      }
    }
    return false;
  };

  auto find_matching_node = [&](const YAML::Node& deployment) -> YAML::Node {
    if (!deployment["spec"] || !deployment["spec"].IsSequence()) {
      return {};
    }

    const auto& spec_array = deployment["spec"];

    // 先查找app字段匹配
    for (const auto& node : spec_array) {
      if (node["app"] && is_process_name_match(node["app"].as<std::string>())) {
        return node;
      }
    }

    // 再查找executable字段匹配
    for (const auto& node : spec_array) {
      if (node["executable"] && check_executable_match(node["executable"])) {
        return node;
      }
    }

    return {};
  };

  auto module_deployment_info = [&]() -> YAML::Node {
    if (core_.deployment_file_path.empty()) {
      return {};
    }

    YAML::Node deployment = GetDeploymentYaml(core_.deployment_file_path);
    return find_matching_node(deployment);
  }();

  if (module_deployment_info.IsNull() or not module_deployment_info.IsDefined())
    return module_deployment_info = YAML::Null;

  return YAML::Load(aimrt::common::util::ReplaceEnvVars(Dump(module_deployment_info)));
}

cfg::backend::plugin::net::Options Cfg::GetNetworkPluginOptions() const
{
  YAML::Node deployment_info = GetModuleDeploymentInfo();
  cfg::backend::plugin::net::Options options;

  if (not deployment_info["net"]) return options;

  const YAML::Node& net_node  = deployment_info["net"];
  auto find_net_plugin_config = [](const YAML::Node& node_array) -> YAML::Node {
    if (not node_array.IsSequence()) return YAML::Node();

    auto check_env_constraint = [](const YAML::Node& constraint_node) -> bool {
      if (not constraint_node.IsDefined() || constraint_node.IsNull()) {
        return true;  // 无约束时默认满足
      }

      if (constraint_node["env"] && constraint_node["env"].IsMap()) {
        for (const auto& env_pair : constraint_node["env"]) {
          const std::string env_name   = env_pair.first.as<std::string>();
          const YAML::Node& env_values = env_pair.second;

          // 获取环境变量的实际值
          const char* env_value = std::getenv(env_name.c_str());
          if (env_value == nullptr) {
            return false;  // 环境变量不存在
          }

          std::string actual_value = env_value;

          // 检查是否在允许的值列表中
          if (env_values.IsSequence()) {
            bool found = false;
            for (const auto& allowed_value : env_values) {
              if (allowed_value.as<std::string>() == actual_value) {
                found = true;
                break;
              }
            }
            if (not found) {
              return false;  // 环境变量值不在允许列表中
            }
          } else if (env_values.IsScalar()) {
            if (env_values.as<std::string>() != actual_value) {
              return false;  // 环境变量值不匹配
            }
          }
        }
      }

      return true;  // 所有约束都满足
    };

    for (const auto& item : node_array) {
      if (item["is_net_plugin"] && item["is_net_plugin"].as<bool>(false)) {
        if (check_env_constraint(item["constraint"])) {
          return item;
        }
      }
    }
    return YAML::Node();
  };

  auto configure_network_option = [&](const std::string& protocol_name, auto& option_field) {
    const std::string node_key = protocol_name;
    if (net_node[node_key] && net_node[node_key].IsDefined()) {
      if (auto config = find_net_plugin_config(net_node[node_key])) {
        using OptionType = std::decay_t<decltype(option_field.value())>;
        OptionType option;

        if (config["listen_port"]) {
          option.listen_port = config["listen_port"].as<int>(0);
        }
        if (config["listen_ip"]) {
          option.listen_ip = config["listen_ip"].as<std::string>("");
        }

        // UDP特有的字段
        if constexpr (std::is_same_v<OptionType, cfg::backend::plugin::net::UdpOption>) {
          if (config["max_pkg_size"]) {
            option.max_pkg_size = config["max_pkg_size"].as<int>(0);
          }
        }

        option_field = option;
      }
    }
  };

  configure_network_option("http", options.http_options);
  configure_network_option("tcp", options.tcp_options);
  configure_network_option("udp", options.udp_options);

  return options;
}

Cfg& Cfg::SetDefaultLogLevel(const cfg::LogLevel level)
{
  aimrt_config_.log.default_module_lvl = level;
  return *this;
}

Cfg& Cfg::SetCoreLogLevel(const cfg::LogLevel level)
{
  aimrt_config_.log.core_lvl = level;
  return *this;
}
}  // namespace aimrte
