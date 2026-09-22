import { ConnectionStatus, connectorContext, onTimerTick, onAgentConnected } from '@/contexts/ConnectorContext';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { ref, watchEffect } from 'vue';
import { useModel } from './Index.model';
import type { PageViewModel } from './Index';
import { GetSystemInfo } from '@/apis/system';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const { systemInfo } = pageModel;
  const connectorRuntimeData = useContext(connectorContext);
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  const fetchSystemInfo = async () => {
    try {
      const response = await GetSystemInfo();

      // 对属性进行排序
      if (response.data?.static_info?.attributes) {
        const attrs = response.data.static_info.attributes;
        response.data.static_info.attributes = Array.isArray(attrs)
          ? attrs.sort((a, b) => Object.keys(a)[0]?.localeCompare(Object.keys(b)[0]) || 0)
          : Object.entries(attrs)
              .map(([k, v]) => ({ [k]: v }))
              .sort((a, b) => Object.keys(a)[0].localeCompare(Object.keys(b)[0]));
      }
      systemInfo.value = response.data;
    } catch (error) {
      console.error('获取系统信息失败:', error);
      ElMessage({
        message: `获取系统信息失败`,
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
        await fetchSystemInfo();
        unwatch();
      }
    });
  });

  onTimerTick(() => {
    // 定时刷新请求动态数据
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchSystemInfo();
  });

  return [pageModel, {}];
};
