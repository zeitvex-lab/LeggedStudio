import { ConnectionStatus, connectorContext, onAgentConnected, onTimerTick } from '@/contexts/ConnectorContext';
import { GetRpcIndexInfo } from '@/apis/system';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { watchEffect, ref } from 'vue';
import { useModel } from './Index.model';
import type { PageViewModel } from './Index';
import { sortArray } from '@/hooks/useSortedPagination';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const { rpcIndexInfo } = pageModel;
  const connectorRuntimeData = useContext(connectorContext);
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  // 获取完整节点信息（静态+动态）
  const fetchRpcIndexInfo = async () => {
    try {
      const response = await GetRpcIndexInfo();
      rpcIndexInfo.value = response.data;

      rpcIndexInfo.value = response.data;

      if (rpcIndexInfo.value?.rpc_index_dynamic_info.dynamic_info_meta) {
        rpcIndexInfo.value.rpc_index_dynamic_info.dynamic_info_meta =
          rpcIndexInfo.value.rpc_index_dynamic_info.dynamic_info_meta.map((item) => ({
            ...item,
            client_qps: Number(item.client_qps.toFixed(3)),
            server_qps: Number(item.server_qps.toFixed(3))
          }));

        rpcIndexInfo.value.rpc_index_dynamic_info.dynamic_info_meta = sortArray(
          rpcIndexInfo.value.rpc_index_dynamic_info.dynamic_info_meta,
          'func_name'
        );
      }

      console.log('节点信息获取成功:', rpcIndexInfo.value);
    } catch (error) {
      console.error('获取节点信息失败:', error);
      ElMessage({
        message: `获取节点信息失败'}`,
        type: 'error',
        duration: 4000,
        offset: 20,
        customClass: 'header-message'
      });
    }
  };

  // 待连接成功后请求一次全量信息
  onAgentConnected(() => {
    const unwatch = watchEffect(async () => {
      if (connectorRuntimeData?.value?.connectionStatus === ConnectionStatus.Connected && !isFirstLoadDone.value) {
        isFirstLoadDone.value = true;
        await fetchRpcIndexInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchRpcIndexInfo();
    console.log('node index 定期请求动态数据');
  });

  return [pageModel, {}];
};
