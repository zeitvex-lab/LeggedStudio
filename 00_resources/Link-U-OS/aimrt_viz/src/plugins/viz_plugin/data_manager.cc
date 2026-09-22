// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include <unistd.h>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

#include "aimrt_module_cpp_interface/rpc/rpc_status.h"
#include "core/channel/channel_backend_tools.h"
#include "core/rpc/rpc_backend_tools.h"
#include "core/util/version.h"
#include "data_manager.h"
#include "process_info.h"
#include "ros_storage.h"
#include "util.h"
#include "util/sys_tools.h"
#include "yaml-cpp/node/emit.h"
#include "yaml-cpp/node/node.h"
#include "yaml-cpp/node/parse.h"

namespace aimrt::plugins::viz_plugin {

bool DataManager::Initialize(aimrt::runtime::core::AimRTCore* core_ptr) {
  core_ptr_ = core_ptr;
  process_info_manager_ptr_ = std::make_unique<ProcessInfoManager>();
  process_info_manager_ptr_->Initialize(aimrt::common::util::GetCurrentProcessPid());
  return true;
}

void DataManager::SetBaseInfo(const std::string& node_name, const std::string& soc) {
  static_info_wrapper_.node_static_info.aimrt_version = runtime::core::util::GetAimRTVersion();
  static_info_wrapper_.node_static_info.cfg_file_path = core_ptr_->GetConfiguratorManager().GetConfigureFilePath();
  static_info_wrapper_.node_static_info.executable_path = aimrt::common::util::GetExecutablePath();
  static_info_wrapper_.node_static_info.pid = getpid(),
  static_info_wrapper_.node_static_info.node_name = node_name;
  static_info_wrapper_.node_static_info.soc = soc;
  static_info_wrapper_.node_static_info.start_time_stamp_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}

void DataManager::SetPluginList() {
  for (auto& plugin : core_ptr_->GetPluginManager().GetOptions().plugins_options) {
    YAML::Node plugin_options;
    plugin_options["options"] = plugin.options;
    static_info_wrapper_.plugin_static_info.plugin_list.emplace_back(PluginInfoMeta{
        .name = plugin.name,
        .path = plugin.path,
        .options = YAML::Dump(plugin_options),
    });
  }
}

void DataManager::SetExecutorList() {
  auto cfg = core_ptr_->GetConfiguratorManager().GetRootOptionsNode();
  std::unordered_map<std::string, std::string> executor_options_map;
  if (cfg["aimrt"] && cfg["aimrt"]["executor"] && cfg["aimrt"]["executor"]["executors"]) {
    for (const auto& executor : cfg["aimrt"]["executor"]["executors"]) {
      auto name = executor["name"].as<std::string>();
      YAML::Node executor_options;
      executor_options["options"] = executor["options"];
      executor_options_map.emplace(name, YAML::Dump(executor_options));
    }
  }

  for (auto& executor : core_ptr_->GetExecutorManager().GetAllExecutors()) {
    static_info_wrapper_.executor_static_info.executor_list.emplace_back(ExecutorInfoMeta{
        .name = std::string(executor->Name()),
        .type = std::string(executor->Type()),
        .thread_safe = executor->ThreadSafe(),
        .support_time_schedule = executor->SupportTimerSchedule(),
        .options = executor_options_map[std::string(executor->Name())],
    });
  }
  for (auto& executor : core_ptr_->GetExecutorManager().GetExecutorGenFuncMap()) {
    static_info_wrapper_.executor_static_info.available_executors.emplace_back(executor.first);
  }

  if (cfg["aimrt"] && cfg["aimrt"]["main_thread"]) {
    auto main_thread_cfg = cfg["aimrt"]["main_thread"];
    if (main_thread_cfg["name"]) {
      static_info_wrapper_.executor_static_info.core_threads.main_thread.name = main_thread_cfg["name"].as<std::string>();
      static_info_wrapper_.executor_static_info.core_threads.main_thread.tid = getpid();
    }
    if (main_thread_cfg["thread_sched_policy"]) {
      static_info_wrapper_.executor_static_info.core_threads.main_thread.thread_sched_policy = main_thread_cfg["thread_sched_policy"].as<std::string>();
    }
    if (main_thread_cfg["bind_cpu"]) {
      for (const auto& cpu : main_thread_cfg["bind_cpu"]) {
        static_info_wrapper_.executor_static_info.core_threads.main_thread.bind_cpu.emplace_back(cpu.as<uint32_t>());
      }
    }
  }
  if (cfg["aimrt"] && cfg["aimrt"]["guard_thread"]) {
    auto guard_thread_cfg = cfg["aimrt"]["guard_thread"];
    if (guard_thread_cfg["name"]) {
      auto name = guard_thread_cfg["name"].as<std::string>();
      static_info_wrapper_.executor_static_info.core_threads.guard_thread.name = name;
      static_info_wrapper_.executor_static_info.core_threads.guard_thread.tid = process_info_manager_ptr_->GetGuardThreadTid(name);
    }
    if (guard_thread_cfg["thread_sched_policy"]) {
      static_info_wrapper_.executor_static_info.core_threads.guard_thread.thread_sched_policy = guard_thread_cfg["thread_sched_policy"].as<std::string>();
    }
    if (guard_thread_cfg["bind_cpu"]) {
      for (const auto& cpu : guard_thread_cfg["bind_cpu"]) {
        static_info_wrapper_.executor_static_info.core_threads.guard_thread.bind_cpu.emplace_back(cpu.as<uint32_t>());
      }
    }
  }
}

void DataManager::SetConfig() {
  static_info_wrapper_.cfg_static_info.original_cfg_file = YAML::Dump(core_ptr_->GetConfiguratorManager().GetOriRootOptionsNode());
  static_info_wrapper_.cfg_static_info.parsed_cfg_file = YAML::Dump(core_ptr_->GetConfiguratorManager().GetRootOptionsNode());
}

void DataManager::SetLog() {
  auto cfg = core_ptr_->GetConfiguratorManager().GetRootOptionsNode();
  if (cfg["aimrt"] && cfg["aimrt"]["log"]) {
    auto log_cfg = cfg["aimrt"]["log"];
    if (log_cfg["core_lvl"]) {
      static_info_wrapper_.log_static_info.core_level = log_cfg["core_lvl"].as<std::string>();
    }
    if (log_cfg["default_module_lvl"]) {
      static_info_wrapper_.log_static_info.default_module_level = log_cfg["default_module_lvl"].as<std::string>();
    }
    if (log_cfg["backends"]) {
      for (const auto& backend : log_cfg["backends"]) {
        YAML::Node backend_options;
        backend_options["options"] = backend["options"];
        static_info_wrapper_.log_static_info.backend_list.emplace_back(LogBackendInfoMeta{
            .type = backend["type"].as<std::string>(),
            .options = YAML::Dump(backend_options),
        });
      }
    }
  }
}

void DataManager::SetPubChannel() {
  auto& channel_static_info = static_info_wrapper_.channel_static_info;

  for (auto& item : core_ptr_->GetChannelManager().GetPublishFilterManager().GetAllFiltersName()) {
    static_info_wrapper_.channel_static_info.available_pub_filters.emplace_back(item);
  }

  auto pub_backend_mp = core_ptr_->GetChannelManager().GetChannelBackendManager().GetPubTopicBackendInfo();
  for (auto& [key, value] : core_ptr_->GetChannelManager().GetChannelRegistry()->GetPubTopicIndexMap()) {
    for (auto& item : value) {
      auto backend_itr = pub_backend_mp.find(item->info.topic_name);
      AIMRT_CHECK_ERROR_THROW(backend_itr != pub_backend_mp.end(), "pub_backend_mp not found");
      std::vector<std::string> backend_list;
      std::transform(backend_itr->second.begin(), backend_itr->second.end(),
                     std::back_inserter(backend_list),
                     [](auto& backend) { return std::string(backend); });

      std::string schema;
      if (item->info.msg_type_support_ref.DefaultSerializationType() == "ros2") {
        auto ts_ptr = reinterpret_cast<const rosidl_message_type_support_t*>(item->info.msg_type_support_ref.CustomTypeSupportPtr());
        const rosidl_message_type_support_t* specific_support = ts_ptr->func(ts_ptr, "rosidl_typesupport_introspection_cpp");
        const auto* type_data = static_cast<const MessageMembers*>(specific_support->data);
        schema = ros2_identifier::BuildRos2Schema(type_data, 0);
      } else if (item->info.msg_type_support_ref.DefaultSerializationType() == "pb") {
        auto req_type_descriptor = reinterpret_cast<const google::protobuf::Descriptor*>(item->info.msg_type_support_ref.CustomTypeSupportPtr());
        schema = proto_identifier::BuildPbSchema(req_type_descriptor);
      } else {
        AIMRT_ERROR("unsupported serialization type: {}", item->info.msg_type_support_ref.DefaultSerializationType());
      }

      channel_static_info.pub_list.emplace_back(ChannelPubInfoMeta{
          .topic = item->info.topic_name,
          .msg_type = item->info.msg_type,
          .schema = schema,
          .modules = {item->info.module_name},
          .backends = backend_list,
          .filters = core_ptr_->GetChannelManager().GetPublishFilterManager().GetFilterNameVec(item->info.topic_name)});

      channel_pub_stats_map_.try_emplace(TopicMetaKey{
          .topic_name = item->info.topic_name,
          .msg_type = item->info.msg_type,
          .module_name = item->info.module_name,
          .pkg_path = item->info.pkg_path,
      });
    }
  }
}

void DataManager::SetSubChannel() {
  auto& channel_static_info = static_info_wrapper_.channel_static_info;

  for (auto& item : core_ptr_->GetChannelManager().GetSubscribeFilterManager().GetAllFiltersName()) {
    channel_static_info.available_sub_filters.emplace_back(item);
  }

  auto sub_backend_mp = core_ptr_->GetChannelManager().GetChannelBackendManager().GetSubTopicBackendInfo();
  for (auto& [key, value] : core_ptr_->GetChannelManager().GetChannelRegistry()->GetSubTopicIndexMap()) {
    for (auto& item : value) {
      auto backend_itr = sub_backend_mp.find(item->info.topic_name);
      AIMRT_CHECK_ERROR_THROW(backend_itr != sub_backend_mp.end(), "pub_backend_mp not found");
      std::vector<std::string> backend_list;
      std::transform(backend_itr->second.begin(), backend_itr->second.end(),
                     std::back_inserter(backend_list),
                     [](auto& backend) { return std::string(backend); });

      std::string schema;

      if (item->info.msg_type_support_ref.DefaultSerializationType() == "ros2") {
        auto ts_ptr = reinterpret_cast<const rosidl_message_type_support_t*>(item->info.msg_type_support_ref.CustomTypeSupportPtr());
        const rosidl_message_type_support_t* specific_support = ts_ptr->func(ts_ptr, "rosidl_typesupport_introspection_cpp");
        const auto* type_data = static_cast<const MessageMembers*>(specific_support->data);
        schema = ros2_identifier::BuildRos2Schema(type_data, 0);
      } else if (item->info.msg_type_support_ref.DefaultSerializationType() == "pb") {
        auto msg_type_descriptor = reinterpret_cast<const google::protobuf::Descriptor*>(item->info.msg_type_support_ref.CustomTypeSupportPtr());
        schema = proto_identifier::BuildPbSchema(msg_type_descriptor);
      } else {
        AIMRT_ERROR("unsupported serialization type: {}", item->info.msg_type_support_ref.DefaultSerializationType());
      }

      channel_static_info.sub_list.emplace_back(ChannelSubInfoMeta{
          .topic = item->info.topic_name,
          .msg_type = item->info.msg_type,
          .schema = schema,
          .modules = {item->info.module_name},
          .backends = backend_list,
          .filters = core_ptr_->GetChannelManager().GetSubscribeFilterManager().GetFilterNameVec(item->info.topic_name)});

      channel_sub_stats_map_.try_emplace(TopicMetaKey{
          .topic_name = item->info.topic_name,
          .msg_type = item->info.msg_type,
          .module_name = item->info.module_name,
          .pkg_path = item->info.pkg_path,
      });
    }
  }
}

void DataManager::SetRpcServer() {
  for (auto& item : core_ptr_->GetRpcManager().GetServerFilterManager().GetAllFiltersName()) {
    static_info_wrapper_.rpc_static_info.available_server_filters.emplace_back(item);
  }
  auto svr_backend_mp = core_ptr_->GetRpcManager().GetRpcBackendManager().GetServersBackendInfo();
  for (auto& [key, value] : core_ptr_->GetRpcManager().GetRpcRegistry()->GetServiceIndexMap()) {
    for (auto& item : value) {
      auto backend_itr = svr_backend_mp.find(item->info.func_name);
      AIMRT_CHECK_ERROR_THROW(backend_itr != svr_backend_mp.end(), "rpc server backend info not found");

      std::vector<std::string> backend_list;

      std::transform(backend_itr->second.begin(), backend_itr->second.end(),
                     std::back_inserter(backend_list),
                     [](auto& backend) { return std::string(backend); });

      std::string req_type_schema;
      std::string rsp_type_schema;
      if (item->info.req_type_support_ref.DefaultSerializationType() == "ros2") {
        auto ts_ptr = reinterpret_cast<const rosidl_message_type_support_t*>(item->info.req_type_support_ref.CustomTypeSupportPtr());
        const rosidl_message_type_support_t* specific_support = ts_ptr->func(ts_ptr, "rosidl_typesupport_introspection_cpp");
        const auto* type_data = static_cast<const MessageMembers*>(specific_support->data);
        req_type_schema = ros2_identifier::BuildRos2Schema(type_data, 0);

        ts_ptr = reinterpret_cast<const rosidl_message_type_support_t*>(item->info.rsp_type_support_ref.CustomTypeSupportPtr());
        specific_support = ts_ptr->func(ts_ptr, "rosidl_typesupport_introspection_cpp");
        type_data = static_cast<const MessageMembers*>(specific_support->data);
        rsp_type_schema = ros2_identifier::BuildRos2Schema(type_data, 0);

      } else if (item->info.req_type_support_ref.DefaultSerializationType() == "pb") {
        auto req_type_descriptor = reinterpret_cast<const google::protobuf::Descriptor*>(item->info.req_type_support_ref.CustomTypeSupportPtr());
        req_type_schema = proto_identifier::BuildPbSchema(req_type_descriptor);
        auto rsp_type_descriptor = reinterpret_cast<const google::protobuf::Descriptor*>(item->info.rsp_type_support_ref.CustomTypeSupportPtr());
        rsp_type_schema = proto_identifier::BuildPbSchema(rsp_type_descriptor);
      } else {
        AIMRT_ERROR("unsupported serialization type: {}", item->info.req_type_support_ref.DefaultSerializationType());
      }

      static_info_wrapper_.rpc_static_info.server_list.emplace_back(RpcServerInfoMeta{
          .func_name = item->info.func_name,
          .req_type = std::string(item->info.req_type_support_ref.TypeName()),
          .rsp_type = std::string(item->info.rsp_type_support_ref.TypeName()),
          .req_schema = req_type_schema,
          .rsp_schema = rsp_type_schema,
          .modules = {item->info.module_name},
          .backends = backend_list,
          .filters = core_ptr_->GetRpcManager().GetServerFilterManager().GetFilterNameVec(item->info.func_name),
      });

      rpc_server_stats_map_.try_emplace(RpcMetaKey{
          .func_name = item->info.func_name,
          .module_name = item->info.module_name,
      });
    }
  }
}

void DataManager::SetRpcClient() {
  for (auto& item : core_ptr_->GetRpcManager().GetClientFilterManager().GetAllFiltersName()) {
    static_info_wrapper_.rpc_static_info.available_client_filters.emplace_back(item);
  }
  auto cli_backend_mp = core_ptr_->GetRpcManager().GetRpcBackendManager().GetClientsBackendInfo();
  for (auto& [key, value] : core_ptr_->GetRpcManager().GetRpcRegistry()->GetClientIndexMap()) {
    for (auto& item : value) {
      auto backend_itr = cli_backend_mp.find(item->info.func_name);
      AIMRT_CHECK_ERROR_THROW(backend_itr != cli_backend_mp.end(), "rpc client backend info not found");

      std::vector<std::string> backend_list;
      std::transform(backend_itr->second.begin(), backend_itr->second.end(),
                     std::back_inserter(backend_list),
                     [](auto& backend) { return std::string(backend); });

      std::string req_type_schema;
      std::string rsp_type_schema;
      if (item->info.req_type_support_ref.DefaultSerializationType() == "ros2") {
        auto ts_ptr = reinterpret_cast<const rosidl_message_type_support_t*>(item->info.req_type_support_ref.CustomTypeSupportPtr());
        const rosidl_message_type_support_t* specific_support = ts_ptr->func(ts_ptr, "rosidl_typesupport_introspection_cpp");
        const auto* type_data = static_cast<const MessageMembers*>(specific_support->data);
        req_type_schema = ros2_identifier::BuildRos2Schema(type_data, 0);

        ts_ptr = reinterpret_cast<const rosidl_message_type_support_t*>(item->info.rsp_type_support_ref.CustomTypeSupportPtr());
        specific_support = ts_ptr->func(ts_ptr, "rosidl_typesupport_introspection_cpp");
        type_data = static_cast<const MessageMembers*>(specific_support->data);
        rsp_type_schema = ros2_identifier::BuildRos2Schema(type_data, 0);

      } else if (item->info.req_type_support_ref.DefaultSerializationType() == "pb") {
        auto req_type_descriptor = reinterpret_cast<const google::protobuf::Descriptor*>(item->info.req_type_support_ref.CustomTypeSupportPtr());
        req_type_schema = proto_identifier::BuildPbSchema(req_type_descriptor);
        auto rsp_type_descriptor = reinterpret_cast<const google::protobuf::Descriptor*>(item->info.rsp_type_support_ref.CustomTypeSupportPtr());
        rsp_type_schema = proto_identifier::BuildPbSchema(rsp_type_descriptor);
      } else {
        AIMRT_ERROR("unsupported serialization type: {}", item->info.req_type_support_ref.DefaultSerializationType());
      }

      static_info_wrapper_.rpc_static_info.client_list.emplace_back(RpcClientInfoMeta{
          .func_name = item->info.func_name,
          .req_type = std::string(item->info.req_type_support_ref.TypeName()),
          .rsp_type = std::string(item->info.rsp_type_support_ref.TypeName()),
          .req_schema = req_type_schema,
          .rsp_schema = rsp_type_schema,
          .modules = {item->info.module_name},
          .backends = backend_list,
          .filters = core_ptr_->GetRpcManager().GetClientFilterManager().GetFilterNameVec(item->info.func_name),
      });

      rpc_client_stats_map_.try_emplace(RpcMetaKey{
          .func_name = item->info.func_name,
          .module_name = item->info.module_name,
      });
    }
  }
}

void DataManager::SetModuleInfo() {
  static constexpr std::array kLvlNameArray = {"Trace", "Debug", "Info", "Warn", "Error", "Fatal", "Off"};

  for (const auto& item : core_ptr_->GetModuleManager().GetModuleDetailInfoList()) {
    std::string log_lvl = item->use_default_log_lvl ? kLvlNameArray[aimrt_log_level_t::AIMRT_LOG_LEVEL_INFO] : kLvlNameArray[item->log_lvl];
    auto cfg_path = item->cfg_file_path.empty() ? core_ptr_->GetConfiguratorManager().GetConfigureFilePath() : item->cfg_file_path;
    auto name = item->name;
    YAML::Node options;
    if (!cfg_path.empty()) {
      YAML::Node cfg_node = YAML::LoadFile(cfg_path);
      if (cfg_node[name]) {
        auto cfg_item = cfg_node[name];
        options["options"] = cfg_item;
      }
    }
    static_info_wrapper_.module_static_info.module_list.emplace_back(ModuleInfoMeta{
        .name = name,
        .log_level = log_lvl,
        .pkg_path = item->pkg_path,
        .cfg_path = cfg_path,
        .version = std::to_string(item->major_version) + "." +
                   std::to_string(item->minor_version) + "." +
                   std::to_string(item->patch_version) + "." +
                   std::to_string(item->build_version),
        .author = item->author,
        .description = item->description,
        .options = YAML::Dump(options),
    });
  }
  static_info_wrapper_.module_static_info.module_list.emplace_back(ModuleInfoMeta{
      .name = "core",
      .log_level = static_info_wrapper_.log_static_info.core_level,
      .pkg_path = "",
      .cfg_path = core_ptr_->GetConfiguratorManager().GetConfigureFilePath(),
  });
}

void DataManager::SetBackends() {
  auto channel_cfg = core_ptr_->GetChannelManager().GetOptions().backends_options;

  for (const auto& backend : channel_cfg) {
    YAML::Node backend_options;
    backend_options["options"] = backend.options;
    static_info_wrapper_.channel_static_info.backend_list.emplace_back(ChannelBackendInfoMeta{
        .type = backend.type,
        .options = YAML::Dump(backend_options),
    });
  }
  auto rpc_cfg = core_ptr_->GetRpcManager().GetOptions().backends_options;
  for (const auto& backend : rpc_cfg) {
    YAML::Node backend_options;
    backend_options["options"] = backend.options;
    static_info_wrapper_.rpc_static_info.backend_list.emplace_back(RpcBackendInfoMeta{
        .type = backend.type,
        .options = YAML::Dump(backend_options),
    });
  }
}

void DataManager::OnPublish(runtime::core::channel::MsgWrapper& msg_wrapper) {
  const auto& info = msg_wrapper.info;

  auto topic_meta_key = TopicMetaKey{
      .topic_name = info.topic_name,
      .msg_type = info.msg_type,
      .module_name = info.module_name,
      .pkg_path = info.pkg_path,
  };
  const auto& topic_meta_itr = channel_pub_stats_map_.find(topic_meta_key);
  if (topic_meta_itr == channel_pub_stats_map_.end()) [[unlikely]] {
    return;
  }
  topic_meta_itr->second.sequence_num.fetch_add(1);
}

void DataManager::OnSubscribe(runtime::core::channel::MsgWrapper& msg_wrapper) {
  const auto& info = msg_wrapper.info;
  auto topic_meta_key = TopicMetaKey{
      .topic_name = info.topic_name,
      .msg_type = info.msg_type,
      .module_name = info.module_name,
      .pkg_path = info.pkg_path,
  };
  auto topic_meta_itr = channel_sub_stats_map_.find(topic_meta_key);
  if (topic_meta_itr == channel_sub_stats_map_.end()) {
    return;
  }
  topic_meta_itr->second.sequence_num.fetch_add(1);
}

void DataManager::OnRpcClient(const std::shared_ptr<runtime::core::rpc::InvokeWrapper>& wrapper_ptr, aimrt::rpc::Status& status, uint64_t begin_time_stamp_us) {
  auto end_time_stamp_us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
  auto duration_us = end_time_stamp_us - begin_time_stamp_us;
  const auto& info = wrapper_ptr->info;
  auto rpc_meta_key = RpcMetaKey{
      .func_name = info.func_name,
      .module_name = info.module_name,
  };
  auto rpc_meta_itr = rpc_client_stats_map_.find(rpc_meta_key);
  if (rpc_meta_itr == rpc_client_stats_map_.end()) [[unlikely]] {
    return;
  }
  rpc_meta_itr->second.latency_us.fetch_add(duration_us);
  rpc_meta_itr->second.sequence_num.fetch_add(1);
  if (!status.OK()) [[unlikely]] {
    rpc_meta_itr->second.error_count.fetch_add(1);
  }
}

void DataManager::OnRpcServer(const std::shared_ptr<runtime::core::rpc::InvokeWrapper>& wrapper_ptr, aimrt::rpc::Status& status, uint64_t begin_time_stamp_us) {
  auto end_time_stamp_us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
  auto duration_us = end_time_stamp_us - begin_time_stamp_us;

  const auto& info = wrapper_ptr->info;
  auto rpc_meta_key = RpcMetaKey{
      .func_name = info.func_name,
      .module_name = info.module_name,
  };

  auto rpc_meta_itr = rpc_server_stats_map_.find(rpc_meta_key);
  if (rpc_meta_itr == rpc_server_stats_map_.end()) [[unlikely]]
    return;
  rpc_meta_itr->second.latency_us.fetch_add(duration_us);
  rpc_meta_itr->second.sequence_num.fetch_add(1);
  if (!status.OK()) [[unlikely]] {
    rpc_meta_itr->second.error_count.fetch_add(1);
  }
}

void DataManager::ReportNodeInfo(const aimrt::protocols::viz_plugin::NodeInfoRequest& req, aimrt::protocols::viz_plugin::NodeInfoResponse& rsp) {
  if (req.soc() != static_info_wrapper_.node_static_info.soc || req.pid() != static_info_wrapper_.node_static_info.pid) {
    SetStaticReply(rsp);
  }
  SetDynamicReply(rsp);
}

void DataManager::SetStaticReply(aimrt::protocols::viz_plugin::NodeInfoResponse& rsp) {
  // 填充节点基本信息

  auto* proto_node_base_info = rsp.mutable_static_info()->mutable_node_base_info();
  const auto& node_static_info = static_info_wrapper_.node_static_info;

  // 节点基本信息
  proto_node_base_info->set_node_name(node_static_info.node_name);
  proto_node_base_info->set_soc(node_static_info.soc);
  proto_node_base_info->set_pid(node_static_info.pid);
  proto_node_base_info->set_aimrt_version(node_static_info.aimrt_version);
  proto_node_base_info->set_start_time_stamp_ns(node_static_info.start_time_stamp_ns);
  proto_node_base_info->set_executable_path(node_static_info.executable_path);
  proto_node_base_info->set_cfg_file_path(node_static_info.cfg_file_path);

  // 配置信息
  auto* proto_conf_static_info = rsp.mutable_static_info()->mutable_configuration_info();

  proto_conf_static_info->set_orin_cfg_file(static_info_wrapper_.cfg_static_info.original_cfg_file);
  proto_conf_static_info->set_parased_cfg_file(static_info_wrapper_.cfg_static_info.parsed_cfg_file);

  // 插件信息
  auto* proto_plugin_static_info = rsp.mutable_static_info()->mutable_plugin_info();

  for (const auto& plugin : static_info_wrapper_.plugin_static_info.plugin_list) {
    auto* proto_plugin = proto_plugin_static_info->add_plugin_info_list();
    proto_plugin->set_name(plugin.name);
    proto_plugin->set_path(plugin.path);
    proto_plugin->set_options(plugin.options);
  }

  // 执行器信息
  auto* proto_exe_static_info = rsp.mutable_static_info()->mutable_executor_info();
  for (const auto& executor : static_info_wrapper_.executor_static_info.available_executors) {
    proto_exe_static_info->add_available_executor_list(executor);
  }

  for (const auto& executor : static_info_wrapper_.executor_static_info.executor_list) {
    auto* proto_executor = proto_exe_static_info->add_executor_info_list();
    proto_executor->set_name(executor.name);
    proto_executor->set_type(executor.type);
    proto_executor->set_thread_safe(executor.thread_safe);
    proto_executor->set_support_time_schedule(executor.support_time_schedule);
    proto_executor->set_options(executor.options);
  }

  auto* proto_core_threads = proto_exe_static_info->mutable_core_threads();
  auto* proto_main_thread = proto_core_threads->mutable_main_thread();
  proto_main_thread->set_name(static_info_wrapper_.executor_static_info.core_threads.main_thread.name);
  proto_main_thread->set_tid(static_info_wrapper_.executor_static_info.core_threads.main_thread.tid);
  proto_main_thread->set_thread_sched_policy(static_info_wrapper_.executor_static_info.core_threads.main_thread.thread_sched_policy);
  for (const auto& cpu : static_info_wrapper_.executor_static_info.core_threads.main_thread.bind_cpu) {
    proto_main_thread->add_bind_cpu(cpu);
  }
  auto* proto_guard_thread = proto_core_threads->mutable_guard_thread();
  proto_guard_thread->set_name(static_info_wrapper_.executor_static_info.core_threads.guard_thread.name);
  proto_guard_thread->set_tid(static_info_wrapper_.executor_static_info.core_threads.guard_thread.tid);
  proto_guard_thread->set_thread_sched_policy(static_info_wrapper_.executor_static_info.core_threads.guard_thread.thread_sched_policy);
  for (const auto& cpu : static_info_wrapper_.executor_static_info.core_threads.guard_thread.bind_cpu) {
    proto_guard_thread->add_bind_cpu(cpu);
  }

  // 日志信息
  auto* proto_log_static_info = rsp.mutable_static_info()->mutable_log_info();

  proto_log_static_info->set_core_lvl(static_info_wrapper_.log_static_info.core_level);
  proto_log_static_info->set_default_module_lvl(static_info_wrapper_.log_static_info.default_module_level);

  for (const auto& backend : static_info_wrapper_.log_static_info.backend_list) {
    proto_log_static_info->add_reliable_log_backend_list(backend.type);
  }

  for (const auto& backend_info : static_info_wrapper_.log_static_info.backend_list) {
    auto* proto_backend_info = proto_log_static_info->add_log_backend_info_list();
    proto_backend_info->set_type(backend_info.type);
    proto_backend_info->set_options(backend_info.options);
  }

  // module 信息
  auto* proto_static_info = rsp.mutable_static_info()->mutable_module_info();

  for (const auto& module : static_info_wrapper_.module_static_info.module_list) {
    auto* proto_module = proto_static_info->add_module_info_list();
    proto_module->set_name(module.name);
    proto_module->set_log_lvl(module.log_level);
    proto_module->set_pkg_path(module.pkg_path);
    proto_module->set_cfg_path(module.cfg_path);
    proto_module->set_version(module.version);
    proto_module->set_author(module.author);
    proto_module->set_description(module.description);
    proto_module->set_options(module.options);
  }
  // rpc 信息
  auto* proto_rpc_static_info = rsp.mutable_static_info()->mutable_rpc_info();

  for (const auto& filter : static_info_wrapper_.rpc_static_info.available_client_filters) {
    proto_rpc_static_info->add_available_client_filter_list(filter);
  }

  for (const auto& filter : static_info_wrapper_.rpc_static_info.available_server_filters) {
    proto_rpc_static_info->add_available_server_filter_list(filter);
  }

  for (const auto& backend : static_info_wrapper_.rpc_static_info.backend_list) {
    auto* proto_backend = proto_rpc_static_info->add_rpc_backend_info_list();
    proto_backend->set_type(backend.type);
    proto_backend->set_options(backend.options);
  }

  for (const auto& client : static_info_wrapper_.rpc_static_info.client_list) {
    auto* proto_client = proto_rpc_static_info->add_rpc_client_info_list();
    proto_client->set_func_name(client.func_name);
    proto_client->set_req_type(client.req_type);
    proto_client->set_rsp_type(client.rsp_type);
    proto_client->set_req_schema(client.req_schema);
    proto_client->set_rsp_schema(client.rsp_schema);
    for (const auto& module : client.modules) {
      proto_client->add_modules(module);
    }

    for (const auto& backend : client.backends) {
      proto_client->add_backends(std::string(backend));
    }

    for (const auto& filter : client.filters) {
      proto_client->add_filters(filter);
    }
  }

  // RPC服务端信息
  for (const auto& server : static_info_wrapper_.rpc_static_info.server_list) {
    auto* proto_server = proto_rpc_static_info->add_rpc_server_info_list();
    proto_server->set_func_name(server.func_name);
    proto_server->set_req_type(server.req_type);
    proto_server->set_rsp_type(server.rsp_type);
    proto_server->set_req_schema(server.req_schema);
    proto_server->set_rsp_schema(server.rsp_schema);

    for (const auto& module : server.modules) {
      proto_server->add_modules(module);
    }

    for (const auto& backend : server.backends) {
      proto_server->add_backends(std::string(backend));
    }

    for (const auto& filter : server.filters) {
      proto_server->add_filters(filter);
    }
  }

  // channel 信息
  auto* proto_channel_static_info = rsp.mutable_static_info()->mutable_channel_info();

  for (const auto& filter : static_info_wrapper_.channel_static_info.available_pub_filters) {
    proto_channel_static_info->add_available_pub_filter_list(filter);
  }

  for (const auto& filter : static_info_wrapper_.channel_static_info.available_sub_filters) {
    proto_channel_static_info->add_available_sub_filter_list(filter);
  }

  for (const auto& backend : static_info_wrapper_.channel_static_info.backend_list) {
    auto* proto_backend = proto_channel_static_info->add_channel_backend_info_list();
    proto_backend->set_type(backend.type);
    proto_backend->set_options(backend.options);
  }

  for (const auto& pub : static_info_wrapper_.channel_static_info.pub_list) {
    auto* proto_pub = proto_channel_static_info->add_channel_pub_info_list();
    proto_pub->set_topic(pub.topic);
    proto_pub->set_msg_type(pub.msg_type);

    proto_pub->set_schema(pub.schema);

    for (const auto& module : pub.modules) {
      proto_pub->add_modules(module);
    }

    for (const auto& backend : pub.backends) {
      proto_pub->add_backends(backend);
    }

    for (const auto& filter : pub.filters) {
      proto_pub->add_filters(filter);
    }
  }

  for (const auto& sub : static_info_wrapper_.channel_static_info.sub_list) {
    auto* proto_sub = proto_channel_static_info->add_channel_sub_info_list();
    proto_sub->set_topic(sub.topic);
    proto_sub->set_msg_type(sub.msg_type);

    proto_sub->set_schema(sub.schema);

    for (const auto& module : sub.modules) {
      proto_sub->add_modules(module);
    }

    for (const auto& backend : sub.backends) {
      proto_sub->add_backends(backend);
    }

    for (const auto& filter : sub.filters) {
      proto_sub->add_filters(filter);
    }
  }
}

void DataManager::SetDynamicReply(aimrt::protocols::viz_plugin::NodeInfoResponse& rsp) {
  auto* proto_dynamic_info = rsp.mutable_dynamic_info();

  std::shared_ptr<DynamicInfoWrapper> current_dynamic_info;
  {
    std::lock_guard<std::mutex> lock(dynamic_mtx_);
    current_dynamic_info = dynamic_info_wrapper_ptr_;
  }

  if (!current_dynamic_info) [[unlikely]] {
    return;
  }

  auto& node_dynamic_info = current_dynamic_info->node_dynamic_info;
  auto* proto_node_info = proto_dynamic_info->mutable_node_base_info();

  proto_node_info->set_online_time_s(node_dynamic_info.online_time_s);
  proto_node_info->set_memory_usage_kb(node_dynamic_info.memory_usage_kb);
  proto_node_info->set_memory_usage_percent(node_dynamic_info.memory_usage_percent);
  proto_node_info->set_thread_count(node_dynamic_info.thread_count);
  proto_node_info->set_cpu_usage_percent(node_dynamic_info.cpu_usage_percent);
  proto_node_info->set_scheduler_priority(node_dynamic_info.scheduler_priority);

  auto* proto_channel_info = proto_dynamic_info->mutable_channel_info();

  for (const auto& pub_info : current_dynamic_info->channel_dynamic_info.pub_dynamic_info_list) {
    auto* proto_pub = proto_channel_info->add_pub_dynamic_info_list();
    proto_pub->set_topic(pub_info.topic);
    proto_pub->set_msg_type(pub_info.msg_type);
    proto_pub->set_module(pub_info.module_name);
    proto_pub->set_frequency(pub_info.frequency);
    proto_pub->set_history_seq_num(pub_info.history_seq_num);
  }

  for (const auto& sub_info : current_dynamic_info->channel_dynamic_info.sub_dynamic_info_list) {
    auto* proto_sub = proto_channel_info->add_sub_dynamic_info_list();
    proto_sub->set_topic(sub_info.topic);
    proto_sub->set_msg_type(sub_info.msg_type);
    proto_sub->set_module(sub_info.module_name);
    proto_sub->set_frequency(sub_info.frequency);
    proto_sub->set_history_seq_num(sub_info.history_seq_num);
  }

  auto* proto_rpc_info = proto_dynamic_info->mutable_rpc_info();

  for (const auto& client_info : current_dynamic_info->rpc_dynamic_info.client_dynamic_info_list) {
    auto* proto_client = proto_rpc_info->add_client_dynamic_info_list();
    proto_client->set_func_name(client_info.func_name);
    proto_client->set_module(client_info.module);
    proto_client->set_seq_num(client_info.seq_num);
    proto_client->set_frequency(client_info.frequency);
    proto_client->set_latency_us(client_info.latency);
    proto_client->set_history_seq_num(client_info.history_seq_num);
    proto_client->set_error_count(client_info.error_count);
    proto_client->set_history_error_count(client_info.history_error_count);
    proto_client->set_error_rate(client_info.error_rate);
  }

  for (const auto& server_info : current_dynamic_info->rpc_dynamic_info.server_dynamic_info_list) {
    auto* proto_server = proto_rpc_info->add_server_dynamic_info_list();
    proto_server->set_func_name(server_info.func_name);
    proto_server->set_module(server_info.module);
    proto_server->set_seq_num(server_info.seq_num);
    proto_server->set_frequency(server_info.frequency);
    proto_server->set_latency_us(server_info.latency);
    proto_server->set_history_seq_num(server_info.history_seq_num);
    proto_server->set_error_count(server_info.error_count);
    proto_server->set_history_error_count(server_info.history_error_count);
    proto_server->set_error_rate(server_info.error_rate);
  }
}

void DataManager::DoUpdateDynamicInfo() {
  if (core_ptr_->GetState() != runtime::core::AimRTCore::State::kPostStart) {
    return;
  }
  auto new_data = std::make_shared<DynamicInfoWrapper>();
  process_info_manager_ptr_->DoUpdate(new_data->node_dynamic_info);

  auto cur_time = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();

  if (prev_time_stamp_ns_ == 0) [[unlikely]] {
    prev_time_stamp_ns_ = cur_time;
    return;
  }
  double duration = (cur_time - prev_time_stamp_ns_) / 1000000000.0;
  double inv_duration = 1.0 / duration;
  prev_time_stamp_ns_ = cur_time;

  if (duration <= 0) [[unlikely]] {
    return;
  }

  for (auto& [key, value] : channel_pub_stats_map_) {
    auto seq_num = value.sequence_num.load();
    auto dur_seq_num = seq_num - value.prev_sequence_num;
    new_data->channel_dynamic_info.pub_dynamic_info_list.emplace_back(ChannelDynamicInfoMeta{
        .topic = std::string(key.topic_name),
        .msg_type = std::string(key.msg_type),
        .module_name = std::string(key.module_name),
        .history_seq_num = seq_num,
        .frequency = dur_seq_num * inv_duration,
    });
    value.prev_sequence_num = seq_num;
  }
  for (auto& [key, value] : channel_sub_stats_map_) {
    auto seq_num = value.sequence_num.load();
    auto dur_seq_num = seq_num - value.prev_sequence_num;
    new_data->channel_dynamic_info.sub_dynamic_info_list.emplace_back(ChannelDynamicInfoMeta{
        .topic = std::string(key.topic_name),
        .msg_type = std::string(key.msg_type),
        .module_name = std::string(key.module_name),
        .history_seq_num = seq_num,
        .frequency = dur_seq_num * inv_duration,
    });
    value.prev_sequence_num = seq_num;
  }

  for (auto& [key, value] : rpc_client_stats_map_) {
    auto seq_num = value.sequence_num.load();
    auto error_count = value.error_count.load();
    auto dur_seq_num = seq_num - value.prev_sequence_num;
    auto dur_error_count = error_count - value.prev_error_count;

    new_data->rpc_dynamic_info.client_dynamic_info_list.emplace_back(RpcDynamicInfoMeta{
        .func_name = std::string(key.func_name),
        .module = std::string(key.module_name),
        .frequency = dur_seq_num * inv_duration,
        .seq_num = dur_seq_num,
        .history_seq_num = seq_num,
        .history_error_count = error_count,
        .error_count = dur_error_count,
        .error_rate = dur_seq_num > 0 ? static_cast<double>(dur_error_count) / static_cast<double>(dur_seq_num) : 0,
        .latency = value.latency_us.load() * inv_duration,
    });
    value.latency_us.store(0);
    value.prev_error_count = error_count;
    value.prev_sequence_num = seq_num;
  }

  for (auto& [key, value] : rpc_server_stats_map_) {
    auto seq_num = value.sequence_num.load();
    auto error_count = value.error_count.load();
    auto dur_seq_num = seq_num - value.prev_sequence_num;
    auto dur_error_count = error_count - value.prev_error_count;

    new_data->rpc_dynamic_info.server_dynamic_info_list.emplace_back(RpcDynamicInfoMeta{
        .func_name = std::string(key.func_name),
        .module = std::string(key.module_name),
        .frequency = dur_seq_num * inv_duration,
        .seq_num = dur_seq_num,
        .history_seq_num = seq_num,
        .history_error_count = error_count,
        .error_count = dur_error_count,
        .error_rate = dur_seq_num > 0 ? static_cast<double>(dur_error_count) / static_cast<double>(dur_seq_num) : 0,
        .latency = dur_seq_num > 0 ? static_cast<double>(value.latency_us.load()) / static_cast<double>(dur_seq_num) : 0,
    });
    value.latency_us.store(0);
    value.prev_error_count = error_count;
    value.prev_sequence_num = seq_num;
  }

  {
    std::unique_lock<std::mutex> lck(dynamic_mtx_);
    dynamic_info_wrapper_ptr_ = new_data;
  }
}

}  // namespace aimrt::plugins::viz_plugin