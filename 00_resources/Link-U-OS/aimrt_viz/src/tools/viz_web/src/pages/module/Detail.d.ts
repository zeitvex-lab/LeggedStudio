import { type Component, type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面model定义
export type PageModel = {
  moduleBaseInfo: Ref<ModuleBaseStaticInfo | null>;
  rpcClinetInfoList: Ref<ModuleRpcStaticInfo[]>;
  rpcServerInfoList: Ref<ModuleRpcStaticInfo[]>;
  chnPubInfoList: Ref<ModuleChannelStaticInfo[]>;
  chnSubInfoList: Ref<ModuleChannelStaticInfo[]>;

  rpcClinetDynamicInfoList: Ref<ModuleRpcDynamicInfo[]>;
  rpcServerDynamicInfoList: Ref<ModuleRpcDynamicInfo[]>;
  chnPubDynamicInfoList: Ref<ModuleChannelDynamicInfo[]>;
  chnSubDynamicInfoList: Ref<ModuleChannelDynamicInfo[]>;

  rpcServerMergedInfoList: ComputedRef<RpcMergeInfoMeta[]>;
  rpcClientMergedInfoList: ComputedRef<RpcMergeInfoMeta[]>;
  channelPubMergedInfoList: ComputedRef<ChannelMergeInfoMeta[]>;
  channelSubMergedInfoList: ComputedRef<ChannelMergeInfoMeta[]>;
};

export interface ModuleDetailInfo {
  module_detail_static_info: ModuleDetailStaticInfo;
  module_detail_dynamic_info: ModuleDetailDynamicInfo;
}

export interface ModuleDetailStaticInfo {
  base_info: ModuleBaseStaticInfo;
  server_info: ModuleRpcStaticInfo[];
  client_info: ModuleRpcStaticInfo[];
  sub_info: ModuleChannelStaticInfo[];
  pub_info: ModuleChannelStaticInfo[];
}

export interface ModuleDetailDynamicInfo {
  base_info: ModuleBaseDynamicInfo;
  server_info: ModuleRpcDynamicInfo[];
  client_info: ModuleRpcDynamicInfo[];
  sub_info: ModuleChannelDynamicInfo[];
  pub_info: ModuleChannelDynamicInfo[];
}

export interface ModuleBaseStaticInfo {
  name: string;
  pkg_path: string;
  log_lvl: string;
  author: string;
  version: string;
  description: string;
  cfg_path: string;
  options_id: number;
}

export interface ModuleBaseDynamicInfo {}
export interface ModuleRpcStaticInfo {
  func_name: string;
  backend: string[];
  filters: string[];
}
export interface ModuleRpcDynamicInfo {
  func_name: string;
  conneced_to: ConnectedTo[];
}
export interface ModuleChannelStaticInfo {
  topic: string;
  msg_type: string;
  backend: string[];
  filters: string[];
}
export interface ModuleChannelDynamicInfo {
  topic: string;
  msg_type: string;
  connected_to: ConnectedTo[];
}

export interface ConnectedTo {
  node_name: string;
  module_name: string;
}

export interface RpcMergeInfoMeta {
  func_name: string;
  backend: string[];
  filters: string[];
  connected_to_node: string[];
  connected_to_module: string[];
}

export interface ChannelMergeInfoMeta {
  topic: string;
  msg_type: string;
  backend: string[];
  filters: string[];
  connected_to_node: string[];
  connected_to_module: string[];
}
