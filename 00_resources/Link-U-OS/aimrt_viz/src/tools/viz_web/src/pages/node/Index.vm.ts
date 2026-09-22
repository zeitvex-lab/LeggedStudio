import { ConnectionStatus, connectorContext, onAgentConnected, onTimerTick } from '@/contexts/ConnectorContext';
import { GetNodeIndexInfo } from '@/apis/system';
import { useContext } from '@/utils';
import { ElMessage } from 'element-plus';
import { watchEffect, ref } from 'vue';
import { useModel } from './Index.model';
import type { PageViewModel, NodeBaseStaticInfo, NodeBaseDynamicInfo } from './Index';
import { sortArray } from '@/hooks/useSortedPagination';

export const useViewModel = (): PageViewModel => {
  const [pageModel] = useModel();
  const { nodeList, nodeStaticList, nodeDynamicList } = pageModel;
  const connectorRuntimeData = useContext(connectorContext);
  const isFirstLoadDone = ref(false); // 确保在onAgentConnected执行前不会触发定时器任务

  const fetchNodeIndexInfo = async () => {
    try {
      const response = await GetNodeIndexInfo();
      nodeStaticList.value = response.data.node_base_static_info_list?.node_base_static_info_list || [];
      nodeDynamicList.value = response.data.node_base_dynamic_info_list?.node_base_dynamic_info_list || [];

      // 排序静态和动态列表
      nodeStaticList.value = sortArray(nodeStaticList.value, 'node_name');
      nodeDynamicList.value = sortArray(nodeDynamicList.value, 'node_name');

      // 如果是首次加载或静态列表长度变化，需要重新构建整个列表
      if (!nodeList.value.length || nodeStaticList.value.length !== nodeList.value.length) {
        // 按 node_name 匹配融合静态和动态信息
        nodeList.value = nodeStaticList.value.map((staticInfo: NodeBaseStaticInfo) => {
          const matchedDynamicInfo = nodeDynamicList.value.find(
            (dynamicInfo: NodeBaseDynamicInfo & { node_name?: string }) =>
              dynamicInfo.node_name === staticInfo.node_name
          );
          return {
            static_info: staticInfo,
            dynamic_info: matchedDynamicInfo || ({} as NodeBaseDynamicInfo)
          };
        });
        console.log('node index 全量数据更新', nodeList.value);
      } else {
        // 只更新现有列表中的动态数据，按 node_name 匹配
        nodeList.value.forEach((node) => {
          const matchedDynamicInfo = nodeDynamicList.value.find(
            (dynamicInfo: NodeBaseDynamicInfo & { node_name?: string }) =>
              dynamicInfo.node_name === node.static_info.node_name
          );
          if (matchedDynamicInfo) {
            node.dynamic_info = matchedDynamicInfo;
          } else {
            node.dynamic_info = {} as NodeBaseDynamicInfo;
          }
        });
        console.log('node index 动态数据更新', nodeList.value);
      }
    } catch (error) {
      console.error('Node 索引信息请求失败', error);
      ElMessage({
        message: `Node 索引信息请求失败`,
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
        await fetchNodeIndexInfo();
        unwatch();
      }
    });
  });

  // 定时请求以更新动态数据
  onTimerTick(() => {
    if (connectorRuntimeData?.value?.connectionStatus !== ConnectionStatus.Connected || !isFirstLoadDone.value) return;
    fetchNodeIndexInfo();
  });

  return [pageModel, {}];
};
