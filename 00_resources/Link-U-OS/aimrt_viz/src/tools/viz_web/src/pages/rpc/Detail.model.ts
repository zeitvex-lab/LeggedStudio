import { ref, computed } from 'vue';
import type { RpcDetailInfo, PageModel } from './Detail';

export const useModel = (): [PageModel] => {
  const rpcDetailInfo = ref<RpcDetailInfo | null>(null);

  const client_error_rate = computed(() => {
    if (rpcDetailInfo.value) {
      const errorRate = rpcDetailInfo.value.rpc_detail_dynamic_info.client_info.current_status.error_rate;
      return `${(errorRate * 100).toFixed(3)} %`;
    }
    return '0.000 %';
  });

  const server_error_rate = computed(() => {
    if (rpcDetailInfo.value) {
      const errorRate = rpcDetailInfo.value.rpc_detail_dynamic_info.server_info.current_status.error_rate;
      return `${(errorRate * 100).toFixed(3)} %`;
    }
    return '0.000 %';
  });

  return [{ rpcDetailInfo, client_error_rate, server_error_rate }];
};
