import { type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [PageModel, {}];

// 页面model定义
export type PageModel = {
  chnIndexInfo: Ref<ChnIndexInfo | null>;
  searchParams: Ref<SearchParamsModel>;
  backendOptions: ComputedRef<string[]>;
  filterOptions: ComputedRef<string[]>;
  filteredTableData: ComputedRef<DynamicInfoMeta[]>;
};

export interface ChnIndexInfo {
  channel_index_static_info: ChnIndexStaticInfo;
  channel_index_dynamic_info: ChnIndexDynamicInfo;
}

export interface ChnIndexStaticInfo {}

export interface ChnIndexDynamicInfo {
  dynamic_info_meta: DynamicInfoMeta[];
}

export interface DynamicInfoMeta {
  topic_name: string;
  msg_type: string;
  sub_count: number;
  pub_count: number;
  backend_name: string[];
  filter_name: string[];
  sub_frequency: number;
  pub_frequency: number;
}

export interface SearchParamsModel {
  topic_name: string;
  msg_type: string;
  backend: string;
  filter: string;
}
