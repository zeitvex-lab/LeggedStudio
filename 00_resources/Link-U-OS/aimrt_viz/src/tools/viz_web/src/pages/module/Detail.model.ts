import { computed, ref } from 'vue';
import type {
  ModuleBaseStaticInfo,
  PageModel,
  ModuleRpcStaticInfo,
  ModuleChannelStaticInfo,
  ModuleRpcDynamicInfo,
  ModuleChannelDynamicInfo,
  RpcMergeInfoMeta,
  ChannelMergeInfoMeta
} from './Detail';
import { sortArray } from '@/hooks/useSortedPagination';

export const useModel = (): [PageModel] => {
  const moduleBaseInfo = ref<ModuleBaseStaticInfo | null>(null);
  const rpcClinetInfoList = ref<ModuleRpcStaticInfo[] | []>([]);
  const rpcServerInfoList = ref<ModuleRpcStaticInfo[] | []>([]);
  const chnPubInfoList = ref<ModuleChannelStaticInfo[] | []>([]);
  const chnSubInfoList = ref<ModuleChannelStaticInfo[] | []>([]);

  const rpcClinetDynamicInfoList = ref<ModuleRpcDynamicInfo[] | []>([]);
  const rpcServerDynamicInfoList = ref<ModuleRpcDynamicInfo[] | []>([]);
  const chnPubDynamicInfoList = ref<ModuleChannelDynamicInfo[] | []>([]);
  const chnSubDynamicInfoList = ref<ModuleChannelDynamicInfo[] | []>([]);

  function mergeRpcInfo(staticInfos: ModuleRpcStaticInfo[], dynamicInfos: ModuleRpcDynamicInfo[]): RpcMergeInfoMeta[] {
    const mergedMap = new Map<string, RpcMergeInfoMeta>();
    staticInfos.forEach((info) => {
      mergedMap.set(info.func_name, {
        ...info,
        connected_to_node: [],
        connected_to_module: []
      });
    });
    dynamicInfos.forEach((info) => {
      const mergedInfo = mergedMap.get(info.func_name);
      if (mergedInfo) {
        info.conneced_to.forEach((conn) => {
          mergedInfo.connected_to_node.push(conn.node_name);
          mergedInfo.connected_to_module.push(conn.module_name);
        });
      }
    });
    return Array.from(mergedMap.values());
  }

  function mergeChnInfo(
    staticInfos: ModuleChannelStaticInfo[],
    dynamicInfos: ModuleChannelDynamicInfo[]
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

    dynamicInfos.forEach((info) => {
      const key = getKey(info.topic, info.msg_type);
      const mergedInfo = mergedMap.get(key);
      if (mergedInfo) {
        info.connected_to.forEach((conn) => {
          mergedInfo.connected_to_node.push(conn.node_name);
          mergedInfo.connected_to_module.push(conn.module_name);
        });
      }
    });
    return Array.from(mergedMap.values());
  }

  const rpcClientMergedInfoList = computed(() => {
    if (rpcClinetInfoList.value && rpcClinetDynamicInfoList.value) {
      const merged = mergeRpcInfo(rpcClinetInfoList.value, rpcClinetDynamicInfoList.value);
      return sortArray(merged, 'func_name');
    }
    return [];
  });

  const rpcServerMergedInfoList = computed(() => {
    if (rpcServerInfoList.value && rpcServerDynamicInfoList.value) {
      const merged = mergeRpcInfo(rpcServerInfoList.value, rpcServerDynamicInfoList.value);
      return sortArray(merged, 'func_name');
    }
    return [];
  });

  const channelPubMergedInfoList = computed(() => {
    if (chnPubInfoList.value && chnPubDynamicInfoList.value) {
      const merged = mergeChnInfo(chnPubInfoList.value, chnPubDynamicInfoList.value);
      return sortArray(merged, 'topic');
    }
    return [];
  });

  const channelSubMergedInfoList = computed(() => {
    if (chnSubInfoList.value && chnSubDynamicInfoList.value) {
      const merged = mergeChnInfo(chnSubInfoList.value, chnSubDynamicInfoList.value);
      return sortArray(merged, 'topic');
    }
    return [];
  });

  return [
    {
      moduleBaseInfo,
      rpcClinetInfoList,
      rpcServerInfoList,
      chnPubInfoList,
      chnSubInfoList,
      rpcClinetDynamicInfoList,
      rpcServerDynamicInfoList,
      chnPubDynamicInfoList,
      chnSubDynamicInfoList,
      rpcServerMergedInfoList,
      rpcClientMergedInfoList,
      channelPubMergedInfoList,
      channelSubMergedInfoList
    }
  ];
};
