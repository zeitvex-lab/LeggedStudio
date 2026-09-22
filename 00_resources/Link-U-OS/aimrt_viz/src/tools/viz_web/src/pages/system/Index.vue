<template>
  <div class="page-container">
    <div v-if="systemInfo">
      <h3 class="descriptions-title">基本信息</h3>
      <el-descriptions :column="1" class="descriptions-item">
        <el-descriptions-item label="名称：">{{ systemInfo?.static_info?.name }}</el-descriptions-item>
        <el-descriptions-item label="版本：">{{ systemInfo?.static_info?.aimrt_viz_version }}</el-descriptions-item>
      </el-descriptions>
      <!-- 属性列表-->

      <h3 class="descriptions-title">其他信息</h3>
      <el-descriptions :column="1" class="descriptions-item" v-if="attributesList.length > 0 && hasAttributes">
        <el-descriptions-item v-for="item in attributesList" :key="item.key" :label="item.key + '：'">
          {{ item.value }}
        </el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="暂无其他信息" />
    </div>
    <el-empty v-else description="暂无系统数据" />
  </div>
</template>

<script setup lang="ts">
import { ElEmpty, ElDescriptions, ElDescriptionsItem } from 'element-plus';
import { useViewModel } from './Index.vm';
const [{ hasAttributes, attributesList, systemInfo }, {}] = useViewModel();
</script>
