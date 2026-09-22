import { type Component, type ComputedRef, type Ref } from 'vue';
// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面model定义
export type PageModel = {
  nodeBaseStaticInfo: Ref<NodeBaseStaticInfo | null>;
  nodeBaseDynamicInfo: Ref<NodeBaseDynamicInfo | null>;
  configurationStaticInfo: Ref<ConfigurationStaticInfo | null>;
  logStaticInfo: Ref<LogStaticInfo | null>;
  pluginStaticInfo: Ref<PluginStaticInfo | null>;
  executorStaticInfo: Ref<ExecutorStaticInfo | null>;
  moduleStaticInfo: Ref<ModuleStaticInfo | null>;
  rpcStaticInfo: Ref<RpcStaticInfo | null>;
  rpcDynamicInfo: Ref<RpcDynamicInfo | null>;
  channelStaticInfo: Ref<ChannelStaticInfo | null>;
  channelDynamicInfo: Ref<ChannelDynamicInfo | null>;

  strat_time_format: ComputedRef<string>;
  online_time_format: ComputedRef<string>;
  memory_usage_format: ComputedRef<string>;
  cpu_usage_format: ComputedRef<string>;

  rpcServerInfoList: ComputedRef<RpcMergeInfoMeta[]>;
  rpcClientInfoList: ComputedRef<RpcMergeInfoMeta[]>;
  channelPubInfoList: ComputedRef<ChannelMergeInfoMeta[]>;
  channelSubInfoList: ComputedRef<ChannelMergeInfoMeta[]>;
};

// 节点信息
export interface NodeBaseStaticInfo {
  node_name: string;
  soc: string;
  pid: number;
  aimrt_version: string;
  start_time_stamp_ns: number;
  executable_path: string;
  cfg_file_path: string;
  server_num: number;
  client_num: number;
  sub_num: number;
  pub_num: number;
}

export interface NodeBaseDynamicInfo {
  node_name: string;
  online_time_s: number;
  memory_usage_kb: number;
  memory_usage_percent: number;
  thread_count: number;
  cpu_usage_percent: number;
  scheduler_priority: number;
}

// 配置信息
export interface ConfigurationStaticInfo {
  orin_cfg_file_id: number;
  parased_cfg_file_id: number;
}

export interface ConfigurationDynamicInfo {}

// 插件信息
export interface PluginInfoMeta {
  name: string;
  path: string;
  options_id: number;
}

export interface PluginStaticInfo {
  plugin_info_list: PluginInfoMeta[];
}

export interface PluginDynamicInfo {}

// 执行器信息
export interface ThreadInfoMeta {
  tid: number;
  name: string;
  thread_sched_policy: string;
  bind_cpu: number[];
}

export interface AimrtCoreThreadInfoMeta {
  main_thread: ThreadInfoMeta;
  guard_thread: ThreadInfoMeta;
}

export interface ExecutorInfoMeta {
  name: string;
  type: string;
  thread_safe: boolean;
  support_time_schedule: boolean;
  options_id: number;
}

export interface ExecutorStaticInfo {
  core_threads: AimrtCoreThreadInfoMeta;
  available_executor_list: string[];
  executor_info_list: ExecutorInfoMeta[];
}

export interface ExecutorDynamicInfo {}

// 日志信息
export interface LogBackendInfoMeta {
  type: string;
  options_id: number;
}

export interface LogStaticInfo {
  core_lvl: string;
  default_module_lvl: string;
  reliable_log_backend_list: string[];
  log_backend_info_list: LogBackendInfoMeta[];
}

export interface LogDynamicInfo {}

// 模块信息
export interface ModuleInfoMeta {
  name: string;
  log_lvl: string;
  pkg_path: string;
  cfg_path: string;
}

export interface ModuleStaticInfo {
  module_info_list: ModuleInfoMeta[];
}

export interface ModuleDynamicInfo {}

// RPC信息
export interface RpcBackendInfoMeta {
  type: string;
  options_id: number;
}

export interface RpcClientInfoMeta {
  func_name: string;
  modules: string[];
  backends: string[];
  filters: string[];
}

export interface RpcServerInfoMeta {
  func_name: string;
  modules: string[];
  backends: string[];
  filters: string[];
}

export interface RpcStaticInfo {
  available_client_filter_list: string[];
  available_server_filter_list: string[];
  rpc_backend_info_list: RpcBackendInfoMeta[];
  rpc_client_info_list: RpcClientInfoMeta[];
  rpc_server_info_list: RpcServerInfoMeta[];
}

export interface RpcConnectedToMeta {
  func_name: string;
  node_name: string;
  module_name: string;
  pid: number;
  soc: string;
}

export interface RpcDynamicInfo {
  client_dynamic_info_list: RpcConnectedToMeta[];
  server_dynamic_info_list: RpcConnectedToMeta[];
}

export interface ChannelBackendInfoMeta {
  type: string;
  options_id: number;
}

export interface ChannelPubInfoMeta {
  topic: string;
  msg_type: string;
  modules: string[];
  backends: string[];
  filters: string[];
}

export interface ChannelSubInfoMeta {
  topic: string;
  msg_type: string;
  modules: string[];
  backends: string[];
  filters: string[];
}

export interface ChannelStaticInfo {
  available_pub_filter_list: string[];
  available_sub_filter_list: string[];
  channel_backend_info_list: ChannelBackendInfoMeta[];
  channel_pub_info_list: ChannelPubInfoMeta[];
  channel_sub_info_list: ChannelSubInfoMeta[];
}

export interface ChannelConnectedToMeta {
  topic: string;
  msg_type: string;
  node_name: string;
  module_name: string;
  pid: number;
  soc: string;
}

export interface ChannelDynamicInfo {
  sub_dynamic_info_list: ChannelConnectedToMeta[];
  pub_dynamic_info_list: ChannelConnectedToMeta[];
}

export interface RpcMergeInfoMeta {
  func_name: string;
  modules: string[];
  backends: string[];
  filters: string[];
  connected_to_node: string[];
  connected_to_module: string[];
}

export interface ChannelMergeInfoMeta {
  topic: string;
  msg_type: string;
  modules: string[];
  backends: string[];
  filters: string[];
  connected_to_node: string[];
  connected_to_module: string[];
}
