import { computed, ref } from 'vue';
import type { SystemInfo, PageModel } from './Index';

export const useModel = (): [PageModel] => {
  const systemInfo = ref<SystemInfo | null>(null);
  const hasAttributes = computed(() => {
    return (
      systemInfo.value?.static_info.attributes &&
      Array.isArray(systemInfo.value.static_info.attributes) &&
      systemInfo.value.static_info.attributes.length > 0
    );
  });

  const attributesList = computed(() => {
    if (!systemInfo.value?.static_info.attributes || !Array.isArray(systemInfo.value.static_info.attributes)) return [];

    return systemInfo.value.static_info.attributes.flatMap((attr) =>
      Object.entries(attr).map(([key, value]) => ({
        key,
        value: String(value)
      }))
    );
  });

  return [
    {
      systemInfo,
      hasAttributes,
      attributesList
    }
  ];
};
