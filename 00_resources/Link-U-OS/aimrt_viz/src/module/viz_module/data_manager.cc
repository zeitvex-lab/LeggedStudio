// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "viz_module/data_manager.h"
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include "aimrt_module_protobuf_interface/util/protobuf_tools.h"
#include "viz_module/common.h"
#include "viz_module/global.h"
#include "yaml-cpp/yaml.h"

#ifdef GOOGLE_PROTOBUF_USING_BAZEL
  #include "src/protocols/viz_plugin/viz_plugin.aimrt_rpc.pb.h"
#else
  #include "viz_plugin.aimrt_rpc.pb.h"
#endif

namespace aimrt_viz::viz_module {

void DataManager::SetNodeRequire(aimrt::protocols::viz_plugin::NodeInfoRequest& req, const std::string& node_name) {
  auto new_data_ptr = std::make_shared<const InfoRegistry>();

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }
  // fill request
  if (auto node_info_ptr = new_data_ptr->node_info_registry_.find(node_name);
      node_info_ptr != new_data_ptr->node_info_registry_.end()) {
    const auto& info = node_info_ptr->second;

    req.set_soc(info->static_info.node_base_info.soc);
    req.set_pid(info->static_info.node_base_info.pid);
  }
}

void DataManager::UpdateData(const std::unordered_map<std::string,
                                                      std::optional<aimrt::protocols::viz_plugin::NodeInfoResponse>>& response_map) {
  auto new_data_ptr = std::make_shared<InfoRegistry>(*m_active_data_);

  // update version
  new_data_ptr->version++;

  for (const auto& [node_name, node_rsp_info] : response_map) {
    if (!node_rsp_info.has_value()) [[unlikely]] {
      // 该节点失联
      DeleteOfflineNodeInfo(new_data_ptr, node_name);
      continue;
    }
    if (new_data_ptr->node_info_registry_.find(node_name) == new_data_ptr->node_info_registry_.end()) [[unlikely]] {
      new_data_ptr->node_info_registry_.emplace(node_name, std::make_shared<NodeInfoWrapper>());
    }
    if (node_rsp_info->has_static_info()) {
      // update static data
      UpdateNodeStaticData(new_data_ptr->node_info_registry_[node_name]->static_info, new_data_ptr->node_info_registry_[node_name]->resource_ids, new_data_ptr->resource_info_registry_, node_rsp_info->static_info());
      UpdateChannelDynamicKey(new_data_ptr, node_rsp_info->static_info());
      UpdateRpcDynamicKey(new_data_ptr, node_rsp_info->static_info());
    }

    if (node_rsp_info->has_dynamic_info()) {
      UpdateNodeDynamicData(new_data_ptr->node_info_registry_[node_name]->dynamic_info,
                            new_data_ptr->node_info_registry_[node_name]->static_info.node_base_info.start_time_stamp_ns,
                            node_rsp_info->dynamic_info());
      UpdateChannelDynamicData(node_name, new_data_ptr, node_rsp_info->dynamic_info());
      UpdateRpcDynamicData(node_name, new_data_ptr, node_rsp_info->dynamic_info());
    }
  }

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_active_data_ = new_data_ptr;
  }
}

void DataManager::UpdateNodeStaticData(StaticInfo& node_info,
                                       std::vector<uint32_t>& resource_ids,
                                       std::unordered_map<uint32_t, std::shared_ptr<ResourceInfoWrapper>>& resource_info_registry,
                                       const ::aimrt::protocols::viz_plugin::StaticInfo& static_info) {
  // update node base info
  if (static_info.has_node_base_info()) {
    const auto& node_base_info_src = static_info.node_base_info();
    node_info.node_base_info = {
        .status = NodeBaseStaticInfo::Status::ONLINE,
        .node_name = node_base_info_src.node_name(),
        .soc = node_base_info_src.soc(),
        .pid = node_base_info_src.pid(),
        .aimrt_version = node_base_info_src.aimrt_version(),
        .start_time_stamp_ns = node_base_info_src.start_time_stamp_ns(),
        .executable_path = node_base_info_src.executable_path(),
        .cfg_file_path = node_base_info_src.cfg_file_path(),
    };
  }

  // update configuration info
  if (static_info.has_configuration_info()) {
    const auto& configuration_info_src = static_info.configuration_info();
    resource_ids.push_back(resource_id_++);
    node_info.configuration_info.orin_cfg_file_id = resource_ids.back();
    resource_ids.push_back(resource_id_++);
    node_info.configuration_info.parased_cfg_file_id = resource_ids.back();

    node_info.configuration_info = {
        .orin_cfg_file_id = node_info.configuration_info.orin_cfg_file_id,
        .parased_cfg_file_id = node_info.configuration_info.parased_cfg_file_id,
    };
    resource_info_registry[node_info.configuration_info.orin_cfg_file_id] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(configuration_info_src.orin_cfg_file()));
    resource_info_registry[node_info.configuration_info.parased_cfg_file_id] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(configuration_info_src.parased_cfg_file()));
  }

  // update plugin info
  if (static_info.has_plugin_info()) {
    const auto& plugin_info_src = static_info.plugin_info();
    auto& plugin_info_list_dir = node_info.plugin_info.plugin_info_list;
    plugin_info_list_dir.clear();
    plugin_info_list_dir.reserve(plugin_info_src.plugin_info_list_size());
    for (const auto& plugin_info : plugin_info_src.plugin_info_list()) {
      resource_ids.push_back(resource_id_++);
      node_info.plugin_info.plugin_info_list.push_back({.name = plugin_info.name(),
                                                        .path = plugin_info.path(),
                                                        .options_id = resource_ids.back()});
      resource_info_registry[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(plugin_info.options()));
    }
  }

  // update executor info
  if (static_info.has_executor_info()) {
    const auto& executor_info_src = static_info.executor_info();
    auto& executor_info_dir = node_info.executor_info;

    executor_info_dir.core_threads.guard_thread = {
        .tid = executor_info_src.core_threads().guard_thread().tid(),
        .name = executor_info_src.core_threads().guard_thread().name(),
        .thread_sched_policy = executor_info_src.core_threads().guard_thread().thread_sched_policy(),
        .bind_cpu = {executor_info_src.core_threads().guard_thread().bind_cpu().begin(),
                     executor_info_src.core_threads().guard_thread().bind_cpu().end()},
    };

    executor_info_dir.core_threads.main_thread = {
        .tid = executor_info_src.core_threads().main_thread().tid(),
        .name = executor_info_src.core_threads().main_thread().name(),
        .thread_sched_policy = executor_info_src.core_threads().main_thread().thread_sched_policy(),
    };

    executor_info_dir.available_executor_list.assign(
        executor_info_src.available_executor_list().begin(),
        executor_info_src.available_executor_list().end());

    executor_info_dir.executor_info_list.clear();
    executor_info_dir.executor_info_list.reserve(executor_info_src.executor_info_list_size());
    for (const auto& executor : executor_info_src.executor_info_list()) {
      resource_ids.push_back(resource_id_++);
      executor_info_dir.executor_info_list.emplace_back(
          ExecutorInfoMeta{
              executor.name(),
              executor.type(),
              executor.thread_safe(),
              executor.support_time_schedule(),
              resource_ids.back(),
          });
      resource_info_registry[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(executor.options()));
    }
  }

  // update log info
  if (static_info.has_log_info()) {
    const auto& log_info_src = static_info.log_info();
    auto& log_info_dir = node_info.log_info;

    log_info_dir.core_lvl = log_info_src.core_lvl();
    log_info_dir.default_module_lvl = log_info_src.default_module_lvl();

    log_info_dir.reliable_log_backend_list.assign(
        log_info_src.reliable_log_backend_list().begin(),
        log_info_src.reliable_log_backend_list().end());

    log_info_dir.log_backend_info_list.clear();
    log_info_dir.log_backend_info_list.reserve(log_info_src.log_backend_info_list_size());
    for (const auto& log_info : log_info_src.log_backend_info_list()) {
      resource_ids.push_back(resource_id_++);
      log_info_dir.log_backend_info_list.emplace_back(LogBackendInfoMeta{
          .type = log_info.type(),
          .options_id = resource_ids.back(),
      });
      resource_info_registry[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(log_info.options()));
    }
  }

  // update module info
  if (static_info.has_module_info()) {
    const auto& module_info_src = static_info.module_info();
    auto& module_info_dir = node_info.module_info;

    module_info_dir.module_info_list.clear();
    module_info_dir.module_info_list.reserve(module_info_src.module_info_list_size());
    for (const auto& module_info : module_info_src.module_info_list()) {
      resource_ids.push_back(resource_id_++);
      module_info_dir.module_info_list.emplace_back(ModuleInfoMeta{
          .name = module_info.name(),
          .log_lvl = module_info.log_lvl(),
          .pkg_path = module_info.pkg_path(),
          .cfg_path = module_info.cfg_path(),
          .version = module_info.version(),
          .author = module_info.author(),
          .description = module_info.description(),
          .options_id = resource_ids.back(),
      });
      resource_info_registry[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(module_info.options()));
    }
  }

  // update rpc info
  if (static_info.has_rpc_info()) {
    const auto& rpc_info_src = static_info.rpc_info();
    node_info.node_base_info.client_num = rpc_info_src.rpc_client_info_list_size();
    node_info.node_base_info.server_num = rpc_info_src.rpc_server_info_list_size();

    auto& rpc_info_dir = node_info.rpc_info;

    rpc_info_dir.available_client_filter_list.assign(
        rpc_info_src.available_client_filter_list().begin(),
        rpc_info_src.available_client_filter_list().end());

    rpc_info_dir.available_server_filter_list.assign(
        rpc_info_src.available_server_filter_list().begin(),
        rpc_info_src.available_server_filter_list().end());

    rpc_info_dir.rpc_backend_info_list.clear();
    rpc_info_dir.rpc_backend_info_list.reserve(rpc_info_src.rpc_backend_info_list_size());
    for (const auto& backend : rpc_info_src.rpc_backend_info_list()) {
      resource_ids.push_back(resource_id_++);
      rpc_info_dir.rpc_backend_info_list.emplace_back(RpcBackendInfoMeta{
          .type = backend.type(),
          .options_id = resource_ids.back(),
      });
      resource_info_registry[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(backend.options()));
    }

    rpc_info_dir.rpc_client_info_list.clear();
    rpc_info_dir.rpc_client_info_list.reserve(rpc_info_src.rpc_client_info_list_size());
    for (const auto& client : rpc_info_src.rpc_client_info_list()) {
      rpc_info_dir.rpc_client_info_list.emplace_back(RpcClientInfoMeta{
          .func_name = client.func_name(),
          .modules = {client.modules().begin(), client.modules().end()},
          .backends = {client.backends().begin(), client.backends().end()},
          .filters = {client.filters().begin(), client.filters().end()},
      });
    }

    rpc_info_dir.rpc_server_info_list.clear();
    rpc_info_dir.rpc_server_info_list.reserve(rpc_info_src.rpc_server_info_list_size());
    for (const auto& server : rpc_info_src.rpc_server_info_list()) {
      rpc_info_dir.rpc_server_info_list.emplace_back(RpcServerInfoMeta{
          .func_name = server.func_name(),
          .modules = {server.modules().begin(), server.modules().end()},
          .backends = {server.backends().begin(), server.backends().end()},
          .filters = {server.filters().begin(), server.filters().end()},
      });
    }
  }

  // update channel info
  if (static_info.has_channel_info()) {
    const auto& channel_info_src = static_info.channel_info();

    node_info.node_base_info.publisher_num = channel_info_src.channel_pub_info_list_size();
    node_info.node_base_info.subscriber_num = channel_info_src.channel_sub_info_list_size();
    auto& channel_info_dst = node_info.channel_info;

    channel_info_dst.available_pub_filter_list.assign(
        channel_info_src.available_pub_filter_list().begin(),
        channel_info_src.available_pub_filter_list().end());

    channel_info_dst.available_sub_filter_list.assign(
        channel_info_src.available_sub_filter_list().begin(),
        channel_info_src.available_sub_filter_list().end());

    channel_info_dst.channel_backend_info_list.clear();
    channel_info_dst.channel_backend_info_list.reserve(channel_info_src.channel_backend_info_list_size());
    for (const auto& backend : channel_info_src.channel_backend_info_list()) {
      resource_ids.push_back(resource_id_++);
      channel_info_dst.channel_backend_info_list.emplace_back(ChannelBackendInfoMeta{
          .type = backend.type(),
          .options_id = resource_ids.back(),
      });
      resource_info_registry[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(backend.options()));
    }

    channel_info_dst.channel_pub_info_list.clear();
    channel_info_dst.channel_pub_info_list.reserve(channel_info_src.channel_pub_info_list_size());
    for (const auto& pub : channel_info_src.channel_pub_info_list()) {
      channel_info_dst.channel_pub_info_list.emplace_back(ChannelPubInfoMeta{
          .topic = pub.topic(),
          .msg_type = pub.msg_type(),
          .modules = {pub.modules().begin(), pub.modules().end()},
          .backends = {pub.backends().begin(), pub.backends().end()},
          .filters = {pub.filters().begin(), pub.filters().end()}});
    }

    channel_info_dst.channel_sub_info_list.clear();
    channel_info_dst.channel_sub_info_list.reserve(channel_info_src.channel_sub_info_list_size());
    for (const auto& sub : channel_info_src.channel_sub_info_list()) {
      channel_info_dst.channel_sub_info_list.emplace_back(ChannelSubInfoMeta{
          .topic = sub.topic(),
          .msg_type = sub.msg_type(),
          .modules = {sub.modules().begin(), sub.modules().end()},
          .backends = {sub.backends().begin(), sub.backends().end()},
          .filters = {sub.filters().begin(), sub.filters().end()}});
    }
  }
}

void DataManager::UpdateNodeDynamicData(DynamicInfo& node_info, uint64_t start_time_stamp_ns,
                                        const ::aimrt::protocols::viz_plugin::DynamicInfo& dynamic_info) {
  const auto& cur_time = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
  uint64_t online_time_s = (cur_time - start_time_stamp_ns) / 1e9;
  if (dynamic_info.has_node_base_info()) {
    const auto& node_base_info_src = dynamic_info.node_base_info();
    node_info.node_base_info = {
        .online_time_s = online_time_s,
        .memory_usage_kb = node_base_info_src.memory_usage_kb(),
        .memory_usage_percent = node_base_info_src.memory_usage_percent(),
        .thread_count = node_base_info_src.thread_count(),
        .cpu_usage_percent = node_base_info_src.cpu_usage_percent(),
        .scheduler_priority = node_base_info_src.scheduler_priority(),
    };
  }
}

void DataManager::UpdateChannelDynamicKey(std::shared_ptr<InfoRegistry> data_ptr,
                                          const ::aimrt::protocols::viz_plugin::StaticInfo& static_info) {
  std::string node_name = static_info.node_base_info().node_name();
  auto soc = static_info.node_base_info().soc();
  auto pid = static_info.node_base_info().pid();

  auto& resource_ids = data_ptr->node_info_registry_[node_name]->resource_ids;

  for (const auto& info : static_info.channel_info().channel_sub_info_list()) {
    ChannelMetaKey key{
        .topic_name = info.topic(),
        .msg_type = info.msg_type(),
    };
    if (data_ptr->channel_info_registry_.find(key) == data_ptr->channel_info_registry_.end()) {
      data_ptr->channel_info_registry_[key] = std::make_shared<ChannelInfoWrapper>();
    }
    resource_ids.push_back(resource_id_++);
    data_ptr->channel_info_registry_[key]->schema_id = resource_ids.back();
    data_ptr->resource_info_registry_[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(info.schema()));

    for (auto& module : info.modules()) {
      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = module,
          .soc = soc,
          .pid = pid,
      };
      auto itr = data_ptr->channel_info_registry_[key]->sub_dynamic_info.find(node_mode_key);
      if (itr == data_ptr->channel_info_registry_[key]->sub_dynamic_info.end()) {
        itr = data_ptr->channel_info_registry_[key]->sub_dynamic_info.insert(std::make_pair(node_mode_key, ChannelDynamicMeta())).first;
      }

      for (auto& backend : info.backends()) {
        data_ptr->channel_info_registry_[key]->used_backends[backend] += 1;
        itr->second.backends.insert(backend);
      }

      for (auto& filter : info.filters()) {
        data_ptr->channel_info_registry_[key]->used_filters[filter] += 1;
        itr->second.filters.insert(filter);
      }
    }
  }

  for (const auto& info : static_info.channel_info().channel_pub_info_list()) {
    ChannelMetaKey key{
        .topic_name = info.topic(),
        .msg_type = info.msg_type(),
    };
    if (data_ptr->channel_info_registry_.find(key) == data_ptr->channel_info_registry_.end()) {
      data_ptr->channel_info_registry_[key] = std::make_shared<ChannelInfoWrapper>();
    }
    resource_ids.push_back(resource_id_++);
    data_ptr->channel_info_registry_[key]->schema_id = resource_ids.back();
    data_ptr->resource_info_registry_[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(info.schema()));

    for (auto& module : info.modules()) {
      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = module,
          .soc = soc,
          .pid = pid,
      };
      auto itr = data_ptr->channel_info_registry_[key]->pub_dynamic_info.find(node_mode_key);
      if (itr == data_ptr->channel_info_registry_[key]->pub_dynamic_info.end()) {
        itr = data_ptr->channel_info_registry_[key]->pub_dynamic_info.emplace(node_mode_key, ChannelDynamicMeta()).first;
      }
      for (auto& backend : info.backends()) {
        data_ptr->channel_info_registry_[key]->used_backends[backend] += 1;
        itr->second.backends.insert(backend);
      }

      for (auto& filter : info.filters()) {
        data_ptr->channel_info_registry_[key]->used_filters[filter] += 1;
        itr->second.filters.insert(filter);
      }
    }
  }
}

void DataManager::UpdateChannelDynamicData(const std::string& node_name_svice,
                                           std::shared_ptr<InfoRegistry> data_ptr,
                                           const ::aimrt::protocols::viz_plugin::DynamicInfo& dynamic_info) {
  auto channel_info_ptr = data_ptr->channel_info_registry_;
  auto node_info_ptr = data_ptr->node_info_registry_[node_name_svice];
  auto node_name = node_info_ptr->static_info.node_base_info.node_name;
  auto soc = node_info_ptr->static_info.node_base_info.soc;
  auto pid = node_info_ptr->static_info.node_base_info.pid;

  if (dynamic_info.has_channel_info()) {
    for (const auto& sub_channel : dynamic_info.channel_info().sub_dynamic_info_list()) {
      ChannelMetaKey sub_key = {
          .topic_name = sub_channel.topic(),
          .msg_type = sub_channel.msg_type(),
      };
      auto channel_wrapper_itr = channel_info_ptr.find(sub_key);
      if (channel_wrapper_itr == channel_info_ptr.end()) {
        channel_wrapper_itr = channel_info_ptr.insert(std::make_pair(sub_key, std::make_shared<ChannelInfoWrapper>())).first;
      }

      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = sub_channel.module(),
          .soc = soc,
          .pid = pid,
      };
      auto sub_itr = channel_wrapper_itr->second->sub_dynamic_info.find(node_mode_key);
      if (sub_itr == channel_wrapper_itr->second->sub_dynamic_info.end()) {
        sub_itr = channel_wrapper_itr->second->sub_dynamic_info.insert(std::make_pair(node_mode_key, ChannelDynamicMeta())).first;
      }
      sub_itr->second.frequency = sub_channel.frequency();
      sub_itr->second.history_seq_num = sub_channel.history_seq_num();
    }
    for (const auto& pub_channel : dynamic_info.channel_info().pub_dynamic_info_list()) {
      ChannelMetaKey pub_key = {
          .topic_name = pub_channel.topic(),
          .msg_type = pub_channel.msg_type(),
      };
      auto channel_wrapper_itr = channel_info_ptr.find(pub_key);
      if (channel_wrapper_itr == channel_info_ptr.end()) {
        channel_wrapper_itr = channel_info_ptr.insert(std::make_pair(pub_key, std::make_shared<ChannelInfoWrapper>())).first;
      }

      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = pub_channel.module(),
          .soc = soc,
          .pid = pid,
      };
      auto pub_itr = channel_wrapper_itr->second->pub_dynamic_info.find(node_mode_key);
      if (pub_itr == channel_wrapper_itr->second->pub_dynamic_info.end()) {
        pub_itr = channel_wrapper_itr->second->pub_dynamic_info.insert(std::make_pair(node_mode_key, ChannelDynamicMeta())).first;
      }
      pub_itr->second.frequency = pub_channel.frequency();
      pub_itr->second.history_seq_num = pub_channel.history_seq_num();
    }
  }
}

void DataManager::UpdateRpcDynamicKey(std::shared_ptr<InfoRegistry> data_ptr,
                                      const ::aimrt::protocols::viz_plugin::StaticInfo& static_info) {
  std::string node_name = static_info.node_base_info().node_name();
  auto soc = static_info.node_base_info().soc();
  auto pid = static_info.node_base_info().pid();

  auto& resource_ids = data_ptr->node_info_registry_[node_name]->resource_ids;

  for (const auto& info : static_info.rpc_info().rpc_server_info_list()) {
    RpcMetaKey key{
        .func_name = info.func_name(),
    };

    for (auto& module : info.modules()) {
      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = module,
          .soc = soc,
          .pid = pid,
      };
      auto rpc_info_wrapper_itr = data_ptr->rpc_info_registry_.find(key);
      if (rpc_info_wrapper_itr == data_ptr->rpc_info_registry_.end()) {
        rpc_info_wrapper_itr = data_ptr->rpc_info_registry_.insert(std::make_pair(key, std::make_shared<RpcInfoWrapper>())).first;
      }
      rpc_info_wrapper_itr->second->req_type = info.req_type();
      rpc_info_wrapper_itr->second->rsp_type = info.rsp_type();

      resource_ids.push_back(resource_id_++);
      rpc_info_wrapper_itr->second->req_schema_id = resource_ids.back();
      data_ptr->resource_info_registry_[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(info.req_schema()));

      resource_ids.push_back(resource_id_++);
      rpc_info_wrapper_itr->second->rsp_schema_id = resource_ids.back();
      data_ptr->resource_info_registry_[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(info.rsp_schema()));

      auto itr = data_ptr->rpc_info_registry_[key]->server_dynamic_info_map.find(node_mode_key);
      if (itr == data_ptr->rpc_info_registry_[key]->server_dynamic_info_map.end()) {
        itr = data_ptr->rpc_info_registry_[key]->server_dynamic_info_map.insert(std::make_pair(node_mode_key, RpcDynamicInfoMeta())).first;
      }

      for (auto& backend : info.backends()) {
        data_ptr->rpc_info_registry_[key]->used_backends[backend] += 1;
        itr->second.backends.insert(backend);
      }

      for (auto& filter : info.filters()) {
        data_ptr->rpc_info_registry_[key]->used_filters[filter] += 1;
        itr->second.filters.insert(filter);
      }
    }
  }

  for (const auto& info : static_info.rpc_info().rpc_client_info_list()) {
    RpcMetaKey key{
        .func_name = info.func_name(),
    };

    for (auto& module : info.modules()) {
      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = module,
          .soc = soc,
          .pid = pid,
      };
      auto rpc_info_wrapper_itr = data_ptr->rpc_info_registry_.find(key);
      if (rpc_info_wrapper_itr == data_ptr->rpc_info_registry_.end()) {
        rpc_info_wrapper_itr = data_ptr->rpc_info_registry_.insert(std::make_pair(key, std::make_shared<RpcInfoWrapper>())).first;
      }
      rpc_info_wrapper_itr->second->req_type = info.req_type();
      rpc_info_wrapper_itr->second->rsp_type = info.rsp_type();

      resource_ids.push_back(resource_id_++);
      rpc_info_wrapper_itr->second->req_schema_id = resource_ids.back();
      data_ptr->resource_info_registry_[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(info.req_schema()));

      resource_ids.push_back(resource_id_++);
      rpc_info_wrapper_itr->second->rsp_schema_id = resource_ids.back();
      data_ptr->resource_info_registry_[resource_ids.back()] = std::make_shared<ResourceInfoWrapper>(ResourceType::STRING, std::string(info.rsp_schema()));

      auto itr = data_ptr->rpc_info_registry_[key]->client_dynamic_info_map.find(node_mode_key);
      if (itr == data_ptr->rpc_info_registry_[key]->client_dynamic_info_map.end()) {
        itr = data_ptr->rpc_info_registry_[key]->client_dynamic_info_map.insert(std::make_pair(node_mode_key, RpcDynamicInfoMeta())).first;
      }
      for (auto& backend : info.backends()) {
        data_ptr->rpc_info_registry_[key]->used_backends[backend] += 1;
        itr->second.backends.insert(backend);
      }

      for (auto& filter : info.filters()) {
        data_ptr->rpc_info_registry_[key]->used_filters[filter] += 1;
        itr->second.filters.insert(filter);
      }
    }
  }
}

void DataManager::UpdateRpcDynamicData(const std::string& node_name_svice,
                                       std::shared_ptr<InfoRegistry> data_ptr,
                                       const ::aimrt::protocols::viz_plugin::DynamicInfo& dynamic_info) {
  auto rpc_info_ptr = data_ptr->rpc_info_registry_;
  auto node_info_ptr = data_ptr->node_info_registry_[node_name_svice];
  auto node_name = node_info_ptr->static_info.node_base_info.node_name;
  auto soc = node_info_ptr->static_info.node_base_info.soc;
  auto pid = node_info_ptr->static_info.node_base_info.pid;

  if (dynamic_info.has_rpc_info()) {
    for (const auto& server_rpc : dynamic_info.rpc_info().server_dynamic_info_list()) {
      RpcMetaKey server_key = {
          .func_name = server_rpc.func_name(),
      };
      auto rpc_wrapper_itr = rpc_info_ptr.find(server_key);
      if (rpc_wrapper_itr == rpc_info_ptr.end()) {
        rpc_wrapper_itr = rpc_info_ptr.insert(std::make_pair(server_key, std::make_shared<RpcInfoWrapper>())).first;
      }

      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = server_rpc.module(),
          .soc = soc,
          .pid = pid,
      };
      auto server_itr = rpc_wrapper_itr->second->server_dynamic_info_map.find(node_mode_key);
      if (server_itr == rpc_wrapper_itr->second->server_dynamic_info_map.end()) {
        server_itr = rpc_wrapper_itr->second->server_dynamic_info_map.insert(std::make_pair(node_mode_key, RpcDynamicInfoMeta())).first;
      }
      server_itr->second.frequency = server_rpc.frequency();
      server_itr->second.latency_us = server_rpc.latency_us();
      server_itr->second.history_seq_num = server_rpc.history_seq_num();
      server_itr->second.history_error_count = server_rpc.history_error_count();
      server_itr->second.seq_num = server_rpc.seq_num();
      server_itr->second.error_count = server_rpc.error_count();
      server_itr->second.error_rate = server_rpc.error_rate();
    }
    for (const auto& client_rpc : dynamic_info.rpc_info().client_dynamic_info_list()) {
      RpcMetaKey client_key = {
          .func_name = client_rpc.func_name(),
      };
      auto rpc_wrapper_itr = rpc_info_ptr.find(client_key);
      if (rpc_wrapper_itr == rpc_info_ptr.end()) {
        rpc_wrapper_itr = rpc_info_ptr.insert(std::make_pair(client_key, std::make_shared<RpcInfoWrapper>())).first;
      }

      NodeModeKey node_mode_key{
          .node_name = node_name,
          .mode = client_rpc.module(),
          .soc = soc,
          .pid = pid,
      };
      auto client_itr = rpc_wrapper_itr->second->client_dynamic_info_map.find(node_mode_key);
      if (client_itr == rpc_wrapper_itr->second->client_dynamic_info_map.end()) {
        client_itr = rpc_wrapper_itr->second->client_dynamic_info_map.insert(std::make_pair(node_mode_key, RpcDynamicInfoMeta())).first;
      }
      client_itr->second.frequency = client_rpc.frequency();
      client_itr->second.latency_us = client_rpc.latency_us();
      client_itr->second.history_seq_num = client_rpc.history_seq_num();
      client_itr->second.history_error_count = client_rpc.history_error_count();
      client_itr->second.seq_num = client_rpc.seq_num();
      client_itr->second.error_count = client_rpc.error_count();
      client_itr->second.error_rate = client_rpc.error_rate();
    }
  }
}

void DataManager::SetSystemInfo(SystemInfo& system_info) {
  system_info_ = system_info;
  system_info_.aimrt_viz_version = AIMRT_VIZ_VERSION;
}

void DataManager::SetWebSystemInfoResponse(::aimrt::protocols::viz_web::SystemInfoResponse& rsp) {
  auto* static_info = rsp.mutable_static_info();
  static_info->set_name(system_info_.system_name);
  static_info->set_aimrt_viz_version(system_info_.aimrt_viz_version);

  auto& attributes = *static_info->mutable_attributes();
  for (const auto& attr : system_info_.attributes) {
    attributes[attr.at("key")] = attr.at("value");
  }
}

void DataManager::SetWebNodeBaseInfoResponse(::aimrt::protocols::viz_web::NodeBaseInfoResponse& rsp) {
  std::shared_ptr<const InfoRegistry> new_data_ptr;

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  auto* static_info_list = rsp.mutable_node_base_static_info_list();
  auto* dynamic_info_list = rsp.mutable_node_base_dynamic_info_list();

  for (const auto& [node_name, node_info] : new_data_ptr->node_info_registry_) {
    auto* static_info = static_info_list->add_node_base_static_info_list();

    static_info->set_node_name(node_info->static_info.node_base_info.node_name);
    static_info->set_soc(node_info->static_info.node_base_info.soc);
    static_info->set_pid(node_info->static_info.node_base_info.pid);
    static_info->set_aimrt_version(node_info->static_info.node_base_info.aimrt_version);
    static_info->set_start_time_stamp_ns(node_info->static_info.node_base_info.start_time_stamp_ns);
    static_info->set_executable_path(node_info->static_info.node_base_info.executable_path);
    static_info->set_cfg_file_path(node_info->static_info.node_base_info.cfg_file_path);
    static_info->set_pub_num(node_info->static_info.node_base_info.publisher_num);
    static_info->set_sub_num(node_info->static_info.node_base_info.subscriber_num);
    static_info->set_client_num(node_info->static_info.node_base_info.client_num);
    static_info->set_server_num(node_info->static_info.node_base_info.server_num);

    if (node_info->static_info.node_base_info.status == NodeBaseStaticInfo::Status::OFFLINE) {
      static_info->set_status(::aimrt::protocols::viz_web::NodeBaseStaticInfo_Status_OFFLINE);
      continue;
    } else {
      static_info->set_status(::aimrt::protocols::viz_web::NodeBaseStaticInfo_Status_ONLINE);
    }

    auto* dynamic_info = dynamic_info_list->add_node_base_dynamic_info_list();
    dynamic_info->set_node_name(node_info->static_info.node_base_info.node_name);
    dynamic_info->set_online_time_s(node_info->dynamic_info.node_base_info.online_time_s);
    dynamic_info->set_memory_usage_kb(node_info->dynamic_info.node_base_info.memory_usage_kb);
    dynamic_info->set_memory_usage_percent(node_info->dynamic_info.node_base_info.memory_usage_percent);
    dynamic_info->set_thread_count(node_info->dynamic_info.node_base_info.thread_count);
    dynamic_info->set_cpu_usage_percent(node_info->dynamic_info.node_base_info.cpu_usage_percent);
    dynamic_info->set_scheduler_priority(node_info->dynamic_info.node_base_info.scheduler_priority);
  }
}
void DataManager::SetWebNodeDetailInfoResponse(const std::string& node_name, ::aimrt::protocols::viz_web::NodeDetailInfoResponse& rsp) {
  std::shared_ptr<const InfoRegistry> new_data_ptr;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  const auto& channel_info_registry_ = new_data_ptr->channel_info_registry_;
  const auto& rpc_info_registry_ = new_data_ptr->rpc_info_registry_;
  auto node_info_itr = new_data_ptr->node_info_registry_.find(node_name);
  if (node_info_itr == new_data_ptr->node_info_registry_.end()) {
    return;
  }

  const auto& node_info = node_info_itr->second;
  // 获取静态和动态信息引用
  const auto& src_static = node_info->static_info;
  const auto& src_dynamic = node_info->dynamic_info;
  auto* dst_static = rsp.mutable_node_detail_static_info();
  auto* dst_dynamic = rsp.mutable_node_detail_dynamic_info();

  // 1. 节点基本信息
  {
    auto* node_info = dst_static->mutable_node_base_info();
    const auto& base = src_static.node_base_info;
    node_info->set_node_name(base.node_name);
    node_info->set_soc(base.soc);
    node_info->set_pid(base.pid);
    node_info->set_aimrt_version(base.aimrt_version);
    node_info->set_start_time_stamp_ns(base.start_time_stamp_ns);
    node_info->set_executable_path(base.executable_path);
    node_info->set_cfg_file_path(base.cfg_file_path);
    node_info->set_pub_num(base.publisher_num);
    node_info->set_sub_num(base.subscriber_num);
    node_info->set_client_num(base.client_num);
    node_info->set_server_num(base.server_num);

    auto* node_dynamic = dst_dynamic->mutable_node_base_info();
    const auto& dyn_base = src_dynamic.node_base_info;
    node_dynamic->set_online_time_s(dyn_base.online_time_s);
    node_dynamic->set_memory_usage_kb(dyn_base.memory_usage_kb);
    node_dynamic->set_memory_usage_percent(dyn_base.memory_usage_percent);
    node_dynamic->set_thread_count(dyn_base.thread_count);
    node_dynamic->set_cpu_usage_percent(dyn_base.cpu_usage_percent);
    node_dynamic->set_scheduler_priority(dyn_base.scheduler_priority);
  }

  // 2. 配置信息
  {
    auto* cfg_info = dst_static->mutable_configuration_info();
    const auto& cfg = src_static.configuration_info;
    cfg_info->set_orin_cfg_file_id(cfg.orin_cfg_file_id);
    cfg_info->set_parased_cfg_file_id(cfg.parased_cfg_file_id);
  }

  // 3. 插件信息
  {
    auto* plugin_list = dst_static->mutable_plugin_info();
    for (const auto& plugin : src_static.plugin_info.plugin_info_list) {
      auto* plugin_info = plugin_list->add_plugin_info_list();
      plugin_info->set_name(plugin.name);
      plugin_info->set_path(plugin.path);
      plugin_info->set_options_id(plugin.options_id);
    }
  }

  // 4. 执行器信息
  {
    auto* exec_info = dst_static->mutable_executor_info();
    const auto& src_exec = src_static.executor_info;

    // 核心线程
    auto* core = exec_info->mutable_core_threads();
    {
      auto* main = core->mutable_main_thread();
      main->set_tid(src_exec.core_threads.main_thread.tid);
      main->set_name(src_exec.core_threads.main_thread.name);
      main->set_thread_sched_policy(src_exec.core_threads.main_thread.thread_sched_policy);
      for (const auto& cpu : src_exec.core_threads.main_thread.bind_cpu) {
        main->add_bind_cpu(cpu);
      }

      auto* guard = core->mutable_guard_thread();
      guard->set_tid(src_exec.core_threads.guard_thread.tid);
      guard->set_name(src_exec.core_threads.guard_thread.name);
      guard->set_thread_sched_policy(src_exec.core_threads.guard_thread.thread_sched_policy);
      for (const auto& cpu : src_exec.core_threads.guard_thread.bind_cpu) {
        guard->add_bind_cpu(cpu);
      }
    }

    // 可用执行器
    for (const auto& type : src_exec.available_executor_list) {
      exec_info->add_available_executor_list(type);
    }

    // 执行器列表
    for (const auto& exec : src_exec.executor_info_list) {
      auto* pb_exec = exec_info->add_executor_info_list();
      pb_exec->set_name(exec.name);
      pb_exec->set_type(exec.type);
      pb_exec->set_thread_safe(exec.thread_safe);
      pb_exec->set_support_time_schedule(exec.support_time_schedule);
      pb_exec->set_options_id(exec.options_id);
    }
  }

  // 5. 日志信息
  {
    auto* log_info = dst_static->mutable_log_info();
    const auto& src_log = src_static.log_info;
    log_info->set_core_lvl(src_log.core_lvl);
    log_info->set_default_module_lvl(src_log.default_module_lvl);

    // 使用范围构造
    for (const auto& backend : src_log.reliable_log_backend_list) {
      log_info->add_reliable_log_backend_list(backend);
    }

    for (const auto& backend : src_log.log_backend_info_list) {
      auto* pb_backend = log_info->add_log_backend_info_list();
      pb_backend->set_type(backend.type);
      pb_backend->set_options_id(backend.options_id);
    }
  }

  // 6. 模块信息
  {
    auto* module_info = dst_static->mutable_module_info();
    for (const auto& module : src_static.module_info.module_info_list) {
      auto* pb_module = module_info->add_module_info_list();
      pb_module->set_name(module.name);
      pb_module->set_log_lvl(module.log_lvl);
      pb_module->set_pkg_path(module.pkg_path);
      pb_module->set_cfg_path(module.cfg_path);
    }
  }

  // 7. RPC信息
  {
    auto* rpc_static = dst_static->mutable_rpc_info();
    auto* rpc_dynamic = dst_dynamic->mutable_rpc_info();
    const auto& src_rpc = src_static.rpc_info;

    // 静态信息
    for (const auto& filter : src_rpc.available_client_filter_list) {
      rpc_static->add_available_client_filter_list(filter);
    }

    for (const auto& filter : src_rpc.available_server_filter_list) {
      rpc_static->add_available_server_filter_list(filter);
    }

    for (const auto& backend : src_rpc.rpc_backend_info_list) {
      auto* pb_backend = rpc_static->add_rpc_backend_info_list();
      pb_backend->set_type(backend.type);
      pb_backend->set_options_id(backend.options_id);
    }

    for (const auto& client : src_rpc.rpc_client_info_list) {
      auto* pb_client = rpc_static->add_rpc_client_info_list();
      pb_client->set_func_name(client.func_name);

      // 列表字段
      for (const auto& module : client.modules) pb_client->add_modules(module);
      for (const auto& backend : client.backends) pb_client->add_backends(backend);
      for (const auto& filter : client.filters) pb_client->add_filters(filter);

      RpcMetaKey client_key = {
          .func_name = client.func_name,
      };
      auto rpc_wrapper_itr = rpc_info_registry_.find(client_key);
      if (rpc_wrapper_itr == rpc_info_registry_.end()) {
        continue;
      }

      for (const auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_wrapper_itr->second->server_dynamic_info_map) {
        auto* connect_to = rpc_dynamic->add_server_dynamic_info_list();
        connect_to->set_func_name(client.func_name);
        connect_to->set_node_name(node_mode_key.node_name);
        connect_to->set_module_name(node_mode_key.mode);
        connect_to->set_soc(node_mode_key.soc);
        connect_to->set_pid(node_mode_key.pid);
      }
    }

    for (const auto& server : src_rpc.rpc_server_info_list) {
      auto* pb_server = rpc_static->add_rpc_server_info_list();
      pb_server->set_func_name(server.func_name);
      for (const auto& module : server.modules) pb_server->add_modules(module);
      for (const auto& backend : server.backends) pb_server->add_backends(backend);
      for (const auto& filter : server.filters) pb_server->add_filters(filter);

      RpcMetaKey server_key = {
          .func_name = server.func_name,
      };
      auto rpc_wrapper_itr = rpc_info_registry_.find(server_key);
      if (rpc_wrapper_itr == rpc_info_registry_.end()) {
        continue;
      }

      for (const auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_wrapper_itr->second->client_dynamic_info_map) {
        auto* connect_to = rpc_dynamic->add_client_dynamic_info_list();
        connect_to->set_func_name(server.func_name);
        connect_to->set_node_name(node_mode_key.node_name);
        connect_to->set_module_name(node_mode_key.mode);
        connect_to->set_soc(node_mode_key.soc);
        connect_to->set_pid(node_mode_key.pid);
      }
    }

    // 8. 通道信息
    {
      auto* channel_static = dst_static->mutable_channel_info();
      auto* channel_dynamic = dst_dynamic->mutable_channel_info();
      const auto& src_channel = src_static.channel_info;

      // 静态信息
      for (const auto& filter : src_channel.available_pub_filter_list) {
        channel_static->add_available_pub_filter_list(filter);
      }

      for (const auto& filter : src_channel.available_sub_filter_list) {
        channel_static->add_available_sub_filter_list(filter);
      }

      for (const auto& backend : src_channel.channel_backend_info_list) {
        auto* pb_backend = channel_static->add_channel_backend_info_list();
        pb_backend->set_type(backend.type);
        pb_backend->set_options_id(backend.options_id);
      }

      for (const auto& pub : src_channel.channel_pub_info_list) {
        auto* pb_pub = channel_static->add_channel_pub_info_list();
        pb_pub->set_topic(pub.topic);
        pb_pub->set_msg_type(pub.msg_type);

        for (const auto& module : pub.modules) pb_pub->add_modules(module);
        for (const auto& backend : pub.backends) pb_pub->add_backends(backend);
        for (const auto& filter : pub.filters) pb_pub->add_filters(filter);

        ChannelMetaKey pub_key = {
            .topic_name = pub.topic,
            .msg_type = pub.msg_type,
        };
        auto channel_wrapper_itr = channel_info_registry_.find(pub_key);
        if (channel_wrapper_itr == channel_info_registry_.end()) {
          continue;
        }

        for (const auto& [node_mode_key, channel_dynamic_info_meta] : channel_wrapper_itr->second->sub_dynamic_info) {
          auto* connect_to = channel_dynamic->add_sub_dynamic_info_list();
          connect_to->set_topic(pub.topic);
          connect_to->set_msg_type(pub.msg_type);
          connect_to->set_node_name(node_mode_key.node_name);
          connect_to->set_module_name(node_mode_key.mode);
          connect_to->set_soc(node_mode_key.soc);
          connect_to->set_pid(node_mode_key.pid);
        }
      }

      for (const auto& sub : src_channel.channel_sub_info_list) {
        auto* pb_sub = channel_static->add_channel_sub_info_list();
        pb_sub->set_topic(sub.topic);
        pb_sub->set_msg_type(sub.msg_type);

        for (const auto& module : sub.modules) pb_sub->add_modules(module);
        for (const auto& backend : sub.backends) pb_sub->add_backends(backend);
        for (const auto& filter : sub.filters) pb_sub->add_filters(filter);

        ChannelMetaKey sub_key = {
            .topic_name = sub.topic,
            .msg_type = sub.msg_type,
        };
        auto channel_wrapper_itr = channel_info_registry_.find(sub_key);
        if (channel_wrapper_itr == channel_info_registry_.end()) {
          continue;
        }

        for (const auto& [node_mode_key, channel_dynamic_info_meta] : channel_wrapper_itr->second->pub_dynamic_info) {
          auto* connect_to = channel_dynamic->add_pub_dynamic_info_list();
          connect_to->set_topic(sub.topic);
          connect_to->set_msg_type(sub.msg_type);
          connect_to->set_node_name(node_mode_key.node_name);
          connect_to->set_module_name(node_mode_key.mode);
          connect_to->set_soc(node_mode_key.soc);
          connect_to->set_pid(node_mode_key.pid);
        }
      }
    }
  }
}

void DataManager::DeleteOfflineNodeInfo(std::shared_ptr<InfoRegistry> data_ptr, const std::string& node_name) {
  auto& node_info_registry = data_ptr->node_info_registry_;
  auto itr = node_info_registry.find(node_name);
  if (itr == node_info_registry.end()) {
    node_info_registry.emplace(node_name, std::make_shared<NodeInfoWrapper>());
    node_info_registry[node_name]->static_info.node_base_info.status = NodeBaseStaticInfo::Status::OFFLINE;
    node_info_registry[node_name]->static_info.node_base_info.node_name = node_name;
    return;
  }
  for (auto& [rpc_key, rpc_info_wrapper] : data_ptr->rpc_info_registry_) {
    for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->client_dynamic_info_map) {
      if (node_mode_key.node_name == node_name) {
        continue;
      }
      for (auto& backend : rpc_dynamic_info_meta.backends) {
        rpc_info_wrapper->used_backends[backend]--;
      }
      for (auto& filter : rpc_dynamic_info_meta.filters) {
        rpc_info_wrapper->used_filters[filter]--;
      }
    }
    std::erase_if(rpc_info_wrapper->client_dynamic_info_map, [&](const auto& pair_item) {
      const auto& node_mode_key = pair_item.first;
      if (node_mode_key.node_name == node_name) {
        return true;
      }
      return false;
    });
    for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->server_dynamic_info_map) {
      if (node_mode_key.node_name == node_name) {
        continue;
      }
      for (auto& backend : rpc_dynamic_info_meta.backends) {
        rpc_info_wrapper->used_backends[backend]--;
      }
      for (auto& filter : rpc_dynamic_info_meta.filters) {
        rpc_info_wrapper->used_filters[filter]--;
      }
    }
    std::erase_if(rpc_info_wrapper->server_dynamic_info_map, [&](const auto& pair_item) {
      const auto& node_mode_key = pair_item.first;
      if (node_mode_key.node_name == node_name) {
        return true;
      }
      return false;
    });
  }
  std::erase_if(data_ptr->rpc_info_registry_, [&](const auto& pair_item) {
    const auto& [rpc_key, rpc_info_wrapper] = pair_item;
    if (rpc_info_wrapper->client_dynamic_info_map.size() == 0 && rpc_info_wrapper->server_dynamic_info_map.size() == 0) {
      return true;
    }
    return false;
  });

  for (auto& [channel_key, channel_info_wrapper] : data_ptr->channel_info_registry_) {
    for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->pub_dynamic_info) {
      if (node_mode_key.node_name == node_name) {
        continue;
      }
      for (auto& backend : channel_dynamic_info_meta.backends) {
        channel_info_wrapper->used_backends[backend]--;
      }
      for (auto& filter : channel_dynamic_info_meta.filters) {
        channel_info_wrapper->used_filters[filter]--;
      }
    }
    std::erase_if(channel_info_wrapper->pub_dynamic_info, [&](const auto& pair_item) {
      const auto& node_mode_key = pair_item.first;
      if (node_mode_key.node_name == node_name) {
        return true;
      }
      return false;
    });
    for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->sub_dynamic_info) {
      if (node_mode_key.node_name == node_name) {
        continue;
      }
      for (auto& backend : channel_dynamic_info_meta.backends) {
        channel_info_wrapper->used_backends[backend]--;
      }
      for (auto& filter : channel_dynamic_info_meta.filters) {
        channel_info_wrapper->used_filters[filter]--;
      }
    }
    std::erase_if(channel_info_wrapper->sub_dynamic_info, [&](const auto& pair_item) {
      const auto& node_mode_key = pair_item.first;
      if (node_mode_key.node_name == node_name) {
        return true;
      }
      return false;
    });
  }
  std::erase_if(data_ptr->channel_info_registry_, [&](const auto& pair_item) {
    const auto& [channel_key, channel_info_wrapper] = pair_item;
    if (channel_info_wrapper->pub_dynamic_info.size() == 0 && channel_info_wrapper->sub_dynamic_info.size() == 0) {
      return true;
    }
    return false;
  });

  for (auto& resource_id : itr->second->resource_ids) {
    auto resource_info_itr = data_ptr->resource_info_registry_.find(resource_id);
    if (resource_info_itr == data_ptr->resource_info_registry_.end()) {
      continue;
    }
    data_ptr->resource_info_registry_.erase(resource_info_itr);
  }
  itr->second->static_info.node_base_info.status = NodeBaseStaticInfo::Status::OFFLINE;
  itr->second->static_info.node_base_info.soc = "";
  itr->second->static_info.node_base_info.pid = 0;
}

void DataManager::SetWebModuleDetailInfoResponse(const std::string& node_name, const std::string& module_name, ::aimrt::protocols::viz_web::ModuleDetailInfoResponse& rsp) {
  std::shared_ptr<const InfoRegistry> new_data_ptr;

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  auto* static_info = rsp.mutable_module_detail_static_info();
  auto* base_info = static_info->mutable_base_info();
  auto node_info_itr = new_data_ptr->node_info_registry_.find(node_name);
  if (node_info_itr == new_data_ptr->node_info_registry_.end()) {
    AIMRT_ERROR("NodeInfo not found: {}", node_name);
    return;
  }

  auto soc = node_info_itr->second->static_info.node_base_info.soc;
  auto pid = node_info_itr->second->static_info.node_base_info.pid;

  auto& module_info_list = node_info_itr->second->static_info.module_info.module_info_list;
  for (const auto& module_info : module_info_list) {
    if (module_info.name == module_name) {
      base_info->set_name(module_info.name);
      base_info->set_log_lvl(module_info.log_lvl);
      base_info->set_pkg_path(module_info.pkg_path);
      base_info->set_cfg_path(module_info.cfg_path);
      base_info->set_version(module_info.version);
      base_info->set_author(module_info.author);
      base_info->set_description(module_info.description);
      base_info->set_options_id(module_info.options_id);
      break;
    }
  }

  auto* rpc_static_info = rsp.mutable_module_detail_static_info();
  auto* rpc_dynamic_info = rsp.mutable_module_detail_dynamic_info();
  auto& rpc_info_list = new_data_ptr->rpc_info_registry_;

  NodeModeKey node_mode_key{
      .node_name = node_name,
      .mode = module_name,
      .soc = soc,
      .pid = pid,
  };

  for (const auto& [rpc_key, rpc_info_wrapper] : rpc_info_list) {
    if (rpc_info_wrapper->server_dynamic_info_map.find(node_mode_key) != rpc_info_wrapper->server_dynamic_info_map.end()) {
      auto& server_dynamic_info_meta = rpc_info_wrapper->server_dynamic_info_map.at(node_mode_key);
      auto* server_info = rpc_static_info->add_server_info();
      server_info->set_func_name(rpc_key.func_name);
      for (auto& backend : server_dynamic_info_meta.backends) {
        server_info->add_backend(backend);
      }
      for (auto& filter : server_dynamic_info_meta.filters) {
        server_info->add_filters(filter);
      }
      auto* server_dynamic_info = rpc_dynamic_info->add_server_info();
      server_dynamic_info->set_func_name(rpc_key.func_name);
      for (auto& [node_mode_key, _] : rpc_info_wrapper->client_dynamic_info_map) {
        auto* connected_to = server_dynamic_info->add_conneced_to();
        connected_to->set_soc(node_mode_key.soc);
        connected_to->set_pid(node_mode_key.pid);
        connected_to->set_node_name(node_mode_key.node_name);
        connected_to->set_module_name(node_mode_key.mode);
      }
    }

    if (rpc_info_wrapper->client_dynamic_info_map.find(node_mode_key) != rpc_info_wrapper->client_dynamic_info_map.end()) {
      auto& client_dynamic_info_meta = rpc_info_wrapper->client_dynamic_info_map.at(node_mode_key);
      auto* client_info = rpc_static_info->add_client_info();
      client_info->set_func_name(rpc_key.func_name);
      for (auto& backend : client_dynamic_info_meta.backends) {
        client_info->add_backend(backend);
      }
      for (auto& filter : client_dynamic_info_meta.filters) {
        client_info->add_filters(filter);
      }
      auto* client_dynamic_info = rpc_dynamic_info->add_client_info();
      client_dynamic_info->set_func_name(rpc_key.func_name);
      for (auto& [node_mode_key, _] : rpc_info_wrapper->server_dynamic_info_map) {
        auto* connected_to = client_dynamic_info->add_conneced_to();
        connected_to->set_soc(node_mode_key.soc);
        connected_to->set_pid(node_mode_key.pid);
        connected_to->set_node_name(node_mode_key.node_name);
        connected_to->set_module_name(node_mode_key.mode);
      }
    }
  }

  auto* channel_static_info = rsp.mutable_module_detail_static_info();
  auto* channel_dynamic_info = rsp.mutable_module_detail_dynamic_info();
  auto& channel_info_list = new_data_ptr->channel_info_registry_;

  for (const auto& [channel_key, channel_info_wrapper] : channel_info_list) {
    if (channel_info_wrapper->pub_dynamic_info.find(node_mode_key) != channel_info_wrapper->pub_dynamic_info.end()) {
      auto& pub_dynamic_info_meta = channel_info_wrapper->pub_dynamic_info.at(node_mode_key);
      auto* pub_info = channel_static_info->add_pub_info();
      pub_info->set_topic(channel_key.topic_name);
      pub_info->set_msg_type(channel_key.msg_type);
      for (auto& backend : pub_dynamic_info_meta.backends) {
        pub_info->add_backend(backend);
      }
      for (auto& filter : pub_dynamic_info_meta.filters) {
        pub_info->add_filters(filter);
      }
      auto* pub_dynamic_info = channel_dynamic_info->add_pub_info();
      pub_dynamic_info->set_topic(channel_key.topic_name);
      pub_dynamic_info->set_msg_type(channel_key.msg_type);
      for (auto& [node_mode_key, _] : channel_info_wrapper->sub_dynamic_info) {
        auto* connected_to = pub_dynamic_info->add_connected_to();
        connected_to->set_soc(node_mode_key.soc);
        connected_to->set_pid(node_mode_key.pid);
        connected_to->set_node_name(node_mode_key.node_name);
        connected_to->set_module_name(node_mode_key.mode);
      }
    }

    if (channel_info_wrapper->sub_dynamic_info.find(node_mode_key) != channel_info_wrapper->sub_dynamic_info.end()) {
      auto& sub_dynamic_info_meta = channel_info_wrapper->sub_dynamic_info.at(node_mode_key);
      auto* sub_info = channel_static_info->add_sub_info();
      sub_info->set_topic(channel_key.topic_name);
      sub_info->set_msg_type(channel_key.msg_type);
      for (auto& backend : sub_dynamic_info_meta.backends) {
        sub_info->add_backend(backend);
      }
      for (auto& filter : sub_dynamic_info_meta.filters) {
        sub_info->add_filters(filter);
      }
      auto* sub_dynamic_info = channel_dynamic_info->add_sub_info();
      sub_dynamic_info->set_topic(channel_key.topic_name);
      sub_dynamic_info->set_msg_type(channel_key.msg_type);
      for (auto& [node_mode_key, _] : channel_info_wrapper->pub_dynamic_info) {
        auto* connected_to = sub_dynamic_info->add_connected_to();
        connected_to->set_soc(node_mode_key.soc);
        connected_to->set_pid(node_mode_key.pid);
        connected_to->set_node_name(node_mode_key.node_name);
        connected_to->set_module_name(node_mode_key.mode);
      }
    }
  }
}

void DataManager::SetWebRpcIndexInfoResponse(::aimrt::protocols::viz_web::RpcIndexInfoResponse& rsp) {
  std::shared_ptr<const InfoRegistry> new_data_ptr;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  auto* rpc_index_dynamic_info = rsp.mutable_rpc_index_dynamic_info();

  for (const auto& [rpc_key, rpc_info_wrapper] : new_data_ptr->rpc_info_registry_) {
    auto* rpc_dynamic_info_meta = rpc_index_dynamic_info->add_dynamic_info_meta();
    rpc_dynamic_info_meta->set_func_name(rpc_key.func_name);
    rpc_dynamic_info_meta->set_client_count(rpc_info_wrapper->client_dynamic_info_map.size());
    rpc_dynamic_info_meta->set_server_count(rpc_info_wrapper->server_dynamic_info_map.size());
    for (auto& backend : rpc_info_wrapper->used_backends) {
      rpc_dynamic_info_meta->add_backend_name(backend.first);
    }
    for (auto& filter : rpc_info_wrapper->used_filters) {
      rpc_dynamic_info_meta->add_filter_name(filter.first);
    }
    double client_qps = 0, server_qps = 0;
    for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->client_dynamic_info_map) {
      client_qps += rpc_dynamic_info_meta.frequency;
    }
    for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->server_dynamic_info_map) {
      server_qps += rpc_dynamic_info_meta.frequency;
    }
    rpc_dynamic_info_meta->set_client_qps(client_qps);
    rpc_dynamic_info_meta->set_server_qps(server_qps);
  }
}

void DataManager::SetWebRpcDetailInfoResponse(const std::string& func_name, ::aimrt::protocols::viz_web::RpcDetailInfoResponse& rsp) {
  auto new_data_ptr = std::make_shared<const InfoRegistry>();
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  auto* rpc_detail_static_info = rsp.mutable_rpc_detail_static_info();
  auto* rpc_detail_dynamic_info = rsp.mutable_rpc_detail_dynamic_info();
  RpcMetaKey rpc_meta_key{
      .func_name = func_name,
  };
  auto rpc_info_itr = new_data_ptr->rpc_info_registry_.find(rpc_meta_key);

  if (rpc_info_itr == new_data_ptr->rpc_info_registry_.end()) {
    AIMRT_ERROR("RpcInfo not found: {}", func_name);
    return;
  }

  auto& rpc_info_wrapper = rpc_info_itr->second;

  auto* rpc_base_info = rpc_detail_static_info->mutable_base_info();

  rpc_base_info->set_func_name(func_name);
  rpc_base_info->set_request_type(rpc_info_wrapper->req_type);
  rpc_base_info->set_response_type(rpc_info_wrapper->rsp_type);
  rpc_base_info->set_request_schema_id(rpc_info_wrapper->req_schema_id);
  rpc_base_info->set_response_schema_id(rpc_info_wrapper->rsp_schema_id);
  for (auto& backend : rpc_info_wrapper->used_backends) {
    rpc_base_info->add_backend_name(backend.first);
  }
  for (auto& filter : rpc_info_wrapper->used_filters) {
    rpc_base_info->add_filter_name(filter.first);
  }

  auto* rpc_client_info = rpc_detail_dynamic_info->mutable_client_info();
  auto* rpc_server_info = rpc_detail_dynamic_info->mutable_server_info();

  double client_qps = 0, client_seq_num = 0, client_history_seq_num = 0, client_history_error_count = 0, client_error_count = 0;
  for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->client_dynamic_info_map) {
    auto* rpc_module_status_info = rpc_client_info->add_module_infos();
    rpc_module_status_info->set_node_name(node_mode_key.node_name);
    rpc_module_status_info->set_module_name(node_mode_key.mode);
    for (auto& backend : rpc_dynamic_info_meta.backends) {
      rpc_module_status_info->add_backend_name(backend);
    }
    for (auto& filter : rpc_dynamic_info_meta.filters) {
      rpc_module_status_info->add_filter_name(filter);
    }
    rpc_module_status_info->set_qps(rpc_dynamic_info_meta.frequency);
    rpc_module_status_info->set_latency_us(rpc_dynamic_info_meta.latency_us);
    rpc_module_status_info->set_error_rate(rpc_dynamic_info_meta.error_rate);

    client_qps += rpc_dynamic_info_meta.frequency;
    client_seq_num += rpc_dynamic_info_meta.seq_num;
    client_error_count += rpc_dynamic_info_meta.error_count;

    client_history_seq_num += rpc_dynamic_info_meta.history_seq_num;
    client_history_error_count += rpc_dynamic_info_meta.history_error_count;
  }
  auto client_status_info = rpc_client_info->mutable_current_status();
  client_status_info->set_qps(client_qps);
  client_status_info->set_error_rate(client_seq_num > 0 ? static_cast<double>(client_error_count) / static_cast<double>(client_seq_num) : 0);

  auto client_history_status_info = rpc_client_info->mutable_history_stats();
  client_history_status_info->set_seq_num(client_history_seq_num);
  client_history_status_info->set_error_count(client_history_error_count);

  double server_qps = 0, server_history_seq_num = 0, server_history_error_count = 0, server_seq_num = 0, server_error_count = 0;
  for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->server_dynamic_info_map) {
    auto* rpc_module_status_info = rpc_server_info->add_module_infos();
    rpc_module_status_info->set_node_name(node_mode_key.node_name);
    rpc_module_status_info->set_module_name(node_mode_key.mode);
    for (auto& backend : rpc_dynamic_info_meta.backends) {
      rpc_module_status_info->add_backend_name(backend);
    }
    for (auto& filter : rpc_dynamic_info_meta.filters) {
      rpc_module_status_info->add_filter_name(filter);
    }
    rpc_module_status_info->set_qps(rpc_dynamic_info_meta.frequency);
    rpc_module_status_info->set_latency_us(rpc_dynamic_info_meta.latency_us);
    rpc_module_status_info->set_error_rate(rpc_dynamic_info_meta.error_rate);

    server_qps += rpc_dynamic_info_meta.frequency;
    server_seq_num += rpc_dynamic_info_meta.seq_num;
    server_error_count += rpc_dynamic_info_meta.error_count;

    server_history_seq_num += rpc_dynamic_info_meta.history_seq_num;
    server_history_error_count += rpc_dynamic_info_meta.history_error_count;
  }
  auto server_status_info = rpc_server_info->mutable_current_status();
  server_status_info->set_qps(server_qps);
  server_status_info->set_error_rate(server_seq_num > 0 ? static_cast<double>(server_error_count) / static_cast<double>(server_seq_num) : 0);

  auto server_history_status_info = rpc_server_info->mutable_history_stats();
  server_history_status_info->set_seq_num(server_history_seq_num);
  server_history_status_info->set_error_count(server_history_error_count);

  // endpoint info
  for (auto& backend : rpc_info_wrapper->used_backends) {
    auto* rpc_endpoint_info = rpc_detail_dynamic_info->add_endpoint_info();
    rpc_endpoint_info->set_backend_name(backend.first);
    for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->client_dynamic_info_map) {
      if (rpc_dynamic_info_meta.backends.find(backend.first) == rpc_dynamic_info_meta.backends.end()) {
        continue;
      }
      auto* client_endpoint_info = rpc_endpoint_info->add_client_endpoints();
      client_endpoint_info->set_node_name(node_mode_key.node_name);
      client_endpoint_info->set_module_name(node_mode_key.mode);
      for (auto& filter : rpc_dynamic_info_meta.filters) {
        client_endpoint_info->add_filter_name(filter);
      }
    }
    for (auto& [node_mode_key, rpc_dynamic_info_meta] : rpc_info_wrapper->server_dynamic_info_map) {
      if (rpc_dynamic_info_meta.backends.find(backend.first) == rpc_dynamic_info_meta.backends.end()) {
        continue;
      }
      auto* server_endpoint_info = rpc_endpoint_info->add_server_endpoints();
      server_endpoint_info->set_node_name(node_mode_key.node_name);
      server_endpoint_info->set_module_name(node_mode_key.mode);
      for (auto& filter : rpc_dynamic_info_meta.filters) {
        server_endpoint_info->add_filter_name(filter);
      }
    }
  }
}

void DataManager::SetWebChannelIndexInfoResponse(::aimrt::protocols::viz_web::ChannelIndexInfoResponse& rsp) {
  auto new_data_ptr = std::make_shared<const InfoRegistry>();
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  auto* channel_index_dynamic_info = rsp.mutable_channel_index_dynamic_info();

  for (const auto& [channel_key, channel_info_wrapper] : new_data_ptr->channel_info_registry_) {
    auto* channel_dynamic_info_meta = channel_index_dynamic_info->add_dynamic_info_meta();
    channel_dynamic_info_meta->set_topic_name(channel_key.topic_name);
    channel_dynamic_info_meta->set_msg_type(channel_key.msg_type);
    channel_dynamic_info_meta->set_sub_count(channel_info_wrapper->sub_dynamic_info.size());
    channel_dynamic_info_meta->set_pub_count(channel_info_wrapper->pub_dynamic_info.size());
    for (auto& backend : channel_info_wrapper->used_backends) {
      channel_dynamic_info_meta->add_backend_name(backend.first);
    }
    for (auto& filter : channel_info_wrapper->used_filters) {
      channel_dynamic_info_meta->add_filter_name(filter.first);
    }
    double sub_frequency = 0, pub_frequency = 0;
    for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->sub_dynamic_info) {
      sub_frequency += channel_dynamic_info_meta.frequency;
    }
    channel_dynamic_info_meta->set_sub_frequency(sub_frequency);

    for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->pub_dynamic_info) {
      pub_frequency += channel_dynamic_info_meta.frequency;
    }
    channel_dynamic_info_meta->set_pub_frequency(pub_frequency);
  }
}

void DataManager::SetWebChannelDetailInfoResponse(const std::string& topic_name, const std::string& msg_type, ::aimrt::protocols::viz_web::ChannelDetailInfoResponse& rsp) {
  auto new_data_ptr = std::make_shared<const InfoRegistry>();

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }
  ChannelMetaKey channel_key{
      .topic_name = topic_name,
      .msg_type = msg_type,
  };

  auto* channel_detail_static_info = rsp.mutable_channel_detail_static_info();
  auto* channel_detail_dynamic_info = rsp.mutable_channel_detail_dynamic_info();

  auto channel_info_itr = new_data_ptr->channel_info_registry_.find(channel_key);
  if (channel_info_itr == new_data_ptr->channel_info_registry_.end()) {
    AIMRT_ERROR("ChannelInfo not found: {}", topic_name);
    return;
  }

  auto& channel_info_wrapper = channel_info_itr->second;

  auto* channel_base_info = channel_detail_static_info->mutable_base_info();
  channel_base_info->set_topic_name(topic_name);
  channel_base_info->set_msg_type(msg_type);
  channel_base_info->set_schema_id(channel_info_wrapper->schema_id);
  for (auto& backend : channel_info_wrapper->used_backends) {
    channel_base_info->add_backend_name(backend.first);
  }
  for (auto& filter : channel_info_wrapper->used_filters) {
    channel_base_info->add_filter_name(filter.first);
  }

  auto* channel_sub_info = channel_detail_dynamic_info->mutable_sub_info();
  auto* channel_pub_info = channel_detail_dynamic_info->mutable_pub_info();

  double sub_frequency = 0;
  uint64_t sub_seq_num = 0;
  for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->sub_dynamic_info) {
    auto* channel_module_status_info = channel_sub_info->add_module_infos();
    channel_module_status_info->set_node_name(node_mode_key.node_name);
    channel_module_status_info->set_module_name(node_mode_key.mode);
    for (auto& backend : channel_dynamic_info_meta.backends) {
      channel_module_status_info->add_backend_name(backend);
    }
    for (auto& filter : channel_dynamic_info_meta.filters) {
      channel_module_status_info->add_filter_name(filter);
    }
    channel_module_status_info->set_frequency(channel_dynamic_info_meta.frequency);
    sub_frequency += channel_dynamic_info_meta.frequency;
    sub_seq_num += channel_dynamic_info_meta.history_seq_num;
  }
  auto sub_status_info = channel_sub_info->mutable_current_status();
  sub_status_info->set_frequency(sub_frequency);

  auto sub_history_status_info = channel_sub_info->mutable_history_stats();
  sub_history_status_info->set_seq_num(sub_seq_num);

  double pub_frequency = 0;
  uint64_t pub_seq_num = 0;
  for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->pub_dynamic_info) {
    auto* channel_module_status_info = channel_pub_info->add_module_infos();
    channel_module_status_info->set_node_name(node_mode_key.node_name);
    channel_module_status_info->set_module_name(node_mode_key.mode);
    for (auto& backend : channel_dynamic_info_meta.backends) {
      channel_module_status_info->add_backend_name(backend);
    }
    for (auto& filter : channel_dynamic_info_meta.filters) {
      channel_module_status_info->add_filter_name(filter);
    }
    channel_module_status_info->set_frequency(channel_dynamic_info_meta.frequency);
    pub_frequency += channel_dynamic_info_meta.frequency;
    pub_seq_num += channel_dynamic_info_meta.history_seq_num;
  }
  auto pub_status_info = channel_pub_info->mutable_current_status();
  pub_status_info->set_frequency(pub_frequency);

  auto pub_history_status_info = channel_pub_info->mutable_history_stats();
  pub_history_status_info->set_seq_num(pub_seq_num);

  // endpoint info
  for (auto& backend : channel_info_wrapper->used_backends) {
    auto* channel_endpoint_info = channel_detail_dynamic_info->add_endpoint_info();
    channel_endpoint_info->set_backend_name(backend.first);
    for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->sub_dynamic_info) {
      if (channel_dynamic_info_meta.backends.find(backend.first) == channel_dynamic_info_meta.backends.end()) {
        continue;
      }
      auto* sub_endpoint_info = channel_endpoint_info->add_sub_endpoints();
      sub_endpoint_info->set_node_name(node_mode_key.node_name);
      sub_endpoint_info->set_module_name(node_mode_key.mode);
      for (auto& filter : channel_dynamic_info_meta.filters) {
        sub_endpoint_info->add_filter_name(filter);
      }
    }
    for (auto& [node_mode_key, channel_dynamic_info_meta] : channel_info_wrapper->pub_dynamic_info) {
      if (channel_dynamic_info_meta.backends.find(backend.first) == channel_dynamic_info_meta.backends.end()) {
        continue;
      }
      auto* pub_endpoint_info = channel_endpoint_info->add_pub_endpoints();
      pub_endpoint_info->set_node_name(node_mode_key.node_name);
      pub_endpoint_info->set_module_name(node_mode_key.mode);
      for (auto& filter : channel_dynamic_info_meta.filters) {
        pub_endpoint_info->add_filter_name(filter);
      }
    }
  }
}

void DataManager::SetWebResourceResponse(const uint32_t& resource_id, ::aimrt::protocols::viz_web::GetResourceResponse& rsp) {
  auto new_data_ptr = std::make_shared<const InfoRegistry>();
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    new_data_ptr = m_active_data_;
  }

  auto resource_info_itr = new_data_ptr->resource_info_registry_.find(resource_id);
  if (resource_info_itr == new_data_ptr->resource_info_registry_.end()) {
    AIMRT_ERROR("ResourceInfo not found: {}", resource_id);
    return;
  }

  auto& resource_info_wrapper = resource_info_itr->second;
  rsp.set_resource_id(resource_id);
  if (resource_info_wrapper->type == ResourceType::STRING) {
    rsp.set_data(std::get<std::string>(resource_info_wrapper->data));
  }
}

}  // namespace aimrt_viz::viz_module