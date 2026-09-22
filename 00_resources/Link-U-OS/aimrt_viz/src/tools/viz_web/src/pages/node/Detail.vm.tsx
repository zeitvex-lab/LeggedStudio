import { ConnectionStatus, connectorContext, onTimerTick, onAgentConnected } from '@/contexts/ConnectorContext';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { watchEffect, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useModel } from './Detail.model';
import type { PageViewModel } from './Detail';
import { GetNodeDetailInfo } from '@/apis/system';
import { sortArray } from '@/hooks/useSortedPagination';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const {
    nodeBaseStaticInfo,
    nodeBaseDynamicInfo,
    configurationStaticInfo,
    logStaticInfo,
    pluginStaticInfo,
    executorStaticInfo,
    moduleStaticInfo,
    rpcStaticInfo,
    rpcDynamicInfo,
    channelStaticInfo,
    channelDynamicInfo
  } = pageModel;
  const connectorRuntimeData = useContext(connectorContext);
  const route = useRoute();
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  const fetchNodeDetailInfo = async () => {
    try {
      const req = {
        node_name: route.params.nodeName || ''
      };
      const response = await GetNodeDetailInfo(req);

      // 获取静态数据
      if (response.data.node_detail_static_info) {
        nodeBaseStaticInfo.value = response.data.node_detail_static_info.node_base_info;
        configurationStaticInfo.value = response.data.node_detail_static_info.configuration_info;
        logStaticInfo.value = response.data.node_detail_static_info.log_info;
        pluginStaticInfo.value = response.data.node_detail_static_info.plugin_info;
        executorStaticInfo.value = response.data.node_detail_static_info.executor_info;
        moduleStaticInfo.value = response.data.node_detail_static_info.module_info;
        rpcStaticInfo.value = response.data.node_detail_static_info.rpc_info;
        channelStaticInfo.value = response.data.node_detail_static_info.channel_info;

        if (executorStaticInfo.value?.executor_info_list) {
          executorStaticInfo.value.executor_info_list = sortArray(executorStaticInfo.value.executor_info_list, 'name');
        }
        if (pluginStaticInfo.value?.plugin_info_list) {
          pluginStaticInfo.value.plugin_info_list = sortArray(pluginStaticInfo.value.plugin_info_list, 'name');
        }
        if (logStaticInfo.value?.log_backend_info_list) {
          logStaticInfo.value.log_backend_info_list = sortArray(logStaticInfo.value.log_backend_info_list, 'type');
        }
        if (moduleStaticInfo.value?.module_info_list) {
          moduleStaticInfo.value.module_info_list = sortArray(moduleStaticInfo.value.module_info_list, 'name');
        }
        if (rpcStaticInfo.value?.rpc_backend_info_list) {
          rpcStaticInfo.value.rpc_backend_info_list = sortArray(rpcStaticInfo.value.rpc_backend_info_list, 'type');
        }
        if (channelStaticInfo.value?.channel_backend_info_list) {
          channelStaticInfo.value.channel_backend_info_list = sortArray(
            channelStaticInfo.value.channel_backend_info_list,
            'type'
          );
        }

        console.log('node index 全量数据更新', response.data);
      }

      //  获取动态数据
      if (response.data.node_detail_dynamic_info) {
        nodeBaseDynamicInfo.value = response.data.node_detail_dynamic_info.node_base_info;
        rpcDynamicInfo.value = response.data.node_detail_dynamic_info.rpc_info;
        channelDynamicInfo.value = response.data.node_detail_dynamic_info.channel_info;
        console.log('node detail 动态数据更新', response.data);
      }
    } catch (error) {
      console.error('Node 详情信息请求失败', error);
      ElMessage({
        message: `Node 详情信息请求失败'}`,
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
        await fetchNodeDetailInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchNodeDetailInfo();
  });

  return [pageModel, {}];
};
