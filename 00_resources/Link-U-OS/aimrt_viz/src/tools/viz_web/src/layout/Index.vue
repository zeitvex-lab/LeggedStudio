<template>
  <div class="w-screen h-screen">
    <ConnectorContextProvider>
      <ElContainer class="w-full h-full">
        <ElHeader class="border-b-1 border-b-solid border-b-slate-300 bg-sky-900" height="74px">
          <Header></Header>
        </ElHeader>
        <ElContainer class="min-h-0">
          <ElAside class="!w-auto bg-slate-50" v-if="showAside"> <MenuList></MenuList> </ElAside>
          <ElMain>
            <div class="h-full flex flex-col">
              <Breadcrumb></Breadcrumb>
              <div ref="scrollContainer" class="flex-1 overflow-auto">
                <router-view></router-view>
              </div>
            </div>
          </ElMain>
        </ElContainer>
      </ElContainer>
    </ConnectorContextProvider>
  </div>
</template>
<script lang="ts" setup>
import { ElContainer, ElHeader, ElAside, ElMain } from 'element-plus';
import Header from './header/Header.vue';
import Breadcrumb from './Breadcrumb.vue';
import MenuList from './MenuList.vue';
import { computed, watch, nextTick, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ConnectorContextProvider } from '@/contexts/ConnectorContext';

const route = useRoute();
const scrollContainer = ref<HTMLElement>();
const showAside = computed(() => {
  if (route.meta.showMenuList === false) {
    return true;
  }
  return true;
});

watch(
  () => route.path,
  () => {
    nextTick(() => {
      if (scrollContainer.value) {
        scrollContainer.value.scrollTop = 0;
      }
    });
  }
);
</script>
