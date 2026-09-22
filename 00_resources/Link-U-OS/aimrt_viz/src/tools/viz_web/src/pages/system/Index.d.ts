import { type ComputedRef, type Ref } from 'vue';

// 页面VM定义
export type PageViewModel = [
  PageModel,
  {
    // 方法定义
  }
];

// 页面model定义
export type PageModel = {
  systemInfo: Ref<SystemInfo | null>;
  hasAttributes: ComputedRef;
  attributesList: ComputedRef;
};

export interface SystemInfo {
  static_info: SystemStaticInfo;
  dynamic_info: SystemDynamicInfo;
}

export interface SystemStaticInfo {
  name: string;
  aimrt_viz_version: string;
  attributes: Record<string, string>[];
}

export interface SystemDynamicInfo {}
