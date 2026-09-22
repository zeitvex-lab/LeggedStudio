// 系统信息
export interface SystemStaticInfoResponse {
  name: string;
  aimrt_viz_version: string;
  attributes: Record<string, string>[];
}

export interface SystemDynamicInfoResponse {}

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
  online_time_s: number;
  memory_usage_kb: number;
  memory_usage_percent: number;
  thread_count: number;
  cpu_usage_percent: number;
  scheduler_priority: number;
}

// 配置信息
export interface ConfigurationStaticInfo {
  orin_cfg_file: string;
  parased_cfg_file: string;
}

export interface ConfigurationDynamicInfo {}

// 插件信息
export interface PluginInfoMeta {
  name: string;
  path: string;
  options: string;
}

export interface PluginStaticInfo {
  plugin_info_list: PluginInfoMeta[];
}

export interface PluginDynamicInfo {}

// 执行器信息
export interface ThreadInfoMeta {
  tid: number;
  name: string;
  options: string;
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
  options: string;
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
  options: string;
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
  options: string;
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

export interface RpcDynamicInfoMeta {
  func_name: string;
  module: string;
  seqence_num: number;
  payload_size_b: number;
  send_time_stamp_ns: number;
  sum_latency_ms: number;
  dissmiss_num: number;
}

export interface RpcDynamicInfo {
  client_dynamic_info_list: RpcDynamicInfoMeta[];
  server_dynamic_info_list: RpcDynamicInfoMeta[];
}

export interface ChannelBackendInfoMeta {
  type: string;
  options: string;
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

export interface ChannelDynamicInfoMeta {
  topic: string;
  msg_type: string;
  module: string;
  seqence_num: number;
  payload_size_b: number;
  send_time_stamp_ns: number;
}

export interface ChannelDynamicInfo {
  sub_dynamic_info_list: ChannelDynamicInfoMeta[];
  pub_dynamic_info_list: ChannelDynamicInfoMeta[];
}

// 系统信息响应-----------------------------------------------------------
export interface SystemInfoResponse {
  static_info: SystemStaticInfoResponse;
  dynamic_info: SystemDynamicInfoResponse;
}

export interface NodeBaseStaticInfoResponse {
  node_base_static_info_list: NodeBaseStaticInfo[];
}

export interface NodeBaseDynamicInfoResponse {
  node_base_dynamic_info_list: NodeBaseDynamicInfo[];
}

export interface NodeBaseInfoResponse {
  node_base_static_info_list: NodeBaseStaticInfoResponse;
  node_base_dynamic_info_list: NodeBaseDynamicInfoResponse;
}

export interface NodeDetailInfoRequest {
  soc: string;
  pid: number;
}
