import { computed, ref } from 'vue';
import type {
  NodeBaseStaticInfo,
  NodeBaseDynamicInfo,
  ConfigurationStaticInfo,
  LogStaticInfo,
  PluginStaticInfo,
  ExecutorStaticInfo,
  ModuleStaticInfo,
  RpcStaticInfo,
  RpcDynamicInfo,
  ChannelStaticInfo,
  ChannelDynamicInfo,
  PageModel,
  RpcMergeInfoMeta,
  RpcClientInfoMeta,
  RpcConnectedToMeta,
  ChannelConnectedToMeta,
  ChannelPubInfoMeta,
  ChannelMergeInfoMeta
} from './Detail';

import { formatMemory, formatTimestamp, formatPercentage, formatOnlineTime } from '@/utils/format';
import { sortArray } from '@/hooks/useSortedPagination';

export const useModel = (): [PageModel] => {
  const nodeBaseStaticInfo = ref<NodeBaseStaticInfo | null>(null);
  const nodeBaseDynamicInfo = ref<NodeBaseDynamicInfo | null>(null);

  const configurationStaticInfo = ref<ConfigurationStaticInfo | null>(null);

  const logStaticInfo = ref<LogStaticInfo | null>(null);

  const pluginStaticInfo = ref<PluginStaticInfo | null>(null);
  const executorStaticInfo = ref<ExecutorStaticInfo | null>(null);
  const moduleStaticInfo = ref<ModuleStaticInfo | null>(null);

  const rpcStaticInfo = ref<RpcStaticInfo | null>(null);
  const rpcDynamicInfo = ref<RpcDynamicInfo | null>(null);
  const channelStaticInfo = ref<ChannelStaticInfo | null>(null);
  const channelDynamicInfo = ref<ChannelDynamicInfo | null>(null);

  const strat_time_format = computed(() => {
    if (nodeBaseStaticInfo.value?.start_time_stamp_ns) {
      return formatTimestamp(nodeBaseStaticInfo.value.start_time_stamp_ns);
    }
    return '';
  });
  const online_time_format = computed(() => {
    if (nodeBaseDynamicInfo.value?.online_time_s) {
      return formatOnlineTime(nodeBaseDynamicInfo.value.online_time_s);
    }
    return '';
  });
  const memory_usage_format = computed(() => {
    if (nodeBaseDynamicInfo.value?.memory_usage_kb && nodeBaseDynamicInfo.value.memory_usage_percent) {
      return formatMemory(nodeBaseDynamicInfo.value.memory_usage_kb, nodeBaseDynamicInfo.value.memory_usage_percent);
    }
    return '';
  });
  const cpu_usage_format = computed(() => {
    if (nodeBaseDynamicInfo.value?.cpu_usage_percent) {
      return formatPercentage(nodeBaseDynamicInfo.value.cpu_usage_percent);
    }
    return '0.0%';
  });

  function mergeRpcInfo(staticInfos: RpcClientInfoMeta[], dynamicInfos: RpcConnectedToMeta[]): RpcMergeInfoMeta[] {
    const mergedMap = new Map<string, RpcMergeInfoMeta>();
    staticInfos.forEach((info) => {
      mergedMap.set(info.func_name, {
        ...info,
        connected_to_node: [],
        connected_to_module: []
      });
    });
    dynamicInfos.forEach((conn) => {
      const mergedInfo = mergedMap.get(conn.func_name);
      if (mergedInfo) {
        mergedInfo.connected_to_node.push(conn.node_name);
        mergedInfo.connected_to_module.push(conn.module_name);
      }
    });
    return Array.from(mergedMap.values());
  }

  function mergeChnInfo(
    staticInfos: ChannelPubInfoMeta[],
    dynamicInfos: ChannelConnectedToMeta[]
  ): ChannelMergeInfoMeta[] {
    const mergedMap = new Map<string, ChannelMergeInfoMeta>();
    const getKey = (topic: string, msgType: string) => `${topic}_${msgType}`;

    staticInfos.forEach((info) => {
      mergedMap.set(getKey(info.topic, info.msg_type), {
        ...info,
        connected_to_node: [],
        connected_to_module: []
      });
    });

    dynamicInfos.forEach((conn) => {
      const key = getKey(conn.topic, conn.msg_type);
      const mergedInfo = mergedMap.get(key);
      if (mergedInfo) {
        mergedInfo.connected_to_node.push(conn.node_name);
        mergedInfo.connected_to_module.push(conn.module_name);
      }
    });
    return Array.from(mergedMap.values());
  }

  const rpcServerInfoList = computed(() => {
    if (rpcStaticInfo.value && rpcDynamicInfo.value) {
      const merged = mergeRpcInfo(
        rpcStaticInfo.value.rpc_server_info_list,
        rpcDynamicInfo.value.client_dynamic_info_list
      );
      return sortArray(merged, 'func_name');
    }
    return [];
  });

  const rpcClientInfoList = computed(() => {
    if (rpcStaticInfo.value && rpcDynamicInfo.value) {
      const merged = mergeRpcInfo(
        rpcStaticInfo.value.rpc_client_info_list,
        rpcDynamicInfo.value.server_dynamic_info_list
      );
      return sortArray(merged, 'func_name');
    }
    return [];
  });

  const channelPubInfoList = computed(() => {
    if (channelStaticInfo.value && channelDynamicInfo.value) {
      const merged = mergeChnInfo(
        channelStaticInfo.value.channel_pub_info_list,
        channelDynamicInfo.value.sub_dynamic_info_list
      );
      return sortArray(merged, 'topic');
    }
    return [];
  });

  const channelSubInfoList = computed(() => {
    if (channelStaticInfo.value && channelDynamicInfo.value) {
      const merged = mergeChnInfo(
        channelStaticInfo.value.channel_sub_info_list,
        channelDynamicInfo.value.pub_dynamic_info_list
      );
      return sortArray(merged, 'topic');
    }
    return [];
  });

  return [
    {
      configurationStaticInfo,
      nodeBaseStaticInfo,
      nodeBaseDynamicInfo,
      logStaticInfo,

      pluginStaticInfo,
      executorStaticInfo,
      moduleStaticInfo,

      rpcStaticInfo,
      rpcDynamicInfo,
      channelStaticInfo,
      channelDynamicInfo,

      strat_time_format,
      online_time_format,
      memory_usage_format,
      cpu_usage_format,

      rpcServerInfoList,
      rpcClientInfoList,
      channelPubInfoList,
      channelSubInfoList
    }
  ];
};
