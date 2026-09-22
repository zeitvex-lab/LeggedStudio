import { ConnectionStatus, connectorContext, onTimerTick, onAgentConnected } from '@/contexts/ConnectorContext';
import { useContext } from '@/utils';
import { watchEffect, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useModel } from './Detail.model';
import type { PageViewModel } from './Detail';
import { GetModuleDetailInfo } from '@/apis/system';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const {
    moduleBaseInfo,
    rpcClinetInfoList,
    rpcServerInfoList,
    chnPubInfoList,
    chnSubInfoList,
    rpcClinetDynamicInfoList,
    rpcServerDynamicInfoList,
    chnPubDynamicInfoList,
    chnSubDynamicInfoList
  } = pageModel;
  const connectorRuntimeData = useContext(connectorContext);
  const route = useRoute();
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  const fetchModuleDetailInfo = async () => {
    try {
      const req = {
        node_name: (route.params.nodeName as string) || '',
        module_name: (route.params.moduleId as string) || ''
      };
      const response = await GetModuleDetailInfo(req);

      // 获取静态数据
      if (response.data.module_detail_static_info) {
        moduleBaseInfo.value = response.data.module_detail_static_info.base_info;
        rpcClinetInfoList.value = response.data.module_detail_static_info.client_info;
        rpcServerInfoList.value = response.data.module_detail_static_info.server_info;
        chnPubInfoList.value = response.data.module_detail_static_info.pub_info;
        chnSubInfoList.value = response.data.module_detail_static_info.sub_info;
        console.log('module detail 全量数据更新', response.data);
      }

      //  获取动态数据
      if (response.data.module_detail_dynamic_info) {
        rpcClinetDynamicInfoList.value = response.data.module_detail_dynamic_info.client_info;
        rpcServerDynamicInfoList.value = response.data.module_detail_dynamic_info.server_info;
        chnPubDynamicInfoList.value = response.data.module_detail_dynamic_info.pub_info;
        chnSubDynamicInfoList.value = response.data.module_detail_dynamic_info.sub_info;
        console.log('module detail 动态数据更新', response.data);
      }
    } catch (error) {
      console.error('Module 详情信息获取失败:', error);
    }
  };

  // 待连接成功后请求一次全量信息
  onAgentConnected(() => {
    const unwatch = watchEffect(async () => {
      if (connectorRuntimeData?.value?.connectionStatus === ConnectionStatus.Connected && !isFirstLoadDone.value) {
        isFirstLoadDone.value = true;
        await fetchModuleDetailInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchModuleDetailInfo();
  });

  return [pageModel, {}];
};
