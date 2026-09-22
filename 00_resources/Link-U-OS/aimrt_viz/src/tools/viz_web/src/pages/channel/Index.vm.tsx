import { ConnectionStatus, connectorContext, onAgentConnected, onTimerTick } from '@/contexts/ConnectorContext';
import { GetChannelIndexInfo } from '@/apis/system';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { watchEffect, ref } from 'vue';
import { useModel } from './Index.model';
import type { PageViewModel } from './Index';
import { sortArray } from '@/hooks/useSortedPagination';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const { chnIndexInfo } = pageModel;
  const connectorRuntimeData = useContext(connectorContext);
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  // 获取完整节点信息（静态+动态）
  const fetchChnIndexInfo = async () => {
    try {
      const response = await GetChannelIndexInfo();
      console.log('节点信息获取成功:', response.data);

      chnIndexInfo.value = response.data;
      if (chnIndexInfo.value?.channel_index_dynamic_info.dynamic_info_meta) {
        chnIndexInfo.value.channel_index_dynamic_info.dynamic_info_meta =
          chnIndexInfo.value.channel_index_dynamic_info.dynamic_info_meta.map((item) => ({
            ...item,
            client_qps: Number(item.pub_frequency.toFixed(3)),
            server_qps: Number(item.sub_frequency.toFixed(3))
          }));

        chnIndexInfo.value.channel_index_dynamic_info.dynamic_info_meta = sortArray(
          chnIndexInfo.value.channel_index_dynamic_info.dynamic_info_meta,
          'topic_name'
        );
      }

      console.log('节点信息获取成功:', chnIndexInfo.value);
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
        await fetchChnIndexInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchChnIndexInfo();
    console.log('node index 定期请求动态数据');
  });

  return [pageModel, {}];
};
