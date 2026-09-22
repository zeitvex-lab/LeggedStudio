<template>
  <div class="pb-2 mb-2 border-b-1 border-b-solid border-b-stone-300">
    <div class="w-full flex">
      <div class="flex-1">
        <ElBreadcrumb class="!text-base">
          <ElBreadcrumbItem
            v-for="(item, index) in breadCrumbData"
            :key="index"
            :to="index === breadCrumbData.length - 1 ? undefined : { path: item.path }"
            :class="{ 'current-page': index === breadCrumbData.length - 1 }"
          >
            {{ item.name }}
          </ElBreadcrumbItem>
        </ElBreadcrumb>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElBreadcrumb, ElBreadcrumbItem } from 'element-plus';
import { computed } from 'vue';
import { useRoute, useRouter, type RouteParamsRaw } from 'vue-router';

interface BreadCrumbItem {
  name: string;
  path: string;
}

const route = useRoute();
const router = useRouter();

// 解码并获取路径段名称
const getDecodedName = (path: string, isChannelRoute = false): string => {
  const segments = path.split('/').filter(Boolean);

  if (isChannelRoute && segments.length >= 3) {
    // Channel路由特殊处理：合并最后两个段
    const topic = decodeURIComponent(segments[segments.length - 2]);
    const msgType = decodeURIComponent(segments[segments.length - 1]);
    return `${topic}/${msgType}`;
  }

  return decodeURIComponent(segments.pop() || '');
};

// 构建父级面包屑参数
const buildParentParams = (parentRoute: any): RouteParamsRaw => {
  return parentRoute.path
    .split('/')
    .filter((segment: string) => segment.startsWith(':'))
    .reduce((params: RouteParamsRaw, param: string) => {
      const key = param.slice(1);
      const value = route.params[key];
      if (typeof value === 'string') params[key] = value;
      return params;
    }, {});
};

const breadCrumbData = computed<BreadCrumbItem[]>(() => {
  const items: BreadCrumbItem[] = [];

  for (const [index, matched] of route.matched.entries()) {
    const { title, breadcrumbParent } = matched.meta || {};

    // 跳过 root 和无标题路由
    if (!title || title === 'root') continue;

    // 处理父级面包屑
    if (breadcrumbParent) {
      const parentRoute = router.getRoutes().find((r) => r.name === breadcrumbParent);
      if (parentRoute?.path) {
        const parentParams = buildParentParams(parentRoute);
        const parentPath = router.resolve({
          name: breadcrumbParent as string,
          params: parentParams
        }).path;

        items.push({
          name: getDecodedName(parentPath),
          path: parentPath
        });
      }
    }

    // 添加当前级别面包屑
    const currentPath =
      index === 1 ? matched.path : router.resolve({ name: matched.name as string, params: route.params }).path;

    const isChannelRoute = currentPath.toLowerCase().includes('/channel/');

    items.push({
      name: getDecodedName(currentPath, isChannelRoute),
      path: currentPath
    });
  }

  return items;
});
</script>

<style scoped>
.current-page {
  background-color: #f5f5f5;
  font-style: italic;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
