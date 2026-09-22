<template>
  <span :class="statusClass">{{ displayText }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { formatOnlineTime } from '@/utils/format';
interface Props {
  seconds: number | undefined;
}

const props = defineProps<Props>();
const statusClass = computed(() => (props.seconds === undefined ? 'offline' : 'online'));
const displayText = computed(() => formatOnlineTime(props.seconds));
</script>

<style scoped>
.offline {
  color: #f56565; /* 红色 */
}

.online {
  color: #48bb78; /* 绿色 */
}
</style>
