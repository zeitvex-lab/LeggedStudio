<template>
  <div class="page-container">
    <MyDrawer></MyDrawer>
    <div v-if="moduleBaseInfo">
      <!-- 基本信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">基本信息</h3>
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="名称：">{{ moduleBaseInfo?.name }}</el-descriptions-item>
          <el-descriptions-item label="日志等级：">{{ moduleBaseInfo?.log_lvl }}</el-descriptions-item>
          <el-descriptions-item label="包路径：">{{ moduleBaseInfo?.pkg_path }}</el-descriptions-item>
          <el-descriptions-item label="配置文件路径：">{{ moduleBaseInfo?.cfg_path }}</el-descriptions-item>
          <el-descriptions-item label="原始配置文件：">
            <template #default>
              <el-button
                size="small"
                type="primary"
                class="descriptions-button"
                @click="openResourceDrawer('模块配置文件', moduleBaseInfo!.options_id)"
                >查看</el-button
              >
            </template>
          </el-descriptions-item>
          <el-descriptions-item label="版本：">{{ moduleBaseInfo?.version }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- Rpc信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">Rpc 信息</h3>
        <div style="margin-bottom: 36px">
          <h4 class="descriptions-sub-title">客户端信息</h4>
          <el-table
            :data="rpcClientMergedInfoList"
            style="width: 100%"
            stripe
            show-overflow-tooltip
            class="descriptions-table"
            v-if="rpcClientMergedInfoList.length > 0"
          >
            <el-table-column prop="func_name" label="服务名" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewRpcDetail(scope.row.func_name)">
                  {{ scope.row.func_name }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="后端" min-width="20%">
              <template #default="scope">
                <TagList :list="scope.row.backend ?? []" />
              </template>
            </el-table-column>
            <el-table-column label="过滤器" min-width="20%">
              <template #default="scope"> <TagList :list="scope.row.filters ?? []" colorScheme="peach" /> </template>
            </el-table-column>
            <el-table-column label="所连接服务模块" min-width="30%"
              ><template #default="scope">
                <span class="clickable-cell">
                  <TwoColumnList
                    :firstColumn="scope.row.connected_to_node"
                    :secondColumn="scope.row.connected_to_module"
                    connector="/"
                    @select="handleTwoColClick"
                  />
                </span> </template
            ></el-table-column>
          </el-table>
          <el-empty v-else description="无客户端信息"></el-empty>

          <h4 class="descriptions-sub-title">服务端信息</h4>
          <el-table
            :data="rpcServerMergedInfoList"
            style="width: 100%"
            class="descriptions-table"
            stripe
            show-overflow-tooltip
            v-if="rpcServerMergedInfoList.length > 0"
          >
            <el-table-column prop="func_name" label="服务名" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewRpcDetail(scope.row.func_name)">
                  {{ scope.row.func_name }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="后端" min-width="20%">
              <template #default="scope">
                <TagList :list="scope.row.backend ?? []" />
              </template>
            </el-table-column>
            <el-table-column label="过滤器" min-width="20%">
              <template #default="scope"> <TagList :list="scope.row.filters ?? []" colorScheme="peach" /> </template>
            </el-table-column>
            <el-table-column label="所连接客户模块" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell">
                  <TwoColumnList
                    :firstColumn="scope.row.connected_to_node"
                    :secondColumn="scope.row.connected_to_module"
                    connector="/"
                    @select="handleTwoColClick"
                  />
                </span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无服务端信息"></el-empty>
        </div>
      </div>

      <!-- Channel信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">Channel 信息</h3>
        <div style="margin-bottom: 36px">
          <h4 class="descriptions-sub-title">发布端信息</h4>
          <el-table
            :data="channelPubMergedInfoList"
            style="width: 100%"
            stripe
            class="descriptions-table"
            show-overflow-tooltip
            v-if="channelPubMergedInfoList.length > 0"
          >
            <el-table-column prop="topic" label="话题/消息类型" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewChannelDetail(scope.row.topic, scope.row.msg_type)">
                  {{ scope.row.topic }}/{{ scope.row.msg_type }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="后端" min-width="20%">
              <template #default="scope">
                <TagList :list="scope.row.backend ?? []" />
              </template>
            </el-table-column>
            <el-table-column label="过滤器" min-width="20%">
              <template #default="scope">
                <TagList :list="scope.row.filters ?? []" colorScheme="peach" />
              </template>
            </el-table-column>
            <el-table-column label="所连接订阅模块" min-width="30%"
              ><template #default="scope">
                <span class="clickable-cell">
                  <TwoColumnList
                    :firstColumn="scope.row.connected_to_node"
                    :secondColumn="scope.row.connected_to_module"
                    connector="/"
                    @select="handleTwoColClick"
                  />
                </span> </template
            ></el-table-column>
          </el-table>
          <el-empty v-else description="无发布端信息"></el-empty>

          <h4 class="descriptions-sub-title">订阅端信息</h4>
          <el-table
            :data="channelSubMergedInfoList"
            style="width: 100%"
            stripe
            show-overflow-tooltip
            class="descriptions-table"
            v-if="channelSubMergedInfoList.length > 0"
          >
            <el-table-column prop="topic" label="话题/消息类型" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewChannelDetail(scope.row.topic, scope.row.msg_type)">
                  {{ scope.row.topic }}/{{ scope.row.msg_type }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label="后端" min-width="20%">
              <template #default="scope">
                <TagList :list="scope.row.backend ?? []" />
              </template>
            </el-table-column>
            <el-table-column label="过滤器" min-width="20%">
              <template #default="scope">
                <TagList :list="scope.row.filters ?? []" colorScheme="peach" />
              </template>
            </el-table-column>
            <el-table-column label="所连接发布模块" min-width="30%"
              ><template #default="scope">
                <span class="clickable-cell">
                  <TwoColumnList
                    :firstColumn="scope.row.connected_to_node"
                    :secondColumn="scope.row.connected_to_module"
                    connector="/"
                    @select="handleTwoColClick"
                  />
                </span> </template
            ></el-table-column>
          </el-table>
          <el-empty v-else description="无订阅端信息"></el-empty>
        </div>
      </div>
    </div>
    <el-empty v-else description="暂无模块详细数据" />
  </div>
</template>
<script setup lang="ts">
import { ElEmpty, ElTable, ElButton, ElTableColumn, ElDescriptions, ElDescriptionsItem } from 'element-plus';
import { useViewModel } from './Detail.vm.tsx';
import TwoColumnList from '@/components/TwoColumnList.vue';
import { useNPageJump } from '@/hooks/usePageJump';
import { useResourceDrawer } from '@/hooks/useResourceDrawer';
import TagList from '@/components/TagList.vue';
const [
  {
    moduleBaseInfo,
    rpcServerMergedInfoList,
    rpcClientMergedInfoList,
    channelPubMergedInfoList,
    channelSubMergedInfoList
  },
  {}
] = useViewModel();
const { MyDrawer, openResourceDrawer } = useResourceDrawer();
const { viewRpcDetail, viewChannelDetail, handleTwoColClick } = useNPageJump();
</script>
