<template>
  <div v-if="hasItems" class="two-column-list">
    <div v-for="(item, index) in displayItems" :key="index" class="list-item">
      <div class="item-content" :title="getItemTitle(item)">
        <span @click="handleClick(index, 'first')" class="column-item first-column">
          {{ item.first }}
        </span>
        <template v-if="hasTwoColumns && item.second !== undefined">
          <span class="separator">{{ connector }}</span>
          <span @click="handleClick(index, 'second')" class="column-item second-column">
            {{ item.second }}
          </span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface ItemSingle {
  first: string;
  second?: undefined;
  index: number;
}

interface ItemDouble {
  first: string;
  second: string;
  index: number;
}

type DisplayItem = ItemSingle | ItemDouble;

interface Props {
  /** 第一列数据 */
  firstColumn: string[];
  /** 第二列数据（可选） */
  secondColumn?: string[];
  /** 分隔符 */
  connector?: string;
}

const props = withDefaults(defineProps<Props>(), {
  connector: '/',
  firstColumn: () => [],
  secondColumn: () => []
});

const emit = defineEmits<{
  (e: 'select', column: 'first' | 'second', value1: string, value2?: string): void;
}>();

const hasItems = computed(() => props.firstColumn.length > 0);
const hasTwoColumns = computed(() => props.secondColumn && props.secondColumn.length > 0);

const displayItems = computed<DisplayItem[]>(() => {
  if (!hasItems.value) return [];

  // 只有一列数据
  if (!hasTwoColumns.value) {
    return props.firstColumn.map((item, index) => ({
      first: item,
      index
    }));
  }

  // 两列数据
  const minLength = Math.min(props.firstColumn.length, props.secondColumn!.length);
  return Array.from({ length: minLength }, (_, index) => ({
    first: props.firstColumn[index],
    second: props.secondColumn![index],
    index
  }));
});

const getItemTitle = (item: DisplayItem) => {
  return item.second !== undefined ? `${item.first}${props.connector}${item.second}` : item.first;
};

const handleClick = (index: number, column: 'first' | 'second') => {
  const item = displayItems.value[index];

  if (column === 'first') {
    emit('select', column, item.first, item.second);
  } else if (column === 'second' && 'second' in item && item.second !== undefined) {
    emit('select', column, item.first, item.second);
  }
};
</script>

<style scoped>
.two-column-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  list-style-type: none;
  padding: 0;
  margin: 0;
  width: 100%;
}

.list-item {
  list-style-type: none;
  white-space: normal;
  word-break: break-word;
  width: 100%;
}

.item-content {
  display: flex;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  flex-wrap: wrap;
}

.column-item {
  cursor: pointer;
  padding: 0;
  transition: background-color 0.2s;
  overflow: hidden;
  text-overflow: ellipsis;
}

.first-column {
  color: #5eb7ea;
}

.second-column {
  color: #e79e67;
}

.separator {
  margin: 0 4px;
  color: #e7ce60;
}
</style>
