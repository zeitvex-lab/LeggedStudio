import { ConnectionStatus, connectorContext, onAgentConnected, onTimerTick } from '@/contexts/ConnectorContext';
import { GetRpcDetailInfo } from '@/apis/system';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { watchEffect, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useModel } from './Detail.model';
import type { PageViewModel } from './Detail';
import { sortArray } from '@/hooks/useSortedPagination';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const { rpcDetailInfo } = pageModel;
  const route = useRoute();
  const connectorRuntimeData = useContext(connectorContext);
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  // 获取完整节点信息（静态+动态）
  const fetchRpcDetailInfo = async () => {
    try {
      const req = {
        func_name: route.params.funcName
      };
      const response = await GetRpcDetailInfo(req);
      rpcDetailInfo.value = response.data;

      // 直接对 rpcDetailInfo.value 进行排序处理
      if (rpcDetailInfo.value?.rpc_detail_dynamic_info) {
        // 排序 client_info 中的 module_infos
        if (rpcDetailInfo.value.rpc_detail_dynamic_info.client_info?.module_infos) {
          rpcDetailInfo.value.rpc_detail_dynamic_info.client_info.module_infos = sortArray(
            rpcDetailInfo.value.rpc_detail_dynamic_info.client_info.module_infos,
            'node_name'
          );
        }

        // 排序 server_info 中的 module_infos
        if (rpcDetailInfo.value.rpc_detail_dynamic_info.server_info?.module_infos) {
          rpcDetailInfo.value.rpc_detail_dynamic_info.server_info.module_infos = sortArray(
            rpcDetailInfo.value.rpc_detail_dynamic_info.server_info.module_infos,
            'node_name'
          );
        }

        // 排序 endpoint_info
        if (rpcDetailInfo.value.rpc_detail_dynamic_info.endpoint_info) {
          rpcDetailInfo.value.rpc_detail_dynamic_info.endpoint_info = sortArray(
            rpcDetailInfo.value.rpc_detail_dynamic_info.endpoint_info,
            'backend_name'
          );

          // 排序每个 endpoint 的 client_endpoints 和 server_endpoints
          rpcDetailInfo.value.rpc_detail_dynamic_info.endpoint_info.forEach((endpoint) => {
            if (endpoint.client_endpoints) {
              endpoint.client_endpoints = sortArray(endpoint.client_endpoints, 'node_name');
            }
            if (endpoint.server_endpoints) {
              endpoint.server_endpoints = sortArray(endpoint.server_endpoints, 'node_name');
            }
          });
        }
      }

      console.log('节点信息获取成功:', rpcDetailInfo.value);
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
        await fetchRpcDetailInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchRpcDetailInfo();
  });

  return [pageModel, {}];
};
