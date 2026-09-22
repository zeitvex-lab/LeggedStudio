import { request } from '@/utils';

// 创建带超时的请求包装器
const createApiRequest = (url: string, defaultTimeout = 10000) => {
  return (params?: any, timeout = defaultTimeout) => {
    return request
      .post(
        url,
        { ...params },
        {
          headers: {
            'Content-Type': 'application/json'
          },
          timeout: timeout
        }
      )
      .catch((error) => {
        // 处理超时错误
        if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
          throw new Error(`请求超时：${timeout}ms`);
        }
        throw error;
      });
  };
};

export const GetSystemInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetSystemInfo');
export const GetNodeIndexInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetNodeBaseInfo');
export const GetNodeDetailInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetNodeDetailInfo');
export const GetModuleDetailInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetModuleDetailInfo');
export const GetRpcIndexInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetRpcIndexInfo');
export const GetRpcDetailInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetRpcDetailInfo');
export const GetChannelIndexInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetChannelIndexInfo');
export const GetChannelDetailInfo = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetChannelDetailInfo');
export const GetResource = createApiRequest('/rpc/aimrt.protocols.viz_web.AgentService/GetResource');
