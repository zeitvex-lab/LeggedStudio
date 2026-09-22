<template>
  <span class="tag-list" :class="[`tag-list--${display}`, { 'tag-list--with-separator': separator }]">
    <template v-for="(item, index) in normalizedList" :key="index">
      <span class="tag-item" :class="{ 'tag-item--plain': plain }" :style="getTagStyle(String(item))">
        {{ item }}
      </span>
      <span v-if="separator && index !== normalizedList.length - 1" class="separator">{{ separator }}</span>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

type DisplayMode = 'inline' | 'wrap' | 'block';

const colorSchemes = {
  // 紫色系
  lavender: { bg: '#f5f0ff', border: '#d6c8ff', text: '#8c4eff' },
  purple: { bg: '#f9f0ff', border: '#d3adf7', text: '#722ed1' },
  violet: { bg: '#f4f0ff', border: '#b8a5ff', text: '#6b35e8' },

  // 柔和色系
  mint: { bg: '#e8faf0', border: '#98e6c0', text: '#00b578' },
  sky: { bg: '#e8f7ff', border: '#8fd4ff', text: '#0aa5ff' },
  peach: { bg: '#fff5f0', border: '#ffc4a8', text: '#ff7d41' },

  // 中性色系
  indigo: { bg: '#f0f5ff', border: '#85a5ff', text: '#2f54eb' },
  gray: { bg: '#fafafa', border: '#d9d9d9', text: '#8c8c8c' },
  slate: { bg: '#f0f5ff', border: '#adc6ff', text: '#597ef7' },

  // 蓝色系
  blue: { bg: '#ecf5ff', border: '#d9ecff', text: '#409eff' },
  deepBlue: { bg: '#e8f1ff', border: '#b4d2ff', text: '#1867dc' },
  lightBlue: { bg: '#e6f7ff', border: '#b8e7ff', text: '#0998d5' },

  // 红色系
  red: { bg: '#fff1f0', border: '#ffa39e', text: '#f5222d' },
  rose: { bg: '#fff0f6', border: '#ffadd2', text: '#eb2f96' },
  coral: { bg: '#fff2e8', border: '#ffbb96', text: '#fa541c' },

  // 暖色系
  gold: { bg: '#fffbe6', border: '#ffe58f', text: '#faad14' },
  amber: { bg: '#fff8e6', border: '#ffd666', text: '#d48806' },
  orange: { bg: '#fff7e6', border: '#ffd591', text: '#fa8c16' },

  // 绿色系
  green: { bg: '#f6ffed', border: '#b7eb8f', text: '#52c41a' },
  cyan: { bg: '#e6fffb', border: '#87e8de', text: '#13c2c2' },
  emerald: { bg: '#e6fff3', border: '#8fecc3', text: '#0ba360' }
} as const;

type ColorScheme = keyof typeof colorSchemes;

interface Props {
  list: (string | number)[];
  display?: DisplayMode;
  colorScheme?: ColorScheme;
  colorByContent?: boolean;
  plain?: boolean;
  separator?: string;
  useTextColor?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  display: 'wrap',
  colorScheme: 'blue',
  colorByContent: false,
  plain: false,
  separator: '',
  useTextColor: true
});

const normalizedList = computed(() => props.list.map(String));

const getTagStyle = (content: string) => {
  if (props.plain) {
    if (!props.useTextColor) {
      return {};
    }
    return { color: colorSchemes[props.colorScheme].text };
  }

  if (!props.colorByContent) {
    const color = colorSchemes[props.colorScheme];
    return {
      backgroundColor: color.bg,
      borderColor: color.border,
      color: color.text
    };
  }

  const schemes = Object.keys(colorSchemes) as ColorScheme[];
  const hash = content.split('').reduce((acc, char) => {
    return (acc << 5) - acc + char.charCodeAt(0);
  }, 0);
  const color = colorSchemes[schemes[Math.abs(hash) % schemes.length]];

  return {
    backgroundColor: color.bg,
    borderColor: color.border,
    color: color.text
  };
};
</script>

<style lang="scss" scoped>
.tag-list {
  display: inline-flex;
  gap: 8px;

  // 使用分割符时减少间距
  &--with-separator {
    gap: 0px;
  }

  &--inline {
    flex-wrap: nowrap;
    overflow: hidden;
  }

  &--wrap {
    flex-wrap: wrap;
  }

  &--block {
    flex-direction: column;
  }
}

.tag-item {
  display: inline-block;
  padding: 0 6px;
  font-size: 12px;
  border-radius: 4px;
  border-width: 1px;
  border-style: solid;
  white-space: nowrap;
  transition: all 0.2s;

  &--plain {
    background: transparent !important;
    border: none !important;
  }
}

.separator {
  margin: 0 1px;
  color: #8c8c8c;
  font-size: 12px;
}
</style>
