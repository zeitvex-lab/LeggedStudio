// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>
namespace aimrt_viz::viz_module {

// channel Meta
struct ChannelMetaKey {
  std::string topic_name;
  std::string msg_type;
  bool operator==(const ChannelMetaKey& other) const {
    return topic_name == other.topic_name && msg_type == other.msg_type;
  }
  struct Hash {
    size_t operator()(const ChannelMetaKey& key) const {
      size_t hash = 0;
      hash ^= std::hash<std::string>()(key.topic_name);
      hash ^= std::hash<std::string>()(key.msg_type);
      return hash;
    }
  };
};
// Rpc Meta
struct RpcMetaKey {
  std::string func_name;
  bool operator==(const RpcMetaKey& other) const {
    return func_name == other.func_name;
  }
  struct Hash {
    size_t operator()(const RpcMetaKey& key) const {
      size_t hash = 0;
      hash ^= std::hash<std::string>()(key.func_name);
      return hash;
    }
  };
};

// SystemInfo ---------------------------------------------------------
struct SystemInfo {
  std::string system_name;
  std::string aimrt_viz_version;
  std::vector<std::unordered_map<std::string, std::string>> attributes;
};

// NodeBaseInfo ---------------------------------------------------------
struct NodeBaseStaticInfo {
  enum class Status {
    OFFLINE = 0,
    ONLINE = 1,
  };
  Status status = Status::OFFLINE;
  std::string node_name;
  std::string soc;
  uint64_t pid;
  std::string aimrt_version;
  uint64_t start_time_stamp_ns;
  std::string executable_path;
  std::string cfg_file_path;

  // protocol does not have this
  uint32_t client_num = 0;
  uint32_t server_num = 0;
  uint32_t publisher_num = 0;
  uint32_t subscriber_num = 0;
};

struct NodeBaseDynamicInfo {
  std::string node_name;
  uint64_t online_time_s = 0;
  uint64_t memory_usage_kb{0};
  float memory_usage_percent{0.0F};
  uint64_t thread_count{0};
  float cpu_usage_percent{0.0F};
  int32_t scheduler_priority{0};
};

// Configuration ---------------------------------------------------------
struct ConfigurationStaticInfo {
  uint32_t orin_cfg_file_id;
  uint32_t parased_cfg_file_id;
};

struct ConfigurationDynamicInfo {
};

// Plugin
struct PluginInfoMeta {
  std::string name;
  std::string path;
  uint32_t options_id;
};

struct PluginStaticInfo {
  std::vector<PluginInfoMeta> plugin_info_list;
};

struct PluginDynamicInfo {
};

// Executor ---------------------------------------------------------

struct AimrtCoreThreadInfoMeta {
  struct ThreadInfoMeta {
    uint64_t tid = 0;
    std::string name;
    std::string thread_sched_policy;
    std::vector<uint32_t> bind_cpu;
  };
  ThreadInfoMeta main_thread;
  ThreadInfoMeta guard_thread;
};

struct ExecutorInfoMeta {
  std::string name;
  std::string type;
  bool thread_safe = false;
  bool support_time_schedule = false;
  uint32_t options_id;
};

struct ExecutorStaticInfo {
  AimrtCoreThreadInfoMeta core_threads;
  std::vector<std::string> available_executor_list;
  std::vector<ExecutorInfoMeta> executor_info_list;
};

struct ExecutorDynamicInfo {
};

// Log ---------------------------------------------------------
struct LogBackendInfoMeta {
  std::string type;
  uint32_t options_id;
};

struct LogStaticInfo {
  std::string core_lvl;
  std::string default_module_lvl;
  std::vector<std::string> reliable_log_backend_list;
  std::vector<LogBackendInfoMeta> log_backend_info_list;
};

struct LogDynamicInfo {
};

// Module ---------------------------------------------------------
struct ModuleInfoMeta {
  std::string name;
  std::string log_lvl;
  std::string pkg_path;
  std::string cfg_path;
  std::string version;
  std::string author;
  std::string description;
  uint32_t options_id;
};

struct ModuleStaticInfo {
  std::vector<ModuleInfoMeta> module_info_list;
};

struct ModuleDynamicInfo {
};

// Rpc ---------------------------------------------------------
struct RpcBackendInfoMeta {
  std::string type;
  uint32_t options_id;
};

struct RpcClientInfoMeta {
  std::string func_name;
  std::vector<std::string> modules;
  std::vector<std::string> backends;
  std::vector<std::string> filters;
};

struct RpcServerInfoMeta {
  std::string func_name;
  std::vector<std::string> modules;
  std::vector<std::string> backends;
  std::vector<std::string> filters;
};

struct RpcStaticInfo {
  std::vector<std::string> available_client_filter_list;
  std::vector<std::string> available_server_filter_list;
  std::vector<RpcBackendInfoMeta> rpc_backend_info_list;
  std::vector<RpcClientInfoMeta> rpc_client_info_list;
  std::vector<RpcServerInfoMeta> rpc_server_info_list;
};

struct RpcDynamicInfoMeta {
  uint64_t seq_num = 0;
  uint64_t history_seq_num = 0;
  uint64_t history_error_count = 0;
  uint64_t error_count = 0;
  double error_rate = 0;
  double frequency = 0;
  double latency_us = 0;
  std::set<std::string> backends;
  std::set<std::string> filters;
  // protocol does not have this
};

struct RpcDynamicInfoWrapper {
  std::unordered_map<std::string, RpcDynamicInfoMeta> rpc_dynamic_info_map;
  std::vector<std::string> connected_clients;
  std::vector<std::string> connected_servers;
};

struct RpcDynamicInfo {
  std::unordered_map<RpcMetaKey, RpcDynamicInfoWrapper, RpcMetaKey::Hash> server_dynamic_info_map;
  std::unordered_map<RpcMetaKey, RpcDynamicInfoWrapper, RpcMetaKey::Hash> client_dynamic_info_map;
};

// Channel ---------------------------------------------------------
struct ChannelBackendInfoMeta {
  std::string type;
  uint32_t options_id;
};

struct ChannelPubInfoMeta {
  std::string topic;
  std::string msg_type;
  std::vector<std::string> modules;
  std::vector<std::string> backends;
  std::vector<std::string> filters;
};

struct ChannelSubInfoMeta {
  std::string topic;
  std::string msg_type;
  std::vector<std::string> modules;
  std::vector<std::string> backends;
  std::vector<std::string> filters;
};

struct ChannelStaticInfo {
  std::vector<std::string> available_pub_filter_list;
  std::vector<std::string> available_sub_filter_list;
  std::vector<ChannelBackendInfoMeta> channel_backend_info_list;
  std::vector<ChannelPubInfoMeta> channel_pub_info_list;
  std::vector<ChannelSubInfoMeta> channel_sub_info_list;
};

struct ChannelDynamicMeta {
  double frequency = 0;
  uint64_t history_seq_num = 0;
  std::set<std::string> backends;
  std::set<std::string> filters;
};

struct StaticInfo {
  NodeBaseStaticInfo node_base_info;
  ConfigurationStaticInfo configuration_info;
  PluginStaticInfo plugin_info;
  ExecutorStaticInfo executor_info;
  LogStaticInfo log_info;
  ModuleStaticInfo module_info;
  RpcStaticInfo rpc_info;
  ChannelStaticInfo channel_info;
  std::vector<uint32_t> resource_ids;
};
struct DynamicInfo {
  NodeBaseDynamicInfo node_base_info;
  ConfigurationDynamicInfo configuration_info;
  PluginDynamicInfo plugin_info;
  ExecutorDynamicInfo executor_info;
  LogDynamicInfo log_info;
  ModuleDynamicInfo module_info;
};

struct NodeModeKey {
  std::string node_name;
  std::string mode;
  std::string soc;
  uint64_t pid;
  bool operator==(const NodeModeKey& other) const {
    return node_name == other.node_name && mode == other.mode && soc == other.soc && pid == other.pid;
  }
  struct Hash {
    size_t operator()(const NodeModeKey& key) const {
      size_t hash = 0;
      hash ^= std::hash<std::string>()(key.node_name);
      hash ^= std::hash<std::string>()(key.mode);
      hash ^= std::hash<std::string>()(key.soc);
      hash ^= std::hash<uint64_t>()(key.pid);
      return hash;
    }
  };
};

}  // namespace aimrt_viz::viz_module
