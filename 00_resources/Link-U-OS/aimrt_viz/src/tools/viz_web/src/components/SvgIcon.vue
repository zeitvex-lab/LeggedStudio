<template>
  <img :src="url" class="w-4 h-4" alt="" />
</template>
<script lang="ts" setup>
import { defineProps, ref } from 'vue';

const props = defineProps(['name']);
const url = ref('');
// 获取 SVG 的 URL 路径
try {
  const svgModules = import.meta.glob('@/assets/icon/*.svg', {
    import: 'default',
    eager: true
  });
  // 转换为名称到 URL 的映射
  const icons = Object.entries(svgModules).reduce((acc: { [key: string]: any }, [path, url]) => {
    const name = path.split('/').pop()?.replace('.svg', '');
    name ? (acc[name] = url) : void 0;
    return acc;
  }, {});
  url.value = icons[props.name];
} catch (error) {
  console.error('SVG 加载失败:', error);
}
</script>
