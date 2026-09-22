<template>
  <div class="topology-graph" ref="container">
    <el-card class="node" :id="`source-${uniqueId}`" shadow="hover">
      <template #header>
        <div class="node-header">{{ sourceTitle }}</div>
      </template>
      <el-table :data="sourceData" style="width: 100%" size="small">
        <el-table-column label="节点名" min-width="25%">
          <template #default="scope">
            <span class="clickable-cell" @click="handleClick(scope.row, 'first')">
              {{ scope.row.node_name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="模块名" min-width="50%">
          <template #default="scope">
            <span class="clickable-cell" @click="handleClick(scope.row, 'second')">
              {{ scope.row.module_name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="filter_name" label="过滤器" min-width="35%">
          <template #default="scope">
            <TagList :list="scope.row.filter_name" colorScheme="indigo" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="node" :id="`target-${uniqueId}`" shadow="hover">
      <template #header>
        <div class="node-header">{{ targetTitle }}</div>
      </template>
      <el-table :data="targetData" style="width: 100%" size="small">
        <el-table-column prop="node_name" label="节点名" min-width="25%">
          <template #default="scope">
            <span class="clickable-cell" @click="handleClick(scope.row, 'first')">
              {{ scope.row.node_name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="module_name" label="模块名" min-width="50%">
          <template #default="scope">
            <span class="clickable-cell" @click="handleClick(scope.row, 'second')">
              {{ scope.row.module_name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="filter_name" label="过滤器" min-width="35%">
          <template #default="scope">
            <TagList :list="scope.row.filter_name" colorScheme="indigo" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, onBeforeUnmount, computed, watch, nextTick } from 'vue';
import { jsPlumb } from 'jsplumb';
import { ElCard, ElTable, ElTableColumn } from 'element-plus';
import TagList from './TagList.vue';

export interface NodeData {
  node_name: string;
  module_name: string;
  filter_name: string[];
}

export type TopologyType = 'rpc' | 'channel';

const props = defineProps<{
  type: TopologyType;
  sourceData: NodeData[];
  targetData: NodeData[];
}>();

const emit = defineEmits<{
  (e: 'select', column: 'first' | 'second', value1: string, value2: string): void;
}>();

const uniqueId = Math.random().toString(36).substring(2, 15);
const container = ref(null);
let jsp: any = null;

const sourceTitle = computed(() => (props.type === 'rpc' ? '客户端' : '发布端'));
const targetTitle = computed(() => (props.type === 'rpc' ? '服务端' : '订阅端'));

const handleClick = (data: NodeData, column: 'first' | 'second') => {
  emit('select', column, data.node_name, data.module_name);
};

const repaint = () => jsp?.repaintEverything();

const initConnection = () => {
  if (!jsp) return;

  jsp.deleteEveryConnection();
  jsp.deleteEveryEndpoint();

  const endpoint = {
    endpoint: ['Dot', { radius: 1 }],
    paintStyle: { fill: '#409eff' },
    connectorStyle: { stroke: '#409eff', strokeWidth: 2 },
    connector: ['Straight'],
    maxConnections: -1,
    isSource: true,
    isTarget: true
  };

  jsp.addEndpoint(`source-${uniqueId}`, { anchor: [1, 0.5], ...endpoint, uuid: `source-${uniqueId}` });
  jsp.addEndpoint(`target-${uniqueId}`, { anchor: [0, 0.5], ...endpoint, uuid: `target-${uniqueId}` });

  const overlays =
    props.type === 'rpc'
      ? [
          ['Arrow', { location: 1, width: 16, length: 16 }],
          ['Arrow', { location: 0, width: 16, length: 16, direction: -1 }]
        ]
      : [['Arrow', { location: 1, width: 16, length: 16 }]];

  jsp.connect({
    uuids: [`source-${uniqueId}`, `target-${uniqueId}`],
    paintStyle: { stroke: '#409eff', strokeWidth: 2 },
    overlays
  });
};

watch([() => props.sourceData, () => props.targetData], () => nextTick(repaint), { deep: true });

onMounted(() => {
  jsp = jsPlumb.getInstance({ Container: container.value });
  nextTick(initConnection);

  window.addEventListener('resize', repaint);
  const observer = new ResizeObserver(repaint);
  observer.observe(container.value!);
  (container.value as any).__observer = observer;
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', repaint);
  (container.value as any)?.__observer?.disconnect();
  jsp?.destroy();
});
</script>

<style scoped lang="scss">
.topology-graph {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 100px;
  padding: 6px;
  min-height: 260px;
  background: #f5f7fa;
  border-radius: 8px;
  position: relative;
  margin: 10px 0;
}

.node {
  width: 44%;
  position: relative;
  border-radius: 20px;
  overflow: hidden;
  margin-top: 24px;
  margin-bottom: 24px;

  min-height: 200px;

  &:hover {
    transform: translateY(-15px);
  }

  :deep(.el-card__header) {
    padding: 12px 16px;
    .node-header {
      font-size: 15px;
      font-weight: 600;
      color: #474746;
    }
  }

  :deep(.el-table) {
    &::before,
    &::after {
      display: none;
    }

    .el-table__header th {
      font-size: 14px;
      font-weight: bold;
      color: #ffffff;
      background-color: #41a9c9;
      border: none;
      padding: 8px;
      border-bottom: 3px solid #ffffff;

      &:first-child {
        border-top-left-radius: 8px;
        border-bottom-left-radius: 8px;
      }
      &:last-child {
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
      }
    }

    .el-table__body {
      td {
        font-size: 12px;
        font-weight: 400;
        color: #174d75;
        background-color: #e5f0f8;
        padding: 8px;
        border: none;
        border-bottom: 3px solid #ffffff;

        &:first-child {
          border-top-left-radius: 8px;
          border-bottom-left-radius: 8px;
        }
        &:last-child {
          border-top-right-radius: 8px;
          border-bottom-right-radius: 8px;
        }
      }

      tr:last-child td {
        border-bottom: none;
      }
      tr {
        background-color: transparent;
        margin-bottom: 4px;
        &:hover > td {
          background-color: #b0e9f8;
        }
      }
    }
  }
}
</style>
