import { type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面model定义
export type PageModel = {
  chnDetailInfo: Ref<ChnDetailInfo | null>;
};

export interface ChnDetailInfo {
  channel_detail_static_info: ChnDetailStaticInfo;
  channel_detail_dynamic_info: ChnDetailDynamicInfo;
}

export interface ChnDetailStaticInfo {
  base_info: ChnBaseInfo;
}

export interface ChnDetailDynamicInfo {
  sub_info: ChannelSubInfo;
  pub_info: ChannelPubInfo;
  endpoint_info: ChannelEndpointInfo[];
}

export interface ChnBaseInfo {
  topic_name: string;
  msg_type: string;
  backend_name: string[];
  filter_name: string[];
  schema_id: number;
}

export interface ChannelSubInfo {
  current_status: ChannelCurrentStatusInfo;
  history_stats: ChannelHistoryStatusInfo;
  module_infos: ChannelModuleStatusInfo[];
}

export interface ChannelPubInfo {
  current_status: ChannelCurrentStatusInfo;
  history_stats: ChannelHistoryStatusInfo;
  module_infos: ChannelModuleStatusInfo[];
}

export interface ChannelEndpointInfo {
  backend_name: string;
  sub_endpoints: EndpointInfo[];
  pub_endpoints: EndpointInfo[];
}
export interface ChannelCurrentStatusInfo {
  frequency: number;
}

export interface ChannelHistoryStatusInfo {
  seq_num: number;
}

export interface ChannelModuleStatusInfo {
  node_name: string;
  module_name: string;
  backend_name: string;
  filter_name: string[];
  frequency: number;
}

export interface EndpointInfo {
  node_name: string;
  module_name: string;
  filter_name: string[];
}
