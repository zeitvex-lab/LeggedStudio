import { computed, ref } from 'vue';
import type { ChnIndexInfo, PageModel, SearchParamsModel } from './Index';

export const useModel = (): [PageModel] => {
  const chnIndexInfo = ref<ChnIndexInfo | null>(null);
  const searchParams = ref<SearchParamsModel>({
    topic_name: '',
    msg_type: '',
    backend: '',
    filter: ''
  });

  // 获取所有可用的后端选项
  const backendOptions = computed(() => {
    const options = new Set<string>();
    chnIndexInfo.value?.channel_index_dynamic_info.dynamic_info_meta.forEach((item) => {
      item.backend_name.forEach((b) => options.add(b));
    });
    return Array.from(options);
  });

  // 获取所有可用的过滤器选项
  const filterOptions = computed(() => {
    const options = new Set<string>();
    chnIndexInfo.value?.channel_index_dynamic_info.dynamic_info_meta.forEach((item) => {
      item.filter_name.forEach((b) => options.add(b));
    });
    return Array.from(options);
  });

  const filteredTableData = computed(() => {
    if (!chnIndexInfo.value || !chnIndexInfo.value.channel_index_dynamic_info) {
      return [];
    }

    return chnIndexInfo.value.channel_index_dynamic_info.dynamic_info_meta.filter((item) => {
      const matchTopicName =
        !searchParams.value.topic_name ||
        item.topic_name.toLowerCase().includes(searchParams.value.topic_name.toLowerCase());

      const matchMsgType =
        !searchParams.value.msg_type || item.msg_type.toLowerCase().includes(searchParams.value.msg_type.toLowerCase());

      const matchBackend = !searchParams.value.backend || item.backend_name.includes(searchParams.value.backend);

      const matchFilter = !searchParams.value.filter || item.filter_name.includes(searchParams.value.filter);

      return matchTopicName && matchMsgType && matchBackend && matchFilter;
    });
  });

  return [{ chnIndexInfo, searchParams, backendOptions, filterOptions, filteredTableData }];
};
