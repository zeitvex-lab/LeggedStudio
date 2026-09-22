import { createContext, useContext, request } from '@/utils';
import type { InternalAxiosRequestConfig } from 'axios';
import { watchEffect } from 'vue';

request.interceptors.request.use(ConnectorContextRequestInterceptor);

// 提供三种连接状态（未连接、正在连接、已连接）
export enum ConnectionStatus {
  Disconnected = 0,
  Connecting = 1,
  Connected = 2
}

export type ConnectorRuntimeData = {
  connectionStatus: ConnectionStatus;
  agentIP?: string;
  timeTickTimes: number;
};

export const connectorContext = createContext<ConnectorRuntimeData>({
  connectionStatus: ConnectionStatus.Disconnected,
  agentIP: '',
  timeTickTimes: 1
});
export const ConnectorContextProvider = connectorContext.Provider;

/**
 * 只能在vue setup声明周期内使用
 * @returns
 */
export const useConnectorContext = () => {
  return useContext(connectorContext);
};

/**
 * 智能请求拦截器：自动检测是否需要代理
 * - 如果当前页面是HTTPS，则使用nginx代理转发到HTTP后端
 * - 如果当前页面是HTTP，则直接连接后端
 * @param config
 * @returns
 */
export function ConnectorContextRequestInterceptor(config: InternalAxiosRequestConfig) {
  const agentIP = connectorContext.ctx?.value.agentIP;

  // 如果没有设置后端地址，直接返回
  if (!agentIP) {
    return config;
  }

  // 检测当前页面协议
  const isHTTPS = window.location.protocol === 'https:';

  if (isHTTPS) {
    // HTTPS环境：使用nginx代理模式
    // 通过请求头告诉nginx转发到哪个后端
    const [ip, port = '50080'] = agentIP.split(':');
    config.headers = config.headers || {};
    config.headers['X-Backend-Host'] = ip;
    config.headers['X-Backend-Port'] = port;

    // 使用相对路径，让nginx代理处理
    // config.url 保持不变，使用相对路径 /rpc/xxx
  } else {
    // HTTP环境：直接连接模式
    if (!config.url?.startsWith('http')) {
      let agentHost = agentIP;
      if (!agentHost.startsWith('http')) {
        agentHost = `http://${agentHost}`;
      }
      if (!/:[0-9]+$/gi.test(agentHost)) {
        agentHost += ':50080';
      }
      config.url = [agentHost, config.url].join('');
    }
  }

  return config;
}

export const updateTimerTickTimes = () => {
  connectorContext.ctx!.value.timeTickTimes++;
};

// 当顶层定时器周期一轮或者页面首次打开都会触发
export const onTimerTick = (cb: () => void) => {
  watchEffect(() => {
    if (connectorContext.ctx?.value.timeTickTimes) {
      cb();
    }
  });
};

// 当链接Agent时出触发
export const onAgentConnected = (cb: () => void) => {
  watchEffect(() => {
    if (connectorContext.ctx?.value.connectionStatus === ConnectionStatus.Connected) {
      cb();
    }
  });
};
