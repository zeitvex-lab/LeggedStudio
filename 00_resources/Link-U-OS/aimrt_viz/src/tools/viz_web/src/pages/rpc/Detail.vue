<template>
  <div class="page-container">
    <MyDrawer></MyDrawer>
    <div v-if="rpcDetailInfo">
      <!-- 基本信息部分-->

      <h3 class="descriptions-title">基本信息</h3>
      <el-descriptions :column="1" class="descriptions-item">
        <el-descriptions-item label="名称：">
          {{ rpcDetailInfo?.rpc_detail_static_info.base_info.func_name }}
        </el-descriptions-item>
        <el-descriptions-item label="请求类型：">
          <template #default>
            <span
              class="clickable-cell"
              @click="
                openResourceDrawer(
                  '请求消息类型',
                  rpcDetailInfo!.rpc_detail_static_info.base_info.request_schema_id,
                  'protobuf'
                )
              "
            >
              {{ rpcDetailInfo?.rpc_detail_static_info.base_info.request_type }}
            </span>
          </template>
        </el-descriptions-item>
        <el-descriptions-item label="响应类型：">
          <template #default>
            <span
              class="clickable-cell"
              @click="
                openResourceDrawer(
                  '响应消息类型',
                  rpcDetailInfo!.rpc_detail_static_info.base_info.response_schema_id,
                  'protobuf'
                )
              "
            >
              {{ rpcDetailInfo?.rpc_detail_static_info.base_info.response_type }}
            </span>
          </template>
        </el-descriptions-item>
        <el-descriptions-item label="所有使用的后端：">
          <TagList
            :list="rpcDetailInfo?.rpc_detail_static_info?.base_info?.backend_name ?? []"
            display="wrap"
            color-scheme="peach"
          />
        </el-descriptions-item>
        <el-descriptions-item label="所有使用的过滤器：">
          <TagList
            :list="rpcDetailInfo?.rpc_detail_static_info?.base_info?.filter_name ?? []"
            display="wrap"
            color-scheme="deepBlue"
          />
        </el-descriptions-item>
      </el-descriptions>

      <!-- Rpc请求状态部分-->
      <h3 class="descriptions-title">Rpc 请求状态</h3>
      <div style="margin-bottom: 36px">
        <div class="bordered-box">
          <h4 class="descriptions-sub-title">客户端信息</h4>
          <el-descriptions
            :column="1"
            class="descriptions-item"
            v-if="rpcDetailInfo?.rpc_detail_dynamic_info.client_info.module_infos.length ?? 0 > 0"
          >
            <!--当前状态信息-->
            <el-descriptions-item label="当前状态：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="QPS：">
                  {{
                    rpcDetailInfo?.rpc_detail_dynamic_info?.client_info?.current_status?.qps ?? 0
                  }}</el-descriptions-item
                >
                <el-descriptions-item label="错误率："> {{ client_error_rate }}</el-descriptions-item>
              </el-descriptions>
            </el-descriptions-item>

            <el-descriptions-item label="历史统计：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="累计请求：">
                  {{
                    rpcDetailInfo?.rpc_detail_dynamic_info?.client_info?.history_stats?.seq_num ?? 0
                  }}</el-descriptions-item
                >
                <el-descriptions-item label="失败次数：">
                  {{ rpcDetailInfo?.rpc_detail_dynamic_info?.client_info?.history_stats?.error_count ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
            </el-descriptions-item>
          </el-descriptions>

          <!--状态表-->
          <el-table
            :data="rpcDetailInfo?.rpc_detail_dynamic_info.client_info.module_infos"
            style="width: 100%"
            stripe
            class="descriptions-table"
            v-if="rpcDetailInfo?.rpc_detail_dynamic_info.client_info.module_infos.length ?? 0 > 0"
          >
            <el-table-column type="index" label="序号" min-width="5%" />
            <el-table-column label="节点名称" min-width="20%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewNodeDetail(scope.row.node_name)">
                  {{ scope.row.node_name }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label=" 模块名称" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewModuleDetail(scope.row.node_name, scope.row.module_name)">
                  {{ scope.row.module_name }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label="后端" min-width="15%">
              <template #default="{ row }">
                <TagList :list="row.backend_name" display="wrap" color-scheme="peach" />
              </template>
            </el-table-column>

            <el-table-column label="过滤器" min-width="15%">
              <template #default="{ row }">
                <TagList :list="row.filter_name" display="wrap" color-scheme="deepBlue" />
              </template>
            </el-table-column>

            <el-table-column prop="qps" label="QPS" min-width="15%" />
          </el-table>
          <el-empty v-else description="无客户端信息"></el-empty>
        </div>

        <div class="bordered-box">
          <h4 class="descriptions-sub-title">服务端信息</h4>
          <el-descriptions
            :column="1"
            class="descriptions-item"
            v-if="rpcDetailInfo?.rpc_detail_dynamic_info.server_info.module_infos.length ?? 0 > 0"
          >
            <el-descriptions-item label="当前状态：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="QPS：">
                  {{
                    rpcDetailInfo?.rpc_detail_dynamic_info?.server_info?.current_status?.qps ?? 0
                  }}</el-descriptions-item
                >
                <el-descriptions-item label="错误率："> {{ server_error_rate }}</el-descriptions-item>
              </el-descriptions>
            </el-descriptions-item>

            <el-descriptions-item label="历史统计：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="累计响应：">
                  {{
                    rpcDetailInfo?.rpc_detail_dynamic_info?.server_info?.history_stats?.seq_num ?? 0
                  }}</el-descriptions-item
                >
                <el-descriptions-item label="失败次数：">
                  {{ rpcDetailInfo?.rpc_detail_dynamic_info?.server_info?.history_stats?.error_count ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
            </el-descriptions-item>
          </el-descriptions>

          <el-table
            :data="rpcDetailInfo?.rpc_detail_dynamic_info.server_info.module_infos"
            style="width: 100%"
            stripe
            class="descriptions-table"
            v-if="rpcDetailInfo?.rpc_detail_dynamic_info.server_info.module_infos.length ?? 0 > 0"
          >
            <el-table-column type="index" label="序号" min-width="5%" />
            <el-table-column label="节点名称" min-width="20%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewNodeDetail(scope.row.node_name)">
                  {{ scope.row.node_name }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label=" 模块名称" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewModuleDetail(scope.row.node_name, scope.row.module_name)">
                  {{ scope.row.module_name }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label="后端" min-width="15%">
              <template #default="{ row }">
                <TagList :list="row.backend_name" display="wrap" color-scheme="peach" />
              </template>
            </el-table-column>

            <el-table-column label="过滤器" min-width="15%">
              <template #default="{ row }">
                <TagList :list="row.filter_name" display="wrap" color-scheme="deepBlue" />
              </template>
            </el-table-column>

            <el-table-column prop="qps" label="QPS" min-width="15%" />
          </el-table>
          <el-empty v-else description="无服务端信息"></el-empty>
        </div>
      </div>

      <!-- Rpc请求关系部分-->
      <h3 class="descriptions-title">Rpc 请求关系</h3>
      <div style="margin-bottom: 36px" v-if="rpcDetailInfo.rpc_detail_dynamic_info.endpoint_info.length > 0">
        <span v-for="item in rpcDetailInfo?.rpc_detail_dynamic_info.endpoint_info">
          <h4 class="descriptions-sub-title">
            {{ item.backend_name }} 后端
            <TopologyDiagram
              type="rpc"
              :source-data="item.client_endpoints"
              :target-data="item.server_endpoints"
              @select="handleTwoColClick"
            />
          </h4>
        </span>
      </div>
      <el-empty v-else description="无 Rpc 请求关系信息"></el-empty>
    </div>
    <el-empty v-else description="暂无模块详细数据" />
  </div>
</template>
<script setup lang="ts">
import { ElTable, ElTableColumn } from 'element-plus';
import { ElEmpty, ElDescriptions, ElDescriptionsItem } from 'element-plus';
import TagList from '@/components/TagList.vue';
import { useViewModel } from './Detail.vm';
import TopologyDiagram from '@/components/TopologyDiagram.vue';
import { useNPageJump } from '@/hooks/usePageJump';
import { useResourceDrawer } from '@/hooks/useResourceDrawer';

const [{ rpcDetailInfo, client_error_rate, server_error_rate }, {}] = useViewModel();
const { MyDrawer, openResourceDrawer } = useResourceDrawer();
const { viewModuleDetail, viewNodeDetail, handleTwoColClick } = useNPageJump();
</script>
