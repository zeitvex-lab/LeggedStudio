// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include <fmt/format.h>
#include <netdb.h>
#include <sys/socket.h>
#include "src/common/util/string_util.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <random>
#include <rfl/yaml.hpp>
#include <sstream>
#include <stack>
#include <string>
#include <string_view>
#include <type_traits>
#include "src/sys/internal/config.h"

#include "./cfg/utils.h"
#include "./cfg_processor.h"
#include "cfg.h"

namespace aimrte::details
{
template <class TBackends>
void ReflectBackendFromYaml(TBackends& backend, const YAML::Node& backend_node);

template <>
void ReflectBackendFromYaml(cfg::details::LogBackend& backend, const YAML::Node& backend_node)
{
#define AIMRTE_DETAILS_IMPL(_, _type_)           \
  else if (std::get<0>(backend).type == #_type_) \
    backend = rfl::yaml::read<cfg::backend::log::_type_>(backend_node).value();

  if constexpr (false)
    ;
  AIMRTE_DETAILS_CFG_LOGGER_INVOKE(AIMRTE_DETAILS_IMPL)
  else panic().wtf("");
#undef AIMRTE_DETAILS_IMPL
}

template <>
void ReflectBackendFromYaml(cfg::details::PluginBackend& backend, const YAML::Node& backend_node)
{
#define AIMRTE_DETAILS_IMPL(_, _type_)                     \
  else if (std::get<0>(backend).name == #_type_ "_plugin") \
    backend = rfl::yaml::read<cfg::backend::plugin::_type_>(backend_node).value();

  if constexpr (false)
    ;
  AIMRTE_DETAILS_CFG_PLUGIN_INVOKE(AIMRTE_DETAILS_IMPL)
  else panic().wtf("");
#undef AIMRTE_DETAILS_IMPL
}

template <>
void ReflectBackendFromYaml(cfg::details::ChBackend& backend, const YAML::Node& backend_node)
{
#define AIMRTE_DETAILS_IMPL(_, _type_)           \
  else if (std::get<0>(backend).type == #_type_) \
    backend = rfl::yaml::read<cfg::backend::ch::_type_>(backend_node).value();

  if constexpr (false)
    ;
  AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(AIMRTE_DETAILS_IMPL)
  else panic().wtf("");
#undef AIMRTE_DETAILS_IMPL
}

template <>
void ReflectBackendFromYaml(cfg::details::RpcBackend& backend, const YAML::Node& backend_node)
{
#define AIMRTE_DETAILS_IMPL(_, _type_)           \
  else if (std::get<0>(backend).type == #_type_) \
    backend = rfl::yaml::read<cfg::backend::rpc::_type_>(backend_node).value();

  if constexpr (false)
    ;
  AIMRTE_DETAILS_CFG_RPC_INVOKE(AIMRTE_DETAILS_IMPL)
  else panic().wtf("");
#undef AIMRTE_DETAILS_IMPL
}

template <>
void ReflectBackendFromYaml(cfg::details::ExeBackend& backend, const YAML::Node& backend_node)
{
#define AIMRTE_DETAILS_IMPL(_, _type_)           \
  else if (std::get<0>(backend).type == #_type_) \
    backend = rfl::yaml::read<cfg::exe::_type_>(backend_node).value();

  if constexpr (false)
    ;
  AIMRTE_DETAILS_CFG_EXE_INVOKE(AIMRTE_DETAILS_IMPL)
  else panic().wtf("");
#undef AIMRTE_DETAILS_IMPL
}

template <class TBackends>
void ReflectBackendsFromYaml(std::vector<TBackends>& backends, const YAML::Node& backends_node)
{
  for (std::size_t idx = 0; idx < backends.size(); ++idx) {
    ReflectBackendFromYaml(backends[idx], backends_node[idx]);
  }
}
}  // namespace aimrte::details

namespace aimrte
{

Cfg::Processor::Processor(Cfg& cfg) : cfg_(cfg) {}

void Cfg::Processor::SetUserPatchConfigFilePaths(std::vector<std::string> paths)
{
  user_patch_config_file_paths_ = std::move(paths);
}

void Cfg::Processor::AddDefaultLocal()
{
  cfg_.WithDefaultLocal();
}

void Cfg::Processor::AddHDSCfg()
{
  const auto HDS_TOPIC = "/aima/hds/exception";

  auto& pub_options = cfg_.aimrt_config_.channel.pub_topics_options;
  std::remove_cvref_t<decltype(*pub_options.begin())> pub_option{HDS_TOPIC};

  if (const std::string backend_type = sys::config::FeatureHDSNewBackend(); backend_type == "ros2") {
    cfg_.WithDefaultRos();
    pub_option.enable_backends = {cfg::Ch::ros2};
  } else if (backend_type == "zenoh") {
    cfg_.WithDefaultZenoh();
    pub_option.enable_backends = {cfg::Ch::zenoh};
  } else if (backend_type == "udp") {
    AddDefaultNet();
    AddCommunicationOption(
      cfg::backend::ch::udp::PubOption{
        .topic_name      = HDS_TOPIC,
        .server_url_list = {
          utils::Env("HDS_MONITOR_IP", "127.0.0.1") + ":51587",
          utils::Env("DATA_PROXY_IP", "192.168.100.110") + ":54583",
          utils::Env("RECORD_BAG_IP", "192.168.100.110") + ":52593",
        },
      });
    pub_option.enable_backends = {cfg::Ch::udp};
  }

  pub_options.insert(pub_options.begin(), std::move(pub_option));
}

void Cfg::Processor::AddTraceEventCfg()
{
  cfg_.WithDefaultRos();

  const auto Trace_TOPIC = "/aimrte/trace/events";

  // 基于 ros2 来发送异常码
  cfg_.aimrt_config_.channel.pub_topics_options.insert(cfg_.aimrt_config_.channel.pub_topics_options.begin(), {Trace_TOPIC, {cfg::Ch::ros2}});
}

void Cfg::Processor::AddMonitorCfg()
{
  if (not sys::config::EnableMonitor())
    return;

  constexpr auto DEFAULT_MONITOR_EXECUTOR = "default_monitor_executor";
  constexpr auto HEARTBEAT_TOPIC          = "/aima/heartbeat";

  cfg_[cfg::backend::Plugin::monitor] = {.options = {.executor = DEFAULT_MONITOR_EXECUTOR}};
  cfg_[cfg::backend::Ch::monitor]     = {};
  cfg_[cfg::backend::Rpc::monitor]    = {};
  cfg_[cfg::Exe::asio_thread] += {
    .name    = DEFAULT_MONITOR_EXECUTOR,
    .options = {{
      .thread_num = 3,
    }},
  };

  auto& pub_options = cfg_.aimrt_config_.channel.pub_topics_options;
  std::remove_cvref_t<decltype(*pub_options.begin())> pub_option{HEARTBEAT_TOPIC};

  if (const std::string backend_type = sys::config::FeatureHeartbeatNewBackend(); backend_type == "ros2") {
    cfg_.WithDefaultRos();
    pub_option.enable_backends = {cfg::Ch::ros2};
  } else if (backend_type == "zenoh") {
    cfg_.WithDefaultZenoh();
    pub_option.enable_backends = {cfg::Ch::zenoh};
  } else if (backend_type == "mqtt") {
    cfg_.WithDefaultMqtt();
    pub_option.enable_backends = {cfg::Ch::mqtt};
  }

  pub_options.insert(pub_options.begin(), std::move(pub_option));
  cfg_.aimrt_config_.channel.AddFilter(cfg::Filter::monitor);
}

void Cfg::Processor::AddVizCfg()
{
  if (not sys::config::EnableViz())
    return;

  constexpr auto DEFAULT_VIZ_EXECUTOR = "default_viz_executor";
  auto VIZ_RPC_SERVICE                = "pb:/" + cfg::details::ProcName() + "/GetNodeInfo";
  // pb:/channel_sub_viz/GetNodeInfo

  std::string soc = sys::GetSOCIndex() == 1 ? "orin" : "x86_64";

  cfg_[cfg::backend::Plugin::viz] = {.options = {.executor = DEFAULT_VIZ_EXECUTOR, .soc = soc}};

  cfg_[cfg::Exe::asio_thread] += {
    .name    = DEFAULT_VIZ_EXECUTOR,
    .options = {{
      .thread_num = 3,
    }},
  };

  auto& svr_options = cfg_.aimrt_config_.rpc.servers_options;
  std::remove_cvref_t<decltype(*svr_options.begin())> viz_svr_option(VIZ_RPC_SERVICE);

  cfg_.WithDefaultRos();
  viz_svr_option.enable_backends = {cfg::Rpc::ros2};
  svr_options.insert(svr_options.begin(), std::move(viz_svr_option));
  cfg_.aimrt_config_.channel.AddFilter(cfg::Filter::viz);
  cfg_.aimrt_config_.rpc.AddFilter(cfg::Filter::viz);
}

void Cfg::Processor::AddLogControlCfg()
{
  if (not sys::config::EnableLogControl())
    return;

  // 添加日志等级控制插件
  cfg_[cfg::backend::Plugin::log_control] = {};

  // 基于 http 接收日志等级的控制指令
  cfg_.aimrt_config_.rpc.servers_options.insert(cfg_.aimrt_config_.rpc.servers_options.begin(), {R"((pb:/aimrt\.protocols\.log_control_plugin\.LogControlService/.*))", {cfg::Rpc::http}});

  // 启用默认的网络通信能力
  AddDefaultNet();
}

void Cfg::Processor::AddDefaultNet()
{
  bool need_http_backend = false;
  bool need_tcp_backend  = false;
  bool need_udp_backend  = false;

  const bool net_plugin_existed = cfg::details::Visit<cfg::backend::plugin::net>(
    cfg_.aimrt_config_.plugin.plugins,
    [&](cfg::backend::plugin::net& x) {
      if (x.options.http_options) {
        need_http_backend = true;
      }
      if (x.options.tcp_options) {
        need_tcp_backend = true;
      }
      if (x.options.udp_options) {
        need_udp_backend = true;
      }
    });

  auto network_options = cfg_.GetNetworkPluginOptions();

  // 检查是否需要配置默认net plugin (当任何一个条件满足时)
  need_http_backend = need_http_backend || network_options.http_options.has_value();
  need_tcp_backend  = need_tcp_backend || network_options.tcp_options.has_value();
  need_udp_backend  = need_udp_backend || network_options.udp_options.has_value() || sys::config::FeatureHDSNewBackend() == "udp";

  // 如果net_plugin不存在但需要网络后端支持，则创建默认net plugin
  if (not net_plugin_existed && (need_http_backend || need_tcp_backend || need_udp_backend)) {
    cfg_[cfg::backend::Plugin::net] = {
      .options = {
        .thread_num = 1,
      },
    };
  }

  auto configure_net_options = [&](auto& net_options) {
    // 只有当网络选项中配置了某种类型的端口时，才进行配置
    if (network_options.http_options.has_value()) {
      net_options.http_options = network_options.http_options.value();
    }

    if (network_options.tcp_options.has_value()) {
      net_options.tcp_options = network_options.tcp_options.value();
    }

    if (network_options.udp_options.has_value()) {
      net_options.udp_options = network_options.udp_options.value();
    }
  };

  // 配置网络选项 (现在net_plugin一定存在，要么原来就存在，要么刚创建的默认配置)
  cfg::details::Visit<cfg::backend::plugin::net>(
    cfg_.aimrt_config_.plugin.plugins,
    [&](cfg::backend::plugin::net& x) {
      configure_net_options(x.options);
    });

  // 只有配置了对应类型的端口时，才设置相应的 channel 与 rpc 的 backend 支持
  if (need_http_backend) {
    cfg_[cfg::backend::Ch::http] |= {};
    cfg_[cfg::backend::Rpc::http] |= {};
  }
  if (need_tcp_backend) {
    cfg_[cfg::backend::Ch::tcp] |= {};
  }
  if (need_udp_backend) {
    cfg_[cfg::backend::Ch::udp] |= {};
  }
}

void Cfg::Processor::AddDefaultBackends()
{
  for (const std::string& i : sys::config::DefaultChannelBackends()) {
    switch (rfl::string_to_enum<cfg::Ch>(i).value_or(cfg::Ch::Default)) {
      case cfg::Ch::ros2:
        cfg_.WithDefaultRos();
        break;
      case cfg::Ch::mqtt:
        cfg_.WithDefaultMqtt();
        break;
      case cfg::Ch::zenoh:
        cfg_.WithDefaultZenoh();
        break;
      case cfg::Ch::iceoryx:
        cfg_.WithDefaultIceoryx();
        break;
      default:
        panic().wtf("CANNOT set [{}] as default channel backend !", i);
    }
  }

  for (const std::string& i : sys::config::DefaultRpcBackends()) {
    switch (rfl::string_to_enum<cfg::Rpc>(i).value_or(cfg::Rpc::Default)) {
      case cfg::Rpc::ros2:
        cfg_.WithDefaultRos();
        break;
      case cfg::Rpc::mqtt:
        cfg_.WithDefaultMqtt();
        break;
      case cfg::Rpc::zenoh:
        cfg_.WithDefaultZenoh();
        break;
      default:
        panic().wtf("CANNOT set [{}] as default rpc backend !", i);
    }
  }

  // 用于反射字符串名称到枚举量
  enum class LoggerType : std::uint64_t {
    Unknown,
#define AIMRTE_DETAILS_IMPL(_idx_, _type_) _type_,
    AIMRTE_DETAILS_CFG_LOGGER_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL
  };

  for (const std::string& i : sys::config::DefaultLoggerBackends()) {
    switch (rfl::string_to_enum<LoggerType>(i).value_or(LoggerType::Unknown)) {
      case LoggerType::console:
        cfg_[cfg::backend::Log::console] |= {};
        break;
      case LoggerType::rotate_file:
        cfg_[cfg::backend::Log::rotate_file] |= {};
        break;
      case LoggerType::topic_logger:
        cfg_.TryAddTopicLogger();
        break;
      default:
        panic().wtf("CANNOT set [{}] as default logger backend !", i);
    }
  }
}

void Cfg::Processor::AddCommunicationOption(cfg::backend::ch::udp::PubOption option)
{
  cfg::details::Visit<cfg::backend::ch::udp>(
    cfg_.aimrt_config_.channel.backends,
    [&](cfg::backend::ch::udp& backend) {
      if (not backend.options.has_value())
        backend.options.emplace();

      if (not backend.options->pub_topics_options.has_value())
        backend.options->pub_topics_options.emplace();

      backend.options->pub_topics_options->insert(backend.options->pub_topics_options->begin(), std::move(option));
    });
}

void Cfg::Processor::SetRos2ChannelQos()
{
  const std::string yaml_str = sys::config::FeatureRos2ChannelQos();
  if (yaml_str.empty())
    return;

  cfg::details::Visit<cfg::backend::ch::ros2>(
    cfg_.aimrt_config_.channel.backends,
    [&](cfg::backend::ch::ros2& x) {
      cfg::backend::ch::ros2::QosOptions qos = rfl::yaml::read<cfg::backend::ch::ros2::QosOptions>(yaml_str).value();

      if (not x.options.has_value())
        x.options.emplace();

      if (not x.options->pub_topics_options.has_value())
        x.options->pub_topics_options.emplace();

      if (not x.options->sub_topics_options.has_value())
        x.options->sub_topics_options.emplace();

      x.options->pub_topics_options->push_back({"(.*)", qos});
      x.options->sub_topics_options->push_back({"(.*)", qos});
    });
}

void Cfg::Processor::SetLogSync()
{
  const int sync_interval = sys::config::FeatureLogSyncInterval();
  if (sync_interval <= 0)
    return;

  cfg::details::Visit<cfg::backend::log::rotate_file>(
    cfg_.aimrt_config_.log.backends,
    [&](cfg::backend::log::rotate_file& x) {
      constexpr auto DEFAULT_LOG_SYNC_EXECUTOR = "default_log_sync_executor";

      x.options.enable_sync        = true;
      x.options.sync_interval_ms   = sync_interval;
      x.options.sync_executor_name = DEFAULT_LOG_SYNC_EXECUTOR;

      cfg_[cfg::Exe::asio_thread] += {
        .name = DEFAULT_LOG_SYNC_EXECUTOR,
      };
    });
}

void Cfg::Processor::InjectDefaultCfg()
{
  AddDefaultBackends();
  AddHDSCfg();
  AddLogControlCfg();
  AddTraceEventCfg();
  AddMonitorCfg();
  AddVizCfg();
  AddDefaultLocal();

  SetRos2ChannelQos();
  SetLogSync();
}

void Cfg::Processor::InjectDefaultCfgToAimRTNode(YAML::Node res)
{
  // 将合并后的 aimrt config node （以外部配置优先，可能删掉了一些内部配置）重新反射回配置对象，
  // 由于 rfl 的问题，std::variant 的内容总是会映射到第一个类型，也即各个 meta 类型，仅包含关键字段
  cfg_.aimrt_config_ = rfl::yaml::read<decltype(cfg_.aimrt_config_)>(res).value();

  // 恢复所有的 std::variant 字段内容
  details::ReflectBackendsFromYaml(cfg_.aimrt_config_.log.backends, res["log"]["backends"]);
  details::ReflectBackendsFromYaml(cfg_.aimrt_config_.plugin.plugins, res["plugin"]["plugins"]);
  details::ReflectBackendsFromYaml(cfg_.aimrt_config_.channel.backends, res["channel"]["backends"]);
  details::ReflectBackendsFromYaml(cfg_.aimrt_config_.rpc.backends, res["rpc"]["backends"]);
  details::ReflectBackendsFromYaml(cfg_.aimrt_config_.executor.executors, res["executor"]["executors"]);

  // 注入默认配置到 cfg 配置对象中
  InjectDefaultCfg();

  // 直接使用注入后的结果
  res = YAML::Load(rfl::yaml::write(cfg_.aimrt_config_));
}

void Cfg::Processor::AddModuleConfig(const ctx::ModuleCfg& cfg)
{
  // 新增本模块配置
  cfg_[cfg::module] += cfg.config_;

  // 统计该模块使用的通信资源，合并到全局集合中
  const auto record_module_resource_cfg =
    []<class EType, class TConfig>(const std::list<TConfig>& src, std::map<std::string, std::set<EType>>& dst, const std::initializer_list<EType>& types) {
      for (const TConfig& src_i : src) {
        for (const EType type : types) {
          if (static_cast<std::uint64_t>(type) & static_cast<std::uint64_t>(src_i.methods))
            dst[src_i.name].insert(type);
        }
      }
    };

#define AIMRTE_DETAILS_IMPL(_, _type_) , cfg::Ch::_type_
  const auto ch_types = {cfg::Ch::Default AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(AIMRTE_DETAILS_IMPL)};
#undef AIMRTE_DETAILS_IMPL

#define AIMRTE_DETAILS_IMPL(_, _type_) , cfg::Rpc::_type_
  const auto rpc_types = {cfg::Rpc::Default AIMRTE_DETAILS_CFG_RPC_INVOKE(AIMRTE_DETAILS_IMPL)};
#undef AIMRTE_DETAILS_IMPL

  record_module_resource_cfg(cfg.pubs_, pubs_, ch_types);
  record_module_resource_cfg(cfg.subs_, subs_, ch_types);
  record_module_resource_cfg(cfg.clis_, clis_, rpc_types);
  record_module_resource_cfg(cfg.srvs_, srvs_, rpc_types);

  // 统计该模块使用的执行器资源，合并到全局集合中。若出现重复定义的执行器，则进行报错
  for (const cfg::details::ExeConfig& src_i : cfg.exes_) {
    if (not src_i.option.has_value())
      continue;

    cfg::details::ExeConfig& dst_i = exes_[src_i.name];

    if (dst_i.option.has_value())
      panic().wtf("multiple defined executor {} in different modules !", src_i.name);

    dst_i = src_i;
  }
}

cfg::details::CoreConfig Cfg::Processor::GetCoreConfig() const
{
  return cfg_.core_;
}

std::string Cfg::Processor::DumpFile()
{
  // 准备好配置对象 yaml 以及用户从外部给定的 yaml
  YAML::Node yaml = MakeYamlFromCfg();
  YAML::Node ext_yaml;

  if (not cfg_.core_.cfg_file_path.empty()) {
    ext_yaml = ReadYaml(cfg_.core_.cfg_file_path);
  }

  // 合并框架配置
  MergeAimRTNode(yaml["aimrt"], ext_yaml["aimrt"]);

  // 注入框架的默认配置
  InjectDefaultCfgToAimRTNode(yaml["aimrt"]);

  // 应用外部配置之前的补丁
  for (const std::string& i : sys::config::PatchBeforeConfigFiles()) {
    YAML::Node patch = ReadYaml(i);
    PatchAimRTNode(yaml["aimrt"], patch["aimrte"]);
  }

  // 应用外部配置中的补丁
  current_processing_yaml_file_path_ = cfg_.core_.cfg_file_path;
  PatchAimRTNode(yaml["aimrt"], ext_yaml["aimrte"]);

  // 应用启动参数给定的额外补丁
  for (const std::string& i : user_patch_config_file_paths_) {
    YAML::Node patch = ReadYaml(i);
    PatchAimRTNode(yaml["aimrt"], patch["aimrte"]);
  }

  // 应用外部配置之后的补丁
  for (const std::string& i : sys::config::PatchAfterConfigFiles()) {
    YAML::Node patch = ReadYaml(i);
    PatchAimRTNode(yaml["aimrt"], patch["aimrte"]);
  }

  // 合并模块配置
  MergeCustomNodes(yaml, ext_yaml);

  // 将合并后的最终配置，写到临时的配置文件中，供框架加载，
  // 使用随机数，避免可能得进程多开碰撞，但又避免文件数量无限变多
  std::default_random_engine e(std::chrono::system_clock::now().time_since_epoch().count());
  std::uniform_int_distribution u(0, 10);

  std::string file_root = cfg_.aimrt_config_.configurator.temp_cfg_path;
  std::string file_name = ::fmt::format("{}/tmp{}.yaml", file_root, u(e));

  if (not std::filesystem::exists(file_root))
    std::filesystem::create_directories(file_root);

  std::ofstream file(file_name);
  file << Dump(yaml);
  return file_name;
}

YAML::Node Cfg::Processor::MakeYamlFromCfg()
{
  // 将各个模块配置的通信资源信息，注入到框架配置对象中
  const auto collect_module_resource_cfg =
    []<class EType, class TOption>(const std::map<std::string, std::set<EType>>& src, std::vector<TOption>& dst) {
      dst.reserve(src.size());

      for (auto& [name, types] : src) {
        dst.push_back({name, {types.begin(), types.end()}});
      }
    };

  collect_module_resource_cfg(pubs_, cfg_.aimrt_config_.channel.pub_topics_options);
  collect_module_resource_cfg(subs_, cfg_.aimrt_config_.channel.sub_topics_options);
  collect_module_resource_cfg(clis_, cfg_.aimrt_config_.rpc.clients_options);
  collect_module_resource_cfg(srvs_, cfg_.aimrt_config_.rpc.servers_options);

  // 用于反射字符串名称到枚举量，且可选的执行器是受限的
  enum class UsableExecutorType {
    Unknown,
    asio_thread
  };
  const UsableExecutorType default_executor_type =
    rfl::string_to_enum<UsableExecutorType>(sys::config::DefaultExecutorType()).value_or(UsableExecutorType::Unknown);

  auto add_executor = [&]<class TExeEnum>(TExeEnum option, const cfg::details::ExeConfig& exe_config) {
    cfg_[option] += {
      .name    = exe_config.name,
      .options = {{
        .thread_num          = exe_config.option->thread_num,
        .thread_sched_policy = exe_config.option->thread_sched_policy,
        .thread_bind_cpu     = exe_config.option->thread_bind_cpu,
      }},
    };
  };

  // 将各个模块配置的执行器信息，注入到框架配置对象中
  for (auto& exe_config : exes_ | std::views::values) {
    if (not exe_config.option.has_value())
      exe_config.option.emplace();

    switch (default_executor_type) {
      case UsableExecutorType::asio_thread:
        add_executor(cfg::Exe::asio_thread, exe_config);
        break;
      default:
        panic().wtf("CANNOT set [{}] as default executor backend !", sys::config::DefaultExecutorType());
    }
  }

  // 首先取出框架配置 yaml
  YAML::Node result;
  result["aimrt"] = YAML::Load(rfl::yaml::write(cfg_.aimrt_config_));

  // 将模块 yaml 配置合并进去
  for (const auto it : cfg_.modules_config_) {
    result[it.first.as<std::string>()] = it.second;
  }

  // 返回结果
  return result;
}

inline bool IsUndefined(const YAML::Node& node)
{
  return cfg::details::IsUndefined(node);
}

void Cfg::Processor::MergeAimRTNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeMapNode(res["configurator"], ext["configurator"]);
  MergeMapNode(res["main_thread"], ext["main_thread"]);
  MergeMapNode(res["guard_thread"], ext["guard_thread"]);
  MergeAimRTLogNode(res["log"], ext["log"]);
  MergeAimRTPluginNode(res["plugin"], ext["plugin"]);
  MergeAimRTChannelNode(res["channel"], ext["channel"]);
  MergeAimRTRpcNode(res["rpc"], ext["rpc"]);
  MergeAimRTExecutorNode(res["executor"], ext["executor"]);
  MergeAimRTModuleNode(res["module"], ext["module"]);
}

void Cfg::Processor::MergeAimRTLogNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeMapNode(res["core_lvl"], ext["core_lvl"]);
  MergeMapNode(res["default_module_lvl"], ext["default_module_lvl"]);
  MergeListNode(res["backends"], ext["backends"], "type");
}

void Cfg::Processor::MergeAimRTPluginNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeListNode(res["plugins"], ext["plugins"], "name");
}

void Cfg::Processor::MergeAimRTChannelNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeListNode(
    res["backends"], ext["backends"], "type",
    [](YAML::Node sub_res, YAML::Node sub_ext) {
      MergeMapNodeWithSubList(std::move(sub_res), std::move(sub_ext), {{"pub_topics_options", "topic_name"}, {"sub_topics_options", "topic_name"}});
    });

  MergeListNode(res["pub_topics_options"], ext["pub_topics_options"], "topic_name");
  MergeListNode(res["sub_topics_options"], ext["sub_topics_options"], "topic_name");
}

void Cfg::Processor::MergeAimRTRpcNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeListNode(
    res["backends"], ext["backends"], "type",
    [](YAML::Node sub_res, YAML::Node sub_ext) {
      MergeMapNodeWithSubList(std::move(sub_res), std::move(sub_ext), {{"servers_options", "func_name"}, {"clients_options", "func_name"}});
    });

  MergeListNode(res["clients_options"], ext["clients_options"], "func_name");
  MergeListNode(res["servers_options"], ext["servers_options"], "func_name");
}

void Cfg::Processor::MergeAimRTExecutorNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeListNode(res["executors"], ext["executors"], "name");
}

void Cfg::Processor::MergeAimRTModuleNode(YAML::Node res, const YAML::Node ext)
{
  if (IsUndefined(ext))
    return;

  MergeMapNode(res["pkgs"], ext["pkgs"]);
  MergeListNode(res["modules"], ext["modules"], "name");
}

void Cfg::Processor::MergeCustomNodes(YAML::Node& yaml, const YAML::Node& ext_yaml)
{
  for (const auto ext_it : ext_yaml) {
    const auto ext_name = ext_it.first.as<std::string>();

    // 跳过框架配置
    if (ext_name == "aimrt")
      continue;

    // 将用户外部给定的模块配置，合并入内部配置的同名模块配置中。
    // 由于在补丁阶段，有些 aimrte 子节点被赋值给 aimrt 子节点，可能会形成引用，为了避免这种情况，我们克隆 aimrte 节点
    MergeMapNode(yaml[ext_name], ext_name == "aimrte" ? Clone(ext_it.second) : ext_it.second);
  }
}

void Cfg::Processor::MergeListNode(YAML::Node res, YAML::Node ext, const std::string& id_key)
{
  MergeListNode(
    std::move(res), std::move(ext), id_key,
    [](YAML::Node sub_res, YAML::Node sub_ext) {
      MergeMapNode(std::move(sub_res), std::move(sub_ext));
    });
}

void Cfg::Processor::MergeListNode(
  YAML::Node res, YAML::Node ext, const std::string& id_key, const std::function<void(YAML::Node sub_res, YAML::Node sub_ext)>& handler)
{
  if (IsUndefined(ext))
    return;

  if (IsUndefined(res) or not ext.IsSequence()) {
    res = ext;
    return;
  }

  // should be ensured by internal aimrt config structure
  assert(res.IsSequence());

  // 将外部的配置项，合并到已有的配置中
  for (const YAML::Node& ext_i : ext) {
    const auto ext_name = ext_i[id_key].as<std::string>();

    // 从已有的配置项中寻找同名的配置项
    YAML::Node res_i;
    for (const YAML::Node& i : res) {
      if (i[id_key].as<std::string>() == ext_name) {
        res_i = i;
        break;
      }
    }

    // 若找不到已经存在的同名配置项，则直接追加它；
    // 否则，对它们两个进行合并
    if (IsUndefined(res_i))
      res.push_back(ext_i);
    else
      handler(res_i, ext_i);
  }

  // 删除在外部配置中不存在的配置项
  for (std::size_t res_idx = 0; res_idx != res.size();) {
    const YAML::Node res_i = res[res_idx];
    const auto res_name    = res_i[id_key].as<std::string>();

    bool found = false;
    for (const YAML::Node& ext_i : ext) {
      if (ext_i[id_key].as<std::string>() == res_name) {
        found = true;
        break;
      }
    }

    if (found)
      ++res_idx;
    else
      res.remove(res_idx);
  }
}

void Cfg::Processor::MergeMapNodeWithSubList(
  YAML::Node res, YAML::Node ext, const std::map<std::string, std::string>& possible_list)
{
  if (IsUndefined(ext))
    return;

  if (not ext.IsMap() or not res.IsMap()) {
    res = ext;
    return;
  }

  for (auto ext_it : ext) {
    const auto ext_name = ext_it.first.as<std::string>();

    YAML::Node res_i = res[ext_name];
    YAML::Node ext_i = ext_it.second;

    if (auto ls_it = possible_list.find(ext_name); ls_it != possible_list.end())
      MergeListNode(res_i, ext_i, ls_it->second);
    else
      MergeMapNode(res_i, ext_i);
  }
}

void Cfg::Processor::MergeMapNode(YAML::Node res, const YAML::Node ext)
{
  cfg::details::MergeMapNode(res, ext);
}

Cfg::Processor::PatchMode Cfg::Processor::AnalyzePatchMode(const YAML::Node& node) const
{
  const std::string_view tag = ExtractCustomTag(node);
  if (tag.empty())
    return PatchMode::Override;

  const std::vector<std::string> mode_words = utils::SplitTrim(tag, '+');

  PatchMode modes{PatchMode::Undefined};

  const auto check_if_multiple_define_mode = [&](const PatchMode mode) {
    if (modes & mode)
      panic().wtf(
        "multiple define AimRTe cfg mode [{}] at {}:{}:{}",
        rfl::enum_to_string(mode),
        current_processing_yaml_file_path_,
        node.Mark().line,
        node.Mark().column);
  };

  for (const std::string& word : mode_words) {
    if (word == "delete") {
      check_if_multiple_define_mode(PatchMode::Delete);
      modes |= PatchMode::Delete;
    } else if (word == "skip") {
      check_if_multiple_define_mode(PatchMode::Skip);
      modes |= PatchMode::Skip;
    } else if (constexpr std::string_view KEY("new"); word.starts_with(KEY)) {
      check_if_multiple_define_mode(PatchMode::NewFront);
      check_if_multiple_define_mode(PatchMode::NewBack);
      check_if_multiple_define_mode(PatchMode::NewNever);

      const std::string_view word_option = std::string_view(word).substr(KEY.length());
      if (word_option.empty() or word_option == ".front")
        modes |= PatchMode::NewFront;
      else if (word_option == ".back")
        modes |= PatchMode::NewBack;
      else if (word_option == ".never")
        modes |= PatchMode::NewNever;
      else
        PanicUnsupportedMode(node, word);
    } else if (constexpr std::string_view KEY("override"); word.starts_with(KEY)) {
      check_if_multiple_define_mode(PatchMode::Override);
      check_if_multiple_define_mode(PatchMode::OverrideFront);
      check_if_multiple_define_mode(PatchMode::OverrideBack);

      const std::string_view word_option = std::string_view(word).substr(KEY.length());
      if (word_option.empty())
        modes |= PatchMode::Override;
      else if (word_option == ".front")
        modes |= PatchMode::OverrideFront;
      else if (word_option == ".back")
        modes |= PatchMode::OverrideBack;
      else
        PanicUnsupportedMode(node, word);
    } else if (const std::string_view KEY("merge"); word.starts_with(KEY)) {
      check_if_multiple_define_mode(PatchMode::Merge);
      modes |= PatchMode::Merge;
    } else {
      PanicUnsupportedMode(node, word);
    }
  }

  // 若用户仅仅指定了 new.never，认为该配置项的行为是：如果已经存在同名项，则覆盖；否则跳过，也不新增。
  if (modes == PatchMode::NewNever)
    modes |= PatchMode::Override;

  if ((modes & PatchMode::Delete) + (modes & PatchMode::Override) + (modes & PatchMode::Skip) > 1) {
    panic().wtf(
      "AimRTe cfg mode 'delete', 'override', and 'skip' CANNOT be used together ! please correct it at {}:{}:{}",
      current_processing_yaml_file_path_,
      node.Mark().line,
      node.Mark().column);
  }

  return modes | PatchMode::Explicit;
}

bool Cfg::Processor::HasExplicitOverridePatchMode(const YAML::Node& node) const
{
  if (const std::string_view tag = ExtractCustomTag(node); not tag.empty()) {
    if (tag == "override") {
      return true;
    }

    PanicUnsupportedMode(node, node.Tag());
  }

  return false;
}

void Cfg::Processor::PatchAimRTNode(YAML::Node res, const YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  PatchMapNode(res["configurator"], ext["configurator"]);
  PatchMapNode(res["main_thread"], ext["main_thread"]);
  PatchMapNode(res["guard_thread"], ext["guard_thread"]);
  PatchAimRTLogNode(res["log"], ext["log"]);
  PatchAimRTPluginNode(res["plugin"], ext["plugin"]);
  PatchAimRTChannelNode(res["channel"], ext["channel"]);
  PatchAimRTRpcNode(res["rpc"], ext["rpc"]);
  PatchAimRTExecutorNode(res["executor"], ext["executor"]);
  PatchAimRTModuleNode(res["module"], ext["module"]);
}

void Cfg::Processor::PatchAimRTLogNode(YAML::Node res, YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  MergeMapNode(res["core_lvl"], ext["core_lvl"]);
  MergeMapNode(res["default_module_lvl"], ext["default_module_lvl"]);
  PatchListNode(res["backends"], ext["backends"], "type");
}

void Cfg::Processor::PatchAimRTPluginNode(YAML::Node res, YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  PatchListNode(res["plugins"], ext["plugins"], "name");
}

void Cfg::Processor::PatchAimRTChannelNode(YAML::Node res, YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  PatchListNode(
    res["backends"], ext["backends"], "type",
    [&](YAML::Node sub_res, YAML::Node sub_ext) {
      PatchMapNodeWithSubList(std::move(sub_res), std::move(sub_ext), {{"pub_topics_options", "topic_name"}, {"sub_topics_options", "topic_name"}});
    });

  PatchListNode(
    res["pub_topics_options"], ext["pub_topics_options"], "topic_name",
    [&](YAML::Node sub_res, YAML::Node sub_ext) {
      PatchListNode(sub_res["enable_backends"], sub_ext["enable_backends"], "");
      PatchListNode(sub_res["enable_filters"], sub_ext["enable_filters"], "");
    });

  PatchListNode(
    res["sub_topics_options"], ext["sub_topics_options"], "topic_name",
    [&](YAML::Node sub_res, YAML::Node sub_ext) {
      PatchListNode(sub_res["enable_backends"], sub_ext["enable_backends"], "");
      PatchListNode(sub_res["enable_filters"], sub_ext["enable_filters"], "");
    });
}

void Cfg::Processor::PatchAimRTRpcNode(YAML::Node res, const YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  PatchListNode(
    res["backends"], ext["backends"], "type",
    [&](YAML::Node sub_res, YAML::Node sub_ext) {
      PatchMapNodeWithSubList(std::move(sub_res), std::move(sub_ext), {{"servers_options", "func_name"}, {"clients_options", "func_name"}});
    });

  PatchListNode(
    res["clients_options"], ext["clients_options"], "func_name",
    [&](YAML::Node sub_res, YAML::Node sub_ext) {
      PatchListNode(sub_res["enable_backends"], sub_ext["enable_backends"], "");
      PatchListNode(sub_res["enable_filters"], sub_ext["enable_filters"], "");
    });

  PatchListNode(
    res["servers_options"], ext["servers_options"], "func_name",
    [&](YAML::Node sub_res, YAML::Node sub_ext) {
      PatchListNode(sub_res["enable_backends"], sub_ext["enable_backends"], "");
      PatchListNode(sub_res["enable_filters"], sub_ext["enable_filters"], "");
    });
}

void Cfg::Processor::PatchAimRTExecutorNode(YAML::Node res, YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  PatchListNode(res["executors"], ext["executors"], "name");
}

void Cfg::Processor::PatchAimRTModuleNode(YAML::Node res, YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  PatchListNode(res["pkgs"], ext["pkgs"], "path");
  PatchListNode(res["modules"], ext["modules"], "name");
}

void Cfg::Processor::PatchListNode(YAML::Node res, YAML::Node ext, const std::string& id_key) const
{
  PatchListNode(
    std::move(res), std::move(ext), id_key,
    [](YAML::Node sub_res, YAML::Node sub_ext) {
      MergeMapNode(std::move(sub_res), std::move(sub_ext));
    });
}

void Cfg::Processor::PatchListNode(
  YAML::Node res, YAML::Node ext, const std::string& id_key, const std::function<void(YAML::Node sub_res, YAML::Node sub_ext)>& handler) const
{
  if (IsUndefined(ext))
    return;

  if (IsUndefined(res) or not ext.IsSequence()) {
    res = ext;
    return;
  }

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  // should be ensured by internal aimrt config structure
  assert(res.IsSequence());

  auto get_key = [&](const YAML::Node& node) {
    return id_key.empty() ? node.as<std::string>() : node[id_key].as<std::string>();
  };

  // 逐项补丁外部配置
  for (const YAML::Node& ext_i : ext) {
    // 解析补丁项的补丁模式
    const PatchMode modes = AnalyzePatchMode(ext_i);

    // 找到该补丁项的名称
    const auto ext_name = get_key(ext_i);

    // 找同名项
    YAML::Node res_i;
    std::size_t res_idx = 0;

    for (const YAML::Node& i : res) {
      if (get_key(i) == ext_name) {
        res_i = i;
        break;
      }

      ++res_idx;
    }

    // 同名项不存在时，应用 new 模式
    if (IsUndefined(res_i)) {
      if (modes & PatchMode::NewFront)
        PushFront(res, ext_i);
      else if (modes & PatchMode::NewBack)
        res.push_back(ext_i);
      else if (modes & PatchMode::NewNever)
        ;
      else
        panic().wtf(
          "patch non-existed AimRTe cfg node, maybe use !!new or !!new.never for {}:{}:{}",
          current_processing_yaml_file_path_,
          ext_i.Mark().line,
          ext_i.Mark().column);

      continue;
    }

    // 如果该元素被显式贴上了 !!override，则进行整体替换
    auto do_override = [&]() {
      if (modes & PatchMode::Explicit)
        res_i = ext_i;
      else
        handler(res_i, ext_i);
    };

    // 同名项存在时，根据不同模式进行操作
    if (modes & PatchMode::Override)
      do_override();
    else if (modes & PatchMode::OverrideFront) {
      do_override();
      res.remove(res_idx);
      PushFront(res, res_i);
    } else if (modes & PatchMode::OverrideBack) {
      do_override();
      res.remove(res_idx);
      res.push_back(res_i);
    } else if (modes & PatchMode::Skip)
      ;
    else if (modes & PatchMode::Delete)
      res.remove(res_idx);
    else if (modes & PatchMode::Merge)
      CompareAndReplaceNode(res_i, ext_i);
    else
      panic().wtf(
        "same config existed, you should specify override, skip, or delete mode for {}:{}:{}",
        current_processing_yaml_file_path_,
        ext_i.Mark().line,
        ext_i.Mark().column);
  }
}

void Cfg::Processor::PatchMapNodeWithSubList(
  YAML::Node res, YAML::Node ext, const std::map<std::string, std::string>& possible_list) const
{
  if (IsUndefined(ext))
    return;

  if (not ext.IsMap() or not res.IsMap()) {
    res = ext;
    return;
  }

  for (auto ext_it : ext) {
    const auto ext_name = ext_it.first.as<std::string>();

    YAML::Node res_i = res[ext_name];
    YAML::Node ext_i = ext_it.second;

    if (auto ls_it = possible_list.find(ext_name); ls_it != possible_list.end())
      PatchListNode(res_i, ext_i, ls_it->second);
    else
      MergeMapNode(res_i, ext_i);
  }
}

void Cfg::Processor::PatchMapNode(YAML::Node res, YAML::Node ext) const
{
  if (IsUndefined(ext))
    return;

  if (HasExplicitOverridePatchMode(ext)) {
    res = ext;
    return;
  }

  MergeMapNode(res, ext);
}

void Cfg::Processor::PanicUnsupportedMode(const YAML::Node& node, const std::string& mode_str) const
{
  panic().wtf("unsupported AimRTe cfg mode [{}] at {}:{}:{}", mode_str, current_processing_yaml_file_path_, node.Mark().line, node.Mark().column);
}

std::string_view Cfg::Processor::ExtractCustomTag(const YAML::Node& node)
{
  constexpr std::string_view BASIC_TAG_PREFIX = "tag:yaml.org,2002:";

  if (not node.Tag().starts_with(BASIC_TAG_PREFIX))
    return {};

  return std::string_view(node.Tag()).substr(BASIC_TAG_PREFIX.length());
}

YAML::Node Cfg::Processor::ReadYaml(const std::string& path)
{
  std::ifstream file_stream(path);
  if (not file_stream)
    panic().wtf("failed to open cfg file: {}", path);

  std::stringstream file_data;
  file_data << file_stream.rdbuf();

  current_processing_yaml_file_path_ = path;
  return YAML::Load(aimrt::common::util::ReplaceEnvVars(file_data.str()));
}

void Cfg::Processor::PushFront(YAML::Node& list, YAML::Node element)
{
  assert(list.IsSequence());

  list.push_back(element);

  for (int i = 0, n = list.size() - 1; i < n; ++i) {
    auto front_element = list[0];
    list.remove(0);
    list.push_back(front_element);
  }
}

void Cfg::Processor::CompareAndReplaceNode(YAML::Node res, YAML::Node ext)
{
  // 处理不同类型节点的比较和替换
  if (ext.IsMap() && res.IsMap()) {
    // 对于Map类型，递归比较和替换子节点
    MergeMapNode(res, ext);
  } else if (ext.IsSequence() && res.IsSequence()) {
    // 对于Sequence类型，合并两个序列，保留唯一元素
    // 注意：这里假设序列中的元素是唯一的，如果有重复需要更复杂的合并逻辑
    YAML::Node merged = Clone(res);
    for (const auto& item : ext) {
      bool found = false;
      for (const auto& res_item : res) {
        if (res_item.as<std::string>() == item.as<std::string>()) {
          found = true;
          break;
        }
      }
      if (!found) {
        merged.push_back(item);
      }
    }
    res = merged;
  } else {
    res = ext;
  }
}
}  // namespace aimrte
