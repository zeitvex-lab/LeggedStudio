<template>
  <div class="page-container">
    <h3 class="descriptions-title">在线节点列表</h3>

    <!-- 搜索区域 -->
    <div class="search-area">
      <el-input v-model="searchQuery" placeholder="搜索节点名称..." clearable class="search-input">
        <template #prefix>
          <el-icon>
            <Search />
          </el-icon>
        </template>
      </el-input>

      <el-select v-model="socFilter" placeholder="SoC型号" clearable class="filter-select">
        <el-option v-for="item in socOptions" :key="item" :label="item" :value="item" />
      </el-select>

      <el-select v-model="onlineStatusFilter" placeholder="在线状态" class="filter-select">
        <el-option label="全部" value="all" />
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
      </el-select>
    </div>

    <!-- 信息表格 -->
    <div v-if="nodeList.length > 0">
      <el-table
        :data="currentPageData"
        @sort-change="handleSortChange"
        style="width: 100%"
        stripe
        class="descriptions-table"
        show-overflow-tooltip
      >
        <el-table-column type="index" label="序号" min-width="6%" />
        <el-table-column label="节点名称" min-width="14%" prop="static_info.node_name" sortable="custom">
          <template #default="scope">
            <span
              :class="{
                'clickable-cell': scope.row.dynamic_info.online_time_s >= 0,
                'disabled-cell': scope.row.dynamic_info.online_time_s === undefined
              }"
              @click="scope.row.dynamic_info.online_time_s > 0 ? viewNodeDetail(scope.row.static_info.node_name) : null"
            >
              {{ scope.row.static_info.node_name }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="在线时间" min-width="12%" prop="dynamic_info.online_time_s" sortable="custom">
          <template #default="scope">
            <OnlineStatus :seconds="scope.row.dynamic_info.online_time_s" />
          </template>
        </el-table-column>

        <el-table-column label="SoC型号" min-width="12%" prop="static_info.soc" sortable="custom">
          <template #default="scope">
            <TagList :list="[scope.row.static_info.soc]" display="inline" color-scheme="peach" />
          </template>
        </el-table-column>

        <el-table-column prop="static_info.pid" label="进程ID" min-width="12%" sortable="custom" />

        <el-table-column prop="static_info.server_num" label="服务端数" min-width="11%" sortable="custom" />

        <el-table-column prop="static_info.client_num" label="客户端数" min-width="11%" sortable="custom" />

        <el-table-column prop="static_info.pub_num" label="发布端数" min-width="11%" sortable="custom" />

        <el-table-column prop="static_info.sub_num" label="订阅端数" min-width="11%" sortable="custom" />
      </el-table>

      <!-- 无匹配结果提示 -->
      <el-empty v-if="sortedData.length === 0" description="没有匹配的搜索结果" class="content-empty" />

      <!-- 分页组件 -->
      <el-pagination
        v-if="sortedData.length > 0"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
        :current-page="currentPage"
        :page-sizes="[10, 20, 50, 100]"
        :page-size="pageSize"
        layout="total, sizes, prev, pager, next, jumper"
        background
        :total="sortedData.length"
        style="position: fixed; bottom: 40px; right: 20px; padding: 8px 15px"
      />
    </div>

    <el-empty v-else description="暂无节点数据" class="content-empty" />
  </div>
</template>

<script setup lang="ts">
import { ElEmpty, ElTable, ElTableColumn, ElInput, ElSelect, ElOption, ElIcon, ElPagination } from 'element-plus';
import { Search } from '@element-plus/icons-vue';
import { useSortedPagination } from '@/hooks/useSortedPagination';
import { useViewModel } from './Index.vm';
import type { NodeInfo } from './Index';
import TagList from '@/components/TagList.vue';
import { useNPageJump } from '@/hooks/usePageJump';
import OnlineStatus from '@/components/OnlineStatus.vue';
import { watch } from 'vue';

const { viewNodeDetail } = useNPageJump();
const [{ searchQuery, socFilter, socOptions, nodeList, filteredNodeList, onlineStatusFilter }, {}] = useViewModel();
const { currentPage, pageSize, currentPageData, sortedData, handleSortChange, handleSizeChange, handleCurrentChange } =
  useSortedPagination<NodeInfo>(filteredNodeList, {
    defaultSortField: 'static_info.node_name',
    defaultPageSize: 10
  });

watch([searchQuery, socFilter, onlineStatusFilter], () => {
  handleCurrentChange(1);
});
</script>
