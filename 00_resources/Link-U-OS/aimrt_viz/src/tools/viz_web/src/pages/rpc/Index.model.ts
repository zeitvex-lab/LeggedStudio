import { computed, ref } from 'vue';
import type { RpcIndexInfo, PageModel, SearchParamsModel } from './Index';

export const useModel = (): [PageModel] => {
  const rpcIndexInfo = ref<RpcIndexInfo | null>(null);
  const searchParams = ref<SearchParamsModel>({
    funcName: '',
    backend: '',
    filter: ''
  });

  // 获取所有可用的后端选项
  const backendOptions = computed(() => {
    const options = new Set<string>();
    rpcIndexInfo.value?.rpc_index_dynamic_info.dynamic_info_meta.forEach((item) => {
      item.backend_name.forEach((b) => options.add(b));
    });
    return Array.from(options);
  });

  // 获取所有可用的过滤器选项
  const filterOptions = computed(() => {
    const options = new Set<string>();
    rpcIndexInfo.value?.rpc_index_dynamic_info.dynamic_info_meta.forEach((item) => {
      item.filter_name.forEach((b) => options.add(b));
    });
    return Array.from(options);
  });

  const filteredTableData = computed(() => {
    if (!rpcIndexInfo.value || !rpcIndexInfo.value.rpc_index_dynamic_info) {
      return [];
    }

    return rpcIndexInfo.value.rpc_index_dynamic_info.dynamic_info_meta.filter((item) => {
      const matchFuncName =
        !searchParams.value.funcName ||
        item.func_name.toLowerCase().includes(searchParams.value.funcName.toLowerCase());

      const matchBackend = !searchParams.value.backend || item.backend_name.includes(searchParams.value.backend);

      const matchFilter = !searchParams.value.filter || item.filter_name.includes(searchParams.value.filter);

      return matchFuncName && matchBackend && matchFilter;
    });
  });

  return [{ rpcIndexInfo, searchParams, backendOptions, filterOptions, filteredTableData }];
};
