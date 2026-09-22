<template>
  <div class="page-container">
    <h3 class="descriptions-title">Channel 列表</h3>

    <!-- 搜索区域 -->
    <div class="search-area">
      <el-input v-model="searchParams.topic_name" placeholder="搜索话题名称..." clearable class="search-input">
        <template #prefix>
          <el-icon>
            <Search />
          </el-icon>
        </template>
      </el-input>
      <el-input v-model="searchParams.msg_type" placeholder="搜索消息类型..." clearable class="search-input">
        <template #prefix>
          <el-icon>
            <Search />
          </el-icon>
        </template>
      </el-input>

      <el-select v-model="searchParams.backend" placeholder="后端类型" clearable class="filter-select">
        <el-option v-for="item in backendOptions" :key="item" :label="item" :value="item" />
      </el-select>

      <el-select v-model="searchParams.filter" placeholder="过滤器" clearable class="filter-select">
        <el-option v-for="item in filterOptions" :key="item" :label="item" :value="item" />
      </el-select>
    </div>

    <!-- 信息表格 -->
    <div v-if="(chnIndexInfo?.channel_index_dynamic_info?.dynamic_info_meta?.length ?? 0) > 0">
      <el-table
        :data="currentPageData"
        style="width: 100%"
        stripe
        class="descriptions-table"
        show-overflow-tooltip
        @sort-change="handleSortChange"
      >
        <el-table-column type="index" label="序号" min-width="5%" />
        <el-table-column prop="topic_name" label="话题名/消息类型" min-width="35%" sortable="custom">
          <template #default="scope">
            <span class="clickable-cell" @click="viewChannelDetail(scope.row.topic_name, scope.row.msg_type)">
              <span style="color: #409eff">{{ scope.row.topic_name }}</span>
              <span style="color: #a1a1a1">/</span>
              <span style="color: #67c23a">{{ scope.row.msg_type }}</span>
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="backend_name" label="后端" min-width="15%" sortable="custom">
          <template #default="{ row }">
            <TagList :list="row.backend_name" display="wrap" color-scheme="peach" />
          </template>
        </el-table-column>
        <el-table-column prop="filter_name" label="过滤器" min-width="15%" sortable="custom">
          <template #default="{ row }">
            <TagList :list="row.filter_name" />
          </template>
        </el-table-column>
        <el-table-column prop="pub_count" label="发布数" min-width="7%" sortable="custom" />
        <el-table-column prop="pub_frequency" label="发布频率/Hz" min-width="10%" sortable="custom">
          <template #default="scope">
            <span> {{ scope.row.pub_frequency.toFixed(3) }} </span>
          </template>
        </el-table-column>
        <el-table-column prop="sub_count" label="订阅数" min-width="7%" sortable="custom" />

        <el-table-column prop="sub_frequency" label="订阅频率/Hz" min-width="10%" sortable="custom">
          <template #default="scope">
            <span> {{ scope.row.sub_frequency.toFixed(3) }} </span>
          </template>
        </el-table-column>
      </el-table>
      <!-- 无匹配结果提示 -->
      <el-empty v-if="filteredTableData.length === 0" description="没有匹配的搜索结果" class="content-empty" />
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
    <!-- 信息表格 -->
  </div>
</template>

<script setup lang="ts">
import { ElPagination, ElEmpty, ElTable, ElTableColumn, ElInput, ElSelect, ElOption, ElIcon } from 'element-plus';
import { Search } from '@element-plus/icons-vue';
import TagList from '@/components/TagList.vue';
import { useViewModel } from './Index.vm';
import { useNPageJump } from '@/hooks/usePageJump';
import type { DynamicInfoMeta } from './Index';
import { useSortedPagination } from '@/hooks/useSortedPagination';
import { watch } from 'vue';

const [{ chnIndexInfo, searchParams, backendOptions, filterOptions, filteredTableData }, {}] = useViewModel();
const { viewChannelDetail } = useNPageJump();
const { currentPage, pageSize, currentPageData, sortedData, handleSortChange, handleSizeChange, handleCurrentChange } =
  useSortedPagination<DynamicInfoMeta>(filteredTableData, {
    defaultSortField: 'topic_name',
    defaultPageSize: 10
  });

watch(
  searchParams,
  () => {
    handleCurrentChange(1);
  },
  { deep: true }
);
</script>
