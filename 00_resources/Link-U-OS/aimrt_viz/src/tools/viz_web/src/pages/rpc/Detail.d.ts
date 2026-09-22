import { type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面model定义
export type PageModel = {
  rpcDetailInfo: Ref<RpcDetailInfo | null>;
  client_error_rate: ComputedRef<string>;
  server_error_rate: ComputedRef<string>;
};

export interface RpcDetailInfo {
  rpc_detail_static_info: RpcDetailStaticInfo;
  rpc_detail_dynamic_info: RpcDetailDynamicInfo;
}

export interface RpcDetailStaticInfo {
  base_info: RpcBaseInfo;
}

export interface RpcDetailDynamicInfo {
  client_info: RpcClientInfo;
  server_info: RpcServerInfo;
  endpoint_info: RpcEndpointInfo[];
}

export interface RpcBaseInfo {
  func_name: string;
  request_type: string;
  response_type: string;
  backend_name: string[];
  filter_name: string[];
  request_schema_id: number;
  response_schema_id: number;
}

export interface RpcClientInfo {
  current_status: RpcCurrentStatusInfo;
  history_stats: RpcHistoryStatsInfo;
  module_infos: RpcModuleStatusInfo[];
}

export interface RpcServerInfo {
  current_status: RpcCurrentStatusInfo;
  history_stats: RpcHistoryStatsInfo;
  module_infos: RpcModuleStatusInfo[];
}

export interface RpcEndpointInfo {
  backend_name: string;
  client_endpoints: EndpointInfo[];
  server_endpoints: EndpointInfo[];
}
export interface RpcCurrentStatusInfo {
  qps: number;
  error_rate: number;
}

export interface RpcHistoryStatsInfo {
  seq_num: number;
  error_count: number;
}

export interface RpcModuleStatusInfo {
  node_name: string;
  module_name: string;
  backend_name: string;
  filter_name: string[];
  qps: number;
}

export interface EndpointInfo {
  node_name: string;
  module_name: string;
  filter_name: string[];
}
