import { type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面model定义
export type PageModel = {
  rpcIndexInfo: Ref<RpcIndexInfo | null>;
  searchParams: Ref<SearchParamsModel>;
  backendOptions: ComputedRef<string[]>;
  filterOptions: ComputedRef<string[]>;
  filteredTableData: ComputedRef<DynamicInfoMeta[]>;
};

export interface RpcIndexInfo {
  rpc_index_static_info: RpcIndexStaticInfo;
  rpc_index_dynamic_info: RpcIndexDynamicInfo;
}

export interface RpcIndexStaticInfo {}

export interface RpcIndexDynamicInfo {
  dynamic_info_meta: DynamicInfoMeta[];
}

export interface DynamicInfoMeta {
  func_name: string;
  client_count: number;
  server_count: number;
  backend_name: string[];
  filter_name: string[];
  client_qps: number;
  server_qps: number;
}

export interface SearchParamsModel {
  funcName: string;
  backend: string;
  filter: string;
}
