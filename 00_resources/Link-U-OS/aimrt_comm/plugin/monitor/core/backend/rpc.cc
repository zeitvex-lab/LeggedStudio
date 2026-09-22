// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "rpc.h"
#include "src/runtime/core/util/thread_tools.h"

#include "src/ctx/ctx.h"
#include "plugin/monitor/core/data_manager.h"
#include "src/common/util/string_util.h"
#include "src/common/util/url_parser.h"

namespace YAML
{
template <>
struct convert<aimrte::plugin::monitor::MonitorRpcBackend::Options> {
  static Node encode(
    const aimrte::plugin::monitor::MonitorRpcBackend::Options& rhs)
  {
    Node node;
    // node["executor"] = rhs.executor;
    return node;
  }

  static bool decode(const Node& node, aimrte::plugin::monitor::MonitorRpcBackend::Options& rhs)
  {
    // rhs.executor = node["executor"].as<std::string>();
    return true;
  }
};
}  // namespace YAML

namespace aimrte::plugin::monitor
{

MonitorRpcBackend::MonitorRpcBackend(aimrt::runtime::core::AimRTCore* aimrt_ptr)
    : core_ptr_(aimrt_ptr) {}

void MonitorRpcBackend::Initialize(YAML::Node options_node)
{
  if (options_node && !options_node.IsNull())
    options_ = options_node.as<Options>();

  options_node = options_;
}

void MonitorRpcBackend::SetRpcRegistry(const aimrt::runtime::core::rpc::RpcRegistry* rpc_registry_ptr) noexcept
{
  rpc_registry_ptr_ = rpc_registry_ptr;
}

void MonitorRpcBackend::Start()
{
  // 统计rpc服务信息,发送给上位机显示
  const auto& service_func_wrapper_map =
    rpc_registry_ptr_->GetServiceFuncWrapperMap();
  const auto& client_func_wrapper_map =
    rpc_registry_ptr_->GetClientFuncWrapperMap();

  std::set<RpcFuncInfo> rpc_service_list;
  std::set<RpcFuncInfo> rpc_client_list;

  auto aimrt_config = data_manager_->GetDumpRootConfig()["aimrt"];

  std::vector<std::pair<std::string, std::vector<std::string>>> server_backends_rules;
  if (aimrt_config["rpc"] && aimrt_config["rpc"]["servers_options"] && aimrt_config["rpc"]["servers_options"].IsSequence()) {
    for (auto pub_topic_options_node : aimrt_config["rpc"]["servers_options"]) {
      auto topic_name      = pub_topic_options_node["func_name"].as<std::string>();
      auto enable_backends = pub_topic_options_node["enable_backends"].as<std::vector<std::string>>();
      server_backends_rules.emplace_back(topic_name, enable_backends);
    }
  }

  // 统计rpc服务端信息
  for (const auto& [key, wrapper] : service_func_wrapper_map) {
    RpcFuncInfo rpc_info;

    rpc_info.func_name = key.func_name;
    rpc_info.backends  = GetBackendsByRules(key.func_name, server_backends_rules);
    // 请求体的消息类型字符串获取

    auto req_type_support_ref = wrapper->info.req_type_support_ref;
    auto rsp_type_support_ref = wrapper->info.rsp_type_support_ref;
    rpc_info.req_type         = req_type_support_ref.TypeName();

    rpc_info.rsp_type = rsp_type_support_ref.TypeName();
    rpc_service_list.insert(rpc_info);
  }

  std::vector<std::pair<std::string, std::vector<std::string>>> client_backends_rules;
  if (aimrt_config["rpc"] && aimrt_config["rpc"]["clients_options"] && aimrt_config["rpc"]["clients_options"].IsSequence()) {
    for (auto pub_topic_options_node : aimrt_config["rpc"]["clients_options"]) {
      auto topic_name      = pub_topic_options_node["func_name"].as<std::string>();
      auto enable_backends = pub_topic_options_node["enable_backends"].as<std::vector<std::string>>();
      client_backends_rules.emplace_back(topic_name, enable_backends);
    }
  }

  for (const auto& [key, warpper] : client_func_wrapper_map) {
    RpcFuncInfo rpc_info;
    rpc_info.func_name = key.func_name;
    rpc_info.backends  = GetBackendsByRules(key.func_name, client_backends_rules);
    // 请求体的消息类型字符串获取

    auto req_type_support_ref = warpper->info.req_type_support_ref;
    auto rsp_type_support_ref = warpper->info.rsp_type_support_ref;
    rpc_info.req_type         = req_type_support_ref.TypeName();

    rpc_info.rsp_type = rsp_type_support_ref.TypeName();
    rpc_client_list.insert(rpc_info);
  }

  data_manager_->SetRpcClientInfoList(rpc_client_list);
  data_manager_->SetRpcServiceInfoList(rpc_service_list);
}

void MonitorRpcBackend::Shutdown()
{
  if (std::atomic_exchange(&status_, Status::Shutdown) == Status::Shutdown)
    return;

  service_func_register_index_.clear();
}

std::vector<std::string> MonitorRpcBackend::GetBackendsByRules(
  std::string_view topic_name,
  const std::vector<std::pair<std::string, std::vector<std::string>>>& rules)
{
  for (const auto& item : rules) {
    const auto& topic_regex     = item.first;
    const auto& enable_backends = item.second;

    try {
      if (std::regex_match(topic_name.begin(), topic_name.end(), std::regex(topic_regex, std::regex::ECMAScript))) {
        return enable_backends;
      }
    } catch (const std::exception& e) {
      AIMRTE_WARN("Regex get exception, expr: {}, string: {}, exception info: {}", topic_regex, topic_name, e.what());
    }
  }

  return {};
}

bool MonitorRpcBackend::RegisterServiceFunc(
  const aimrt::runtime::core::rpc::ServiceFuncWrapper& service_func_wrapper) noexcept
{
  if (status_.load() != Status::Init) {
    AIMRTE_ERROR("Service func can only be registered when status is 'Init'.");
    return false;
  }

  std::string_view pkg_path    = service_func_wrapper.info.pkg_path;
  std::string_view module_name = service_func_wrapper.info.module_name;
  std::string_view func_name   = service_func_wrapper.info.func_name;

  service_func_register_index_[func_name][pkg_path].emplace(module_name);

  return true;
}

bool MonitorRpcBackend::RegisterClientFunc(
  const aimrt::runtime::core::rpc::ClientFuncWrapper& client_func_wrapper) noexcept
{
  if (status_.load() != Status::Init) {
    AIMRTE_ERROR("Client func can only be registered when status is 'Init'.");
    return false;
  }

  return true;
}

}  // namespace aimrte::plugin::monitor
