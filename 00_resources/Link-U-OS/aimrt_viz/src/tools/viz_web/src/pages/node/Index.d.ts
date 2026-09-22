import { type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面 model定义
export type PageModel = {
  nodeList: Ref<NodeInfo[]>;
  nodeStaticList: Ref<NodeBaseStaticInfo[]>;
  nodeDynamicList: Ref<NodeBaseDynamicInfo[]>;
  filteredNodeList: ComputedRef<NodeInfo[]>;
  socOptions: ComputedRef;
  searchQuery: Ref<string>;
  socFilter: Ref<string>;
  onlineStatusFilter: Ref<OnlineStatusOption>;
};

// 相关数据结构体定义
export type OnlineStatusOption = 'all' | 'online' | 'offline';

export interface NodeInfo {
  static_info: NodeBaseStaticInfo;
  dynamic_info: NodeBaseDynamicInfo;
}

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
