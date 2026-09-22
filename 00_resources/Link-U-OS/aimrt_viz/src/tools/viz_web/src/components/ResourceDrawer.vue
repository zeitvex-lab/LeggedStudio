<template>
  <div class="config-detail">
    <div class="header">
      <h3>{{ title }}</h3>
      <div class="actions">
        <el-select v-model="format" size="small" style="width: 100px" :disabled="loading">
          <el-option label="YAML" value="yaml" />
          <el-option label="JSON" value="json" />
          <el-option label="Shell" value="bash" />
          <el-option label="Text" value="plaintext" />
          <el-option label="Protobuf" value="protobuf" />
        </el-select>
        <el-button size="small" :icon="CopyDocumentIcon" :disabled="loading || !formattedValue" @click="handleCopy">
          复制
        </el-button>
        <el-button size="small" :loading="loading" @click="fetchData">刷新</el-button>
      </div>
    </div>

    <el-card>
      <div v-if="error" class="error-message">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ error }}</span>
      </div>
      <HighlightItem v-else-if="formattedValue" :lang="format" :text="formattedValue" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ElCard, ElButton, ElSelect, ElOption, ElMessage, ElIcon } from 'element-plus';
import { CopyDocument as CopyDocumentIcon, WarningFilled } from '@element-plus/icons-vue';
import HighlightItem from '@/components/HighlightItem.vue';
import { GetResource } from '@/apis/system';

const props = withDefaults(
  defineProps<{
    title: string;
    uuid: number;
    defaultLang?: string;
  }>(),
  { defaultLang: 'yaml' }
);

const loading = ref(false);
const error = ref('');
const decodedContent = ref('');
const format = ref(props.defaultLang);

// 获取数据
const fetchData = async () => {
  if (!props.uuid) {
    error.value = '无效资源标识符';
    return;
  }

  loading.value = true;
  error.value = '';

  try {
    const response = await GetResource({ resource_id: props.uuid });

    if (response?.data?.data) {
      decodedContent.value = atob(response.data.data);
    } else {
      throw new Error('数据为空');
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '获取数据失败';
    decodedContent.value = '';
  } finally {
    loading.value = false;
  }
};

// 格式化内容
const formattedValue = computed(() => {
  if (!decodedContent.value) return '';

  if (format.value === 'json') {
    try {
      return JSON.stringify(JSON.parse(decodedContent.value), null, 2);
    } catch {
      return decodedContent.value;
    }
  }

  return decodedContent.value;
});

// 原生复制功能
const handleCopy = async () => {
  if (!formattedValue.value) {
    ElMessage.warning('没有可复制的内容');
    return;
  }

  try {
    // 优先使用现代 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(formattedValue.value);
    } else {
      // 降级到传统方法
      const textArea = document.createElement('textarea');
      textArea.value = formattedValue.value;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
    }

    ElMessage.success('已复制到剪贴板');
  } catch (err) {
    console.error('复制失败:', err);
    ElMessage.error('复制失败，请手动选择复制');
  }
};

onMounted(fetchData);
</script>

<style scoped>
.config-detail {
  min-height: 100px;
  padding: 10px;
  border-radius: 4px;
  background-color: #f9fafb;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #555d64;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border-radius: 4px;
  color: #f56c6c;
}
</style>
