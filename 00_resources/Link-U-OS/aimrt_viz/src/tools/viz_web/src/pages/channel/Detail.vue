<template>
  <div class="page-container">
    <MyDrawer></MyDrawer>
    <div v-if="chnDetailInfo">
      <!-- 基本信息部分-->
      <h3 class="descriptions-title">基本信息</h3>
      <el-descriptions :column="1" class="descriptions-item">
        <el-descriptions-item label="话题名：">
          {{ chnDetailInfo?.channel_detail_static_info.base_info.topic_name }}
        </el-descriptions-item>
        <el-descriptions-item label="消息类型：">
          <template #default>
            <span
              class="clickable-cell"
              @click="
                openResourceDrawer(
                  '消息协议',
                  chnDetailInfo!.channel_detail_static_info.base_info.schema_id,
                  'protobuf'
                )
              "
            >
              {{ chnDetailInfo?.channel_detail_static_info.base_info.msg_type }}
            </span>
          </template>
        </el-descriptions-item>
        <el-descriptions-item label="所有使用的后端：">
          <TagList
            :list="chnDetailInfo?.channel_detail_static_info?.base_info?.backend_name ?? []"
            display="wrap"
            color-scheme="peach"
          />
        </el-descriptions-item>
        <el-descriptions-item label="所有使用的过滤器：">
          <TagList
            :list="chnDetailInfo?.channel_detail_static_info?.base_info?.filter_name ?? []"
            display="wrap"
            color-scheme="deepBlue"
          />
        </el-descriptions-item>
      </el-descriptions>

      <!-- Chn请求状态部分-->
      <h3 class="descriptions-title">Channel 请求状态</h3>
      <div style="margin-bottom: 36px">
        <div class="bordered-box">
          <h4 class="descriptions-sub-title">发布端信息</h4>
          <el-descriptions
            :column="1"
            class="descriptions-item"
            v-if="chnDetailInfo?.channel_detail_dynamic_info.pub_info.module_infos.length ?? 0 > 0"
          >
            <!--当前状态信息-->
            <el-descriptions-item label="当前状态：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="频率/Hz：">
                  {{
                    chnDetailInfo?.channel_detail_dynamic_info?.pub_info?.current_status?.frequency ?? 0
                  }}</el-descriptions-item
                >
              </el-descriptions>
            </el-descriptions-item>

            <el-descriptions-item label="历史统计：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="累计发布次数：">
                  {{
                    chnDetailInfo?.channel_detail_dynamic_info?.pub_info?.history_stats?.seq_num ?? 0
                  }}</el-descriptions-item
                >
              </el-descriptions>
            </el-descriptions-item>
          </el-descriptions>

          <!--状态表-->
          <el-table
            :data="chnDetailInfo?.channel_detail_dynamic_info.pub_info.module_infos"
            style="width: 100%"
            stripe
            show-overflow-tooltip
            class="descriptions-table"
            v-if="chnDetailInfo?.channel_detail_dynamic_info.pub_info.module_infos.length ?? 0 > 0"
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

            <el-table-column prop="frequency" label="频率/Hz" min-width="15%" />
          </el-table>
          <el-empty v-else description="无发布端信息"></el-empty>
        </div>

        <div class="bordered-box">
          <h4 class="descriptions-sub-title">订阅端信息</h4>
          <el-descriptions
            :column="1"
            class="descriptions-item"
            v-if="chnDetailInfo?.channel_detail_dynamic_info.sub_info.module_infos.length ?? 0 > 0"
          >
            <el-descriptions-item label="当前状态：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="频率/Hz：">
                  {{
                    chnDetailInfo?.channel_detail_dynamic_info?.sub_info?.current_status?.frequency ?? 0
                  }}</el-descriptions-item
                >
              </el-descriptions>
            </el-descriptions-item>

            <el-descriptions-item label="历史统计：">
              <el-descriptions :column="1" class="descriptions-item-inliner">
                <el-descriptions-item label="累计订阅次数：">
                  {{
                    chnDetailInfo?.channel_detail_dynamic_info?.sub_info?.history_stats?.seq_num ?? 0
                  }}</el-descriptions-item
                >
              </el-descriptions>
            </el-descriptions-item>
          </el-descriptions>

          <el-table
            :data="chnDetailInfo?.channel_detail_dynamic_info.sub_info.module_infos"
            style="width: 100%"
            stripe
            show-overflow-tooltip
            class="descriptions-table"
            v-if="chnDetailInfo?.channel_detail_dynamic_info.sub_info.module_infos.length ?? 0 > 0"
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

            <el-table-column prop="frequency" label="频率/Hz" min-width="15%" />
          </el-table>
          <el-empty v-else description="无服务端信息"></el-empty>
        </div>
      </div>

      <!-- Chn请求关系部分-->
      <h3 class="descriptions-title">Channel 请求关系</h3>
      <div style="margin-bottom: 36px" v-if="chnDetailInfo?.channel_detail_dynamic_info.endpoint_info.length ?? 0 > 0">
        <span v-for="item in chnDetailInfo?.channel_detail_dynamic_info.endpoint_info">
          <h4 class="descriptions-sub-title">
            {{ item.backend_name }} 后端
            <TopologyDiagram
              type="channel"
              :source-data="item.pub_endpoints"
              :target-data="item.sub_endpoints"
              @select="handleTwoColClick"
            />
          </h4>
        </span>
      </div>
      <el-empty v-else description="无 Channel 请求关系信息"></el-empty>
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

const [{ chnDetailInfo }, {}] = useViewModel();
const { MyDrawer, openResourceDrawer } = useResourceDrawer();
const { viewModuleDetail, viewNodeDetail, handleTwoColClick } = useNPageJump();
</script>
