import { ConnectionStatus, connectorContext, onAgentConnected, onTimerTick } from '@/contexts/ConnectorContext';
import { GetChannelDetailInfo } from '@/apis/system';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { watchEffect, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useModel } from './Detail.model';
import type { PageViewModel } from './Detail';
import { sortArray } from '@/hooks/useSortedPagination';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const { chnDetailInfo } = pageModel;
  const route = useRoute();

  const connectorRuntimeData = useContext(connectorContext);
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  // 获取完整节点信息（静态+动态）
  const fetchChnDetailInfo = async () => {
    try {
      const req = {
        topic_name: route.params.topic,
        msg_type: route.params.msgType
      };
      const response = await GetChannelDetailInfo(req);
      chnDetailInfo.value = response.data;

      // 排序处理
      if (chnDetailInfo.value?.channel_detail_dynamic_info) {
        // 排序 sub_info 中的 module_infos
        if (chnDetailInfo.value.channel_detail_dynamic_info.sub_info?.module_infos) {
          chnDetailInfo.value.channel_detail_dynamic_info.sub_info.module_infos = sortArray(
            chnDetailInfo.value.channel_detail_dynamic_info.sub_info.module_infos,
            'node_name'
          );
        }

        // 排序 pub_info 中的 module_infos
        if (chnDetailInfo.value.channel_detail_dynamic_info.pub_info?.module_infos) {
          chnDetailInfo.value.channel_detail_dynamic_info.pub_info.module_infos = sortArray(
            chnDetailInfo.value.channel_detail_dynamic_info.pub_info.module_infos,
            'node_name'
          );
        }

        // 排序 endpoint_info
        if (chnDetailInfo.value.channel_detail_dynamic_info.endpoint_info) {
          chnDetailInfo.value.channel_detail_dynamic_info.endpoint_info = sortArray(
            chnDetailInfo.value.channel_detail_dynamic_info.endpoint_info,
            'backend_name'
          );

          // 排序每个 endpoint 的 sub_endpoints 和 pub_endpoints
          chnDetailInfo.value.channel_detail_dynamic_info.endpoint_info.forEach((endpoint) => {
            if (endpoint.sub_endpoints) {
              endpoint.sub_endpoints = sortArray(endpoint.sub_endpoints, 'node_name');
            }
            if (endpoint.pub_endpoints) {
              endpoint.pub_endpoints = sortArray(endpoint.pub_endpoints, 'node_name');
            }
          });
        }
      }

      console.log('节点信息获取成功:', chnDetailInfo.value);
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
        await fetchChnDetailInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchChnDetailInfo();
  });

  return [pageModel, {}];
};
