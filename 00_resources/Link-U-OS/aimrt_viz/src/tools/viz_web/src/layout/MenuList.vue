<template>
  <div class="h-full flex flex-col relative px-2">
    <ElMenu
      class="h-full pt-4 custom-menu !border-none !bg-transparent"
      router
      :default-active="route?.meta?.menuKey as string ?? route.path"
      :collapse="isCollapse"
    >
      <ElMenuItem index="/system">
        <template #default>
          <el-icon><House /></el-icon>
          <span class="inline-block pr-24">System</span>
        </template>
      </ElMenuItem>
      <ElMenuItem index="/node">
        <template #default>
          <el-icon><Coin /></el-icon>
          <span>Node</span>
        </template>
      </ElMenuItem>
      <ElMenuItem index="/rpc">
        <template #default>
          <el-icon><Connection /></el-icon>
          <span>RPC</span>
        </template>
      </ElMenuItem>
      <ElMenuItem index="/channel">
        <template #default>
          <el-icon><Operation /></el-icon>
          <span>Channel</span>
        </template>
      </ElMenuItem>
    </ElMenu>
    <div class="absolute bottom-0 right-0 w-full">
      <ElButton text size="large" class="w-full !justify-center" @click="toggle">
        <ElIcon>
          <DArrowRight v-if="isCollapse" />
          <DArrowLeft v-else />
        </ElIcon>
        <span v-if="!isCollapse">收起</span>
      </ElButton>
    </div>
  </div>
</template>
<script setup lang="tsx">
import { ElMenu, ElMenuItem, ElIcon, ElButton } from 'element-plus';
import { House, Connection, Operation, Coin, DArrowLeft, DArrowRight } from '@element-plus/icons-vue';
import { useRoute } from 'vue-router';
import { useStorage } from '@vueuse/core';
const route = useRoute();

const isCollapse = useStorage('MENULIST_ISCOLLAPSE', false); // 缓存该操作
function toggle() {
  isCollapse.value = !isCollapse.value;
}
</script>

<style lang="scss" scoped>
.custom-menu {
  :deep(.el-menu-item) {
    border-left: 4px solid transparent;

    border-style: none;

    color: #000000;
    border-radius: 8px;
    margin-bottom: 8px !important;
    height: 44px;
    font-weight: 400;
  }
  :deep(.el-menu-item.is-active) {
    background-color: #e2e8f0;
    border-style: none;
    color: black;
  }
  :deep(.el-menu-item:hover) {
    background-color: #e2e8f0;
    color: black;
  }
}
</style>
