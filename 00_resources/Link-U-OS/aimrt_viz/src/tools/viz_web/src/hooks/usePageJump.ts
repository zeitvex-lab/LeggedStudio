import { useRouter, useRoute } from 'vue-router';

export const useNPageJump = () => {
  const router = useRouter();
  const route = useRoute();

  const viewNodeDetail = (node_name: string) => {
    router.push({
      name: 'node-detail',
      params: {
        nodeName: node_name
      },
      query: {}
    });
  };

  const viewModuleDetail = (node_name: string | undefined, module_name: string) => {
    router.push({
      name: 'module-detail',
      params: {
        nodeName: node_name || route.params.nodeName,
        moduleId: module_name
      },
      query: {}
    });
  };

  const viewRpcDetail = (func_name: string) => {
    router.push({
      name: 'rpc-detail',
      params: { funcName: func_name },
      query: {}
    });
  };

  const viewChannelDetail = (topic: string, msg_type: string) => {
    router.push({
      name: 'channel-detail',
      params: { topic: topic, msgType: msg_type },
      query: {}
    });
  };

  const handleTwoColClick = (idx: string, param1: string, param2?: string) => {
    if (param2) {
      if (idx === 'first') {
        viewNodeDetail(param1);
      } else {
        viewModuleDetail(param1, param2);
      }
    } else {
      viewModuleDetail(undefined, param1);
    }
  };

  return { viewNodeDetail, viewModuleDetail, viewRpcDetail, viewChannelDetail, handleTwoColClick };
};
