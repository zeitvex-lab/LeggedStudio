<template>
  <div class="whitespace-nowrap">
    <ElAutocomplete
      v-model="ipAddress"
      clearable
      :fetch-suggestions="querySearch"
      placeholder="请输入Agent IP:PORT (如 127.0.0.1:8080)"
      size="large"
      @keyup.enter="connect"
      @select="handleSelect"
      @blur="handleBlur"
      class="w-64"
    ></ElAutocomplete>
    <!-- 状态显示，直接在标签中加颜色类 -->
    <span v-if="connectionStatus === ConnectionStatus.Connecting" class="ml-2 text-sm font-medium text-green-600">
      连接中...
    </span>
    <span v-else-if="connectionStatus === ConnectionStatus.Connected" class="ml-2 text-sm font-medium text-green-600">
      已连接
    </span>
    <span v-else class="ml-2 text-sm font-medium text-gray-500"> 未连接 </span>
  </div>
</template>

<script setup lang="ts">
import { useStorage } from '@vueuse/core';
import { ElAutocomplete, ElMessage } from 'element-plus';
import { ref, onMounted } from 'vue';
import { ConnectionStatus, connectorContext } from '@/contexts/ConnectorContext';
import { useContext } from '@/utils';
import { GetSystemInfo } from '@/apis/system';
import { useRoute, useRouter } from 'vue-router';

const connectionStatus = ref(ConnectionStatus.Disconnected);
const ipAddress = useStorage('agent-ip-current', '');
const historyList = useStorage<string[]>('agent-ip-history-list', []);
const MAX_IP_HISTORY = 3;
const connectorRuntimeData = useContext(connectorContext);
const route = useRoute();

// 初始化时尝试恢复连接
onMounted(() => {
  // 检查是否有URL参数中的IP和端口
  if (route.query.autoConnect === 'true' && route.query.ip && route.query.port) {
    const urlIp = route.query.ip as string;
    const urlPort = route.query.port as string;
    ipAddress.value = `${urlIp}:${urlPort}`;

    // 自动连接
    connect();

    // 清除URL中的查询参数（可选）
    const router = useRouter();
    router.replace({ query: {} });
  } else if (ipAddress.value) {
    connect();
  }
});

async function connect() {
  if (!ipAddress.value) {
    ElMessage({
      message: '请输入IP:端口地址',
      type: 'warning',
      duration: 3000,
      offset: 20, // 增加偏移量，避免挡住输入框
      customClass: 'header-message'
    });
    return;
  }

  const ipPortRegex = /^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})$/;
  if (!ipPortRegex.test(ipAddress.value)) {
    ElMessage({
      message: '请输入有效的 IP:端口 地址，例如 127.0.0.1:8080',
      type: 'error',
      duration: 4000,
      offset: 20,
      customClass: 'header-message'
    });
    return;
  }

  connectionStatus.value = ConnectionStatus.Connecting;
  connectorRuntimeData!.value.connectionStatus = ConnectionStatus.Connecting;
  connectorRuntimeData!.value.agentIP = ipAddress.value;

  try {
    const response = await GetSystemInfo();
    console.log('连接成功:', response.data);
    ElMessage({
      message: '连接成功',
      type: 'success',
      duration: 4000,
      offset: 20,
      customClass: 'header-message'
    });
    connectionStatus.value = ConnectionStatus.Connected;

    if (connectorRuntimeData?.value) {
      connectorRuntimeData.value.connectionStatus = ConnectionStatus.Connected;

      // 只在连接成功时更新历史记录
      const filteredHistory = historyList.value.filter((item) => item !== ipAddress.value);
      historyList.value = [ipAddress.value, ...filteredHistory].slice(0, MAX_IP_HISTORY);
    }
  } catch (error: any) {
    console.error('连接失败:', error);
    ElMessage({
      message: `连接失败: ${error.message || '请检查IP地址和网络'}`,
      type: 'error',
      duration: 4000,
      offset: 20,
      customClass: 'header-message'
    });

    connectionStatus.value = ConnectionStatus.Disconnected;
    ipAddress.value = connectorRuntimeData?.value.agentIP || ''; // 连接失败时恢复为上次连接的IP

    if (connectorRuntimeData?.value) {
      connectorRuntimeData.value.connectionStatus = ConnectionStatus.Disconnected;
    }
  }
}

const querySearch = (queryString: string, cb: (results: { value: string }[]) => void) => {
  const results = queryString
    ? historyList.value.filter(createFilter(queryString)).map((item) => ({ value: item }))
    : historyList.value.map((item) => ({ value: item }));
  cb(results);
};

const createFilter = (queryString: string) => {
  return (item: string) => {
    return item.toLowerCase().indexOf(queryString.toLowerCase()) !== -1;
  };
};

const handleSelect = (item: Record<string, any>) => {
  ipAddress.value = item.value;
  connect();
};

const handleBlur = () => {
  if (ipAddress.value !== connectorRuntimeData?.value.agentIP) {
    ipAddress.value = connectorRuntimeData?.value.agentIP || '';
  }
};
</script>
