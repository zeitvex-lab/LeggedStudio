<template>
  <ElDropdown
    split-button
    @command="onSelect"
    @click="submit"
    :disabled="connectorRuntimeData!.connectionStatus === ConnectionStatus.Disconnected"
  >
    <span>
      <span>刷新</span>
      <span class="inline-block">{{ currDurationDesc }}</span>
    </span>
    <template #dropdown>
      <p class="text-sm text-neutral-600 p-1 border-b-1 border-b-solid border-b-slate-200">刷新频率</p>
      <el-dropdown-menu>
        <el-dropdown-item v-for="(item, index) in list" :command="index">{{ item.label }}</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </ElDropdown>
</template>

<script setup lang="ts">
import { ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus';
import { computed, onMounted, onUnmounted, ref, defineEmits } from 'vue';
import { ConnectionStatus, connectorContext } from '@/contexts/ConnectorContext';
import { useContext } from '@/utils';

const connectorRuntimeData = useContext(connectorContext);
const emit = defineEmits(['refresh']);
const list = [
  {
    duration: 0,
    label: 'OFF',
    disabled: true
  },
  {
    duration: 1,
    label: '1s'
  },
  {
    duration: 2,
    label: '2s'
  },
  {
    duration: 3,
    label: '3s'
  },
  {
    duration: 5,
    label: '5s'
  },
  {
    duration: 10,
    label: '10s'
  }
];
const selectedIndex = ref(4);
const currDuration = ref<number>(list[selectedIndex.value].duration);
const currDurationDesc = computed(() => {
  let targetConf = list[selectedIndex.value];
  if (targetConf.disabled) {
    return '';
  } else {
    return `${currDuration.value}s`;
  }
});

const timer = ref<any>(null);

function initTimer() {
  clearTimer();
  const maxDuration = list[selectedIndex.value].duration;

  currDuration.value = maxDuration;

  if (maxDuration <= 0) {
    return;
  }
  timer.value = setInterval(() => {
    let nextTs = currDuration.value - 1;
    if (nextTs < 0) {
      submit();
    } else {
      currDuration.value = nextTs;
    }
  }, 1000);
}
function submit() {
  emit('refresh');
  initTimer();
}

function clearTimer() {
  clearInterval(timer.value);
  timer.value = null;
}

function onSelect(idx: number) {
  selectedIndex.value = idx;
  initTimer();
}

onMounted(() => {
  initTimer();
});

onUnmounted(() => {
  clearTimer();
});
</script>
