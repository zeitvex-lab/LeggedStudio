import { computed, ref } from 'vue';
import type { NodeInfo, NodeBaseStaticInfo, NodeBaseDynamicInfo, PageModel, OnlineStatusOption } from './Index';

export const useModel = (): [PageModel] => {
  // 变量初始化
  const nodeList = ref<NodeInfo[]>([]); // 用于接受服务端返回的数据（其必须与服务端数据结构一致）

  const nodeStaticList = ref<NodeBaseStaticInfo[]>([]);
  const nodeDynamicList = ref<NodeBaseDynamicInfo[]>([]);

  const searchQuery = ref('');
  const socFilter = ref('');
  const onlineStatusFilter = ref<OnlineStatusOption>('online');

  // 用于筛选：获取列表中的 Soc 型号选项
  const socOptions = computed(() => {
    const options = new Set<string>();
    nodeList.value.forEach((node) => {
      if (node.static_info.soc) {
        options.add(node.static_info.soc);
      }
    });
    return Array.from(options);
  });

  // 用于筛选：根据搜索框的输入内容和 Soc 型号选项进行筛选
  const filteredNodeList = computed(() => {
    return nodeList.value.filter((node) => {
      const nameMatch =
        !searchQuery.value || node.static_info.node_name.toLowerCase().includes(searchQuery.value.toLowerCase());
      const socMatch = !socFilter.value || node.static_info.soc === socFilter.value;

      let statusMatch = true;
      if (onlineStatusFilter.value === 'online') {
        statusMatch = node.dynamic_info.online_time_s >= 0;
      } else if (onlineStatusFilter.value === 'offline') {
        statusMatch = node.dynamic_info.online_time_s === undefined;
      }
      return nameMatch && socMatch && statusMatch;
    });
  });

  // 返回数据模型
  return [
    {
      nodeList,
      filteredNodeList,
      nodeStaticList,
      nodeDynamicList,
      socOptions,
      searchQuery,
      socFilter,
      onlineStatusFilter
    }
  ];
};
