// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once
#include <sys/types.h>
#include <atomic>
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace aimrt::plugins::viz_plugin {

struct TopicMetaKey {
  std::string_view topic_name;   // 主题名称
  std::string_view msg_type;     // 消息类型
  std::string_view module_name;  // 模块名称
  std::string_view pkg_path;     // 包路径

  bool operator==(const TopicMetaKey& other) const {
    return topic_name == other.topic_name && msg_type == other.msg_type && module_name == other.module_name;
  }

  struct Hash {
    using is_transparent = void;

    template <typename T>
    std::size_t operator()(const T& k) const {
      return std::hash<std::string_view>{}(k.topic_name) ^
             (std::hash<std::string_view>{}(k.msg_type) << 1) ^
             (std::hash<std::string_view>{}(k.module_name) << 2) ^
             (std::hash<std::string_view>{}(k.pkg_path) << 3);
    }
  };
};

struct RpcMetaKey {
  std::string_view func_name;
  std::string_view module_name;
  bool operator==(const RpcMetaKey& other) const {
    return func_name == other.func_name && module_name == other.module_name;
  }

  struct Hash {
    using is_transparent = void;
    template <typename T>
    std::size_t operator()(const T& k) const {
      return std::hash<std::string_view>{}(k.func_name) ^
             (std::hash<std::string_view>{}(k.module_name) << 1);
    }
  };
};

// 节点基础信息相关结构体
struct NodeStaticInfo {
  std::string node_name;            // 节点名称
  std::string soc;                  // SOC类型
  uint64_t pid{0};                  // 进程ID
  std::string aimrt_version;        // AIMRT版本
  uint64_t start_time_stamp_ns{0};  // 启动时间戳(纳秒)
  std::string executable_path;      // 可执行文件路径
  std::string cfg_file_path;        // 配置文件路径
  uint32_t client_num{0};           // 客户端数量
  uint32_t server_num{0};           // 服务器数量
  uint32_t publisher_num{0};        // 发布者数量
  uint32_t subscriber_num{0};       // 订阅者数量
};

struct NodeDynamicInfo {
  uint64_t online_time_s{0};         // 在线时间(秒)
  uint64_t memory_usage_kb{0};       // 内存使用量(KB)
  float memory_usage_percent{0.0f};  // 内存使用百分比
  uint64_t thread_count{0};          // 线程数量
  float cpu_usage_percent{0.0f};     // CPU使用百分比
  int32_t scheduler_priority{0};     // 调度优先级
};

struct ConfigurationStaticInfo {
  std::string original_cfg_file;  // 原始配置文件
  std::string parsed_cfg_file;    // 解析后的配置文件
};

struct ConfigurationDynamicInfo {
  std::string last_update_time;  // 最后更新时间
};

// 插件信息相关结构体
struct PluginInfoMeta {
  std::string name;  // 插件名称
  std::string path;  // 插件路径
  std::string options;
};

struct PluginStaticInfo {
  std::vector<PluginInfoMeta> plugin_list;  // 插件列表
};

struct PluginDynamicInfo {
  std::vector<std::string> active_plugins;    // 当前活跃的插件
  std::vector<std::string> disabled_plugins;  // 已禁用的插件
};

// 核心线程信息
struct AimrtCoreThreadInfoMeta {
  struct ThreadInfoMeta {
    uint64_t tid;                     // 线程ID
    std::string name;                 // 线程名称
    std::string thread_sched_policy;  // 线程调度策略
    std::vector<uint32_t> bind_cpu;   // 绑定的CPU
  };
  ThreadInfoMeta main_thread;   // 主线程
  ThreadInfoMeta guard_thread;  // 守护线程
};

// 执行器信息相关结构体
struct ExecutorInfoMeta {
  std::string name;                   // 执行器名称
  std::string type;                   // 执行器类型
  bool thread_safe{false};            // 是否线程安全
  bool support_time_schedule{false};  // 是否支持时间调度
  std::string options;                // 执行器选项
};

struct ExecutorStaticInfo {
  AimrtCoreThreadInfoMeta core_threads;          // 核心线程信息
  std::vector<std::string> available_executors;  // 可用执行器列表
  std::vector<ExecutorInfoMeta> executor_list;   // 执行器列表
};

struct ExecutorDynamicInfo {
  std::vector<std::string> active_executors;   // 活跃的执行器
  std::map<std::string, float> executor_load;  // 执行器负载
};

// 日志信息相关结构体
struct LogBackendInfoMeta {
  std::string type;     // 日志后端类型
  std::string options;  // 日志后端选项
};

struct LogStaticInfo {
  std::string core_level;                        // 核心日志级别
  std::string default_module_level;              // 默认模块日志级别
  std::vector<std::string> reliable_backends;    // 可靠的日志后端列表
  std::vector<LogBackendInfoMeta> backend_list;  // 日志后端列表
};

struct LogDynamicInfo {
  std::map<std::string, std::string> current_levels;  // 当前各模块日志级别
};

// 模块信息相关结构体
struct ModuleInfoMeta {
  std::string name;         // 模块名称
  std::string log_level;    // 日志级别
  std::string pkg_path;     // 包路径
  std::string cfg_path;     // 配置路径
  std::string version;      // 模块版本
  std::string author;       // 作者
  std::string description;  // 描述
  std::string options;      // 模块选项
};

struct ModuleStaticInfo {
  std::vector<ModuleInfoMeta> module_list;  // 模块列表
};

struct ModuleDynamicInfo {
  std::vector<std::string> active_modules;    // 活跃的模块
  std::map<std::string, bool> module_status;  // 模块状态
};

// RPC信息相关结构体
struct RpcBackendInfoMeta {
  std::string type;     // RPC后端类型
  std::string options;  // RPC后端选项
};

struct RpcClientInfoMeta {
  std::string func_name;              // 函数名称
  std::string req_type;               // 请求类型
  std::string rsp_type;               // 响应类型
  std::string req_schema;             // 请求类型
  std::string rsp_schema;             // 响应类型
  std::vector<std::string> modules;   // 关联模块
  std::vector<std::string> backends;  // 后端列表
  std::vector<std::string> filters;   // 过滤器列表
};

struct RpcServerInfoMeta {
  std::string func_name;              // 函数名称
  std::string req_type;               // 请求类型
  std::string rsp_type;               // 响应类型
  std::string req_schema;             // 请求类型
  std::string rsp_schema;             // 响应类型
  std::vector<std::string> modules;   // 关联模块
  std::vector<std::string> backends;  // 后端列表
  std::vector<std::string> filters;   // 过滤器列表
};

struct RpcStaticInfo {
  std::vector<std::string> available_client_filters;  // 可用客户端过滤器
  std::vector<std::string> available_server_filters;  // 可用服务端过滤器
  std::vector<RpcBackendInfoMeta> backend_list;       // RPC后端列表
  std::vector<RpcClientInfoMeta> client_list;         // RPC客户端列表
  std::vector<RpcServerInfoMeta> server_list;         // RPC服务端列表
};

struct RpcDynamicInfoMeta {
  std::string func_name;
  std::string module;
  double frequency;
  uint64_t seq_num{0};              // 序列号
  uint64_t history_seq_num{0};      // 历史序列号
  uint64_t history_error_count{0};  // 历史错误计数
  uint64_t error_count{0};          // 错误计数
  double error_rate;                // 错误率
  double latency;                   // 延迟(us)
};

struct RpcDynamicRecord {
  std::atomic<uint64_t> latency_us{0};    // 延迟(微秒)
  uint64_t prev_sequence_num{0};          // 之前记录的序列号
  std::atomic<uint64_t> sequence_num{0};  // 序列号
  uint64_t prev_error_count{0};           // 之前记录的错误计数
  std::atomic<uint64_t> error_count{0};   // 错误计数
};

struct RpcDynamicInfo {
  std::vector<RpcDynamicInfoMeta> client_dynamic_info_list;
  std::vector<RpcDynamicInfoMeta> server_dynamic_info_list;
};

// 通道信息相关结构体
struct ChannelBackendInfoMeta {
  std::string type;     // 通道后端类型
  std::string options;  // 通道后端选项
};

struct ChannelPubInfoMeta {
  std::string topic;                  // 主题
  std::string msg_type;               // 消息类型
  std::string schema;                 // 消息类型
  std::vector<std::string> modules;   // 关联模块
  std::vector<std::string> backends;  // 后端列表
  std::vector<std::string> filters;   // 过滤器列表
};

struct ChannelSubInfoMeta {
  std::string topic;                  // 主题
  std::string msg_type;               // 消息类型
  std::string schema;                 // 消息类型
  std::vector<std::string> modules;   // 关联模块
  std::vector<std::string> backends;  // 后端列表
  std::vector<std::string> filters;   // 过滤器列表
};

struct ChannelStaticInfo {
  std::vector<std::string> available_pub_filters;    // 可用发布过滤器
  std::vector<std::string> available_sub_filters;    // 可用订阅过滤器
  std::vector<ChannelBackendInfoMeta> backend_list;  // 通道后端列表

  std::vector<ChannelPubInfoMeta> pub_list;  // 发布者列表
  std::vector<ChannelSubInfoMeta> sub_list;  // 订阅者列表
};

struct ChannelDynamicInfoMeta {
  std::string topic;
  std::string msg_type;
  std::string module_name;
  uint64_t history_seq_num{0};  // 历史序列号
  double frequency = 0;
};

struct ChannelDynamicRecord {
  uint64_t prev_sequence_num{0};          // 最后一次更新序列号
  std::atomic<uint64_t> sequence_num{0};  // 序列号
};

struct ChannelDynamicInfo {
  std::vector<ChannelDynamicInfoMeta> pub_dynamic_info_list;
  std::vector<ChannelDynamicInfoMeta> sub_dynamic_info_list;
};

struct StaticInfoWrapper {
  NodeStaticInfo node_static_info;
  LogStaticInfo log_static_info;
  ConfigurationStaticInfo cfg_static_info;
  ExecutorStaticInfo executor_static_info;
  PluginStaticInfo plugin_static_info;
  ModuleStaticInfo module_static_info;
  ChannelStaticInfo channel_static_info;
  RpcStaticInfo rpc_static_info;
};

struct DynamicInfoWrapper {
  NodeDynamicInfo node_dynamic_info;
  LogDynamicInfo log_dynamic_info;
  ConfigurationDynamicInfo cfg_dynamic_info;
  ExecutorDynamicInfo executor_dynamic_info;
  PluginDynamicInfo plugin_dynamic_info;
  ModuleDynamicInfo module_dynamic_info;
  ChannelDynamicInfo channel_dynamic_info;
  RpcDynamicInfo rpc_dynamic_info;
};

};  // namespace aimrt::plugins::viz_plugin