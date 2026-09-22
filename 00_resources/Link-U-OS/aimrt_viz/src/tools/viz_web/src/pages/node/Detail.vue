<template>
  <div class="page-container">
    <MyDrawer></MyDrawer>
    <div v-if="nodeBaseStaticInfo">
      <!-- 基本信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">基本信息</h3>
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="节点名称：">{{ nodeBaseStaticInfo?.node_name }}</el-descriptions-item>
          <el-descriptions-item label="aimrt 版本：">{{ nodeBaseStaticInfo?.aimrt_version }}</el-descriptions-item>
          <el-descriptions-item label="SOC：">{{ nodeBaseStaticInfo?.soc }}</el-descriptions-item>
          <el-descriptions-item label="PID：">{{ nodeBaseStaticInfo?.pid }}</el-descriptions-item>
          <el-descriptions-item label="启动时间：">{{ strat_time_format }}</el-descriptions-item>
          <el-descriptions-item label="可执行文件路径：">{{
            nodeBaseStaticInfo?.executable_path
          }}</el-descriptions-item>
          <el-descriptions-item label="配置文件路径：">{{ nodeBaseStaticInfo?.cfg_file_path }}</el-descriptions-item>
          <el-descriptions-item label="Publisher / Subscriber："
            >{{ nodeBaseStaticInfo?.pub_num }} / {{ nodeBaseStaticInfo?.sub_num }}</el-descriptions-item
          >
          <el-descriptions-item label="Server/ client："
            >{{ nodeBaseStaticInfo?.server_num }} / {{ nodeBaseStaticInfo?.client_num }}</el-descriptions-item
          >
        </el-descriptions>
      </div>

      <!-- 运行系统资源部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">系统资源信息</h3>
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="运行时间：">{{ online_time_format }}</el-descriptions-item>
          <el-descriptions-item label="内存使用：">{{ memory_usage_format }}</el-descriptions-item>
          <el-descriptions-item label="CPU使用率：">{{ cpu_usage_format }}</el-descriptions-item>
          <el-descriptions-item label="线程数：">{{ nodeBaseDynamicInfo?.thread_count }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 配置信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">配置信息</h3>
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="原始配置文件：">
            <el-button
              size="small"
              @click="openResourceDrawer('原始配置文件', configurationStaticInfo!.orin_cfg_file_id)"
              type="primary"
              class="descriptions-button"
              >查看</el-button
            >
          </el-descriptions-item>
          <el-descriptions-item label="解析配置文件：">
            <el-button
              size="small"
              @click="openResourceDrawer('解析配置文件', configurationStaticInfo!.parased_cfg_file_id)"
              type="primary"
              class="descriptions-button"
            >
              查看
            </el-button>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 插件信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">插件信息</h3>
        <el-table
          :data="pluginStaticInfo?.plugin_info_list"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="pluginStaticInfo?.plugin_info_list.length ?? 0 > 0"
        >
          <el-table-column prop="name" label="插件名称" min-width="15%" />
          <el-table-column prop="path" label="插件路径" min-width="40%" show-overflow-tooltip />
          <el-table-column label="配置信息" min-width="25%" show-overflow-tooltip>
            <template #default="scope">
              <el-button
                size="small"
                type="primary"
                @click="openResourceDrawer(scope.row.name, scope.row.options_id)"
                class="descriptions-button"
                >查看</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="无插件信息"></el-empty>
      </div>

      <!-- 执行器信息部分 -->
      <div class="bordered-box">
        <h3 class="descriptions-title">执行器信息</h3>
        <h4 class="descriptions-sub-title">执行器信息</h4>
        <!-- 线程信息 -->
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="main_thread：">
            <el-descriptions :column="1" class="descriptions-item-inliner">
              <el-descriptions-item label="TID：">
                {{ executorStaticInfo?.core_threads.main_thread.tid || '0' }}
              </el-descriptions-item>
              <el-descriptions-item label="名称：">
                {{ executorStaticInfo?.core_threads.main_thread.name || '---' }}
              </el-descriptions-item>
              <el-descriptions-item label="线程调度策略：">
                {{ executorStaticInfo?.core_threads.main_thread.thread_sched_policy || '---' }}
              </el-descriptions-item>
              <el-descriptions-item label="绑定的CPU：">
                <TagList :list="executorStaticInfo?.core_threads.main_thread.bind_cpu ?? []" plain separator="," />
              </el-descriptions-item>
            </el-descriptions>
          </el-descriptions-item>

          <el-descriptions-item label="guard_thread：">
            <el-descriptions :column="1" class="descriptions-item-inliner">
              <el-descriptions-item label="TID：">
                {{ executorStaticInfo?.core_threads.guard_thread.tid || '0' }}
              </el-descriptions-item>
              <el-descriptions-item label="名称：">
                {{ executorStaticInfo?.core_threads.guard_thread.name || '---' }}
              </el-descriptions-item>
              <el-descriptions-item label="线程调度策略：">
                {{ executorStaticInfo?.core_threads.guard_thread.thread_sched_policy || '---' }}
              </el-descriptions-item>
              <el-descriptions-item label="绑定的CPU：">
                <TagList :list="executorStaticInfo?.core_threads.guard_thread.bind_cpu ?? []" plain separator="," />
              </el-descriptions-item>
            </el-descriptions>
          </el-descriptions-item>

          <el-descriptions-item label="业务可用执行器类型：">
            <TagList :list="executorStaticInfo?.available_executor_list ?? []" />
          </el-descriptions-item>
        </el-descriptions>

        <!-- 执行器列表 -->
        <h4 class="descriptions-sub-title">执行器列表</h4>
        <el-table
          :data="executorStaticInfo?.executor_info_list"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="executorStaticInfo?.executor_info_list.length ?? 0 > 0"
        >
          <el-table-column prop="name" label="名称" min-width="15%" />
          <el-table-column label="类型" min-width="15%">
            <template #default="scope">
              <TagList :list="[scope.row.type]" />
            </template>
          </el-table-column>
          <el-table-column label="线程安全" min-width="15%">
            <template #default="scope">
              <StatusIndicator :status="scope.row.thread_safe" />
            </template>
          </el-table-column>
          <el-table-column label="支持定时调度" min-width="15%">
            <template #default="scope">
              <StatusIndicator :status="scope.row.support_time_schedule" />
            </template>
          </el-table-column>
          <el-table-column label="配置" min-width="10%">
            <template #default="scope">
              <el-button
                size="small"
                type="primary"
                class="descriptions-button"
                @click="openResourceDrawer(scope.row.name, scope.row.options_id)"
                >查看</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="无执行器信息"></el-empty>
      </div>

      <!-- 日志信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">日志信息</h3>
        <h4 class="descriptions-sub-title">基础信息</h4>
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="core_lvl：">
            <TagList :list="[logStaticInfo!.core_lvl]" />
          </el-descriptions-item>
          <el-descriptions-item label="default_module_lvl：">
            <TagList :list="[logStaticInfo!.default_module_lvl]" />
          </el-descriptions-item>

          <el-descriptions-item label="可用Log后端类型列表">
            <TagList :list="logStaticInfo?.reliable_log_backend_list ?? []" />
          </el-descriptions-item>
        </el-descriptions>
        <h4 class="descriptions-sub-title">日志后端列表</h4>
        <el-table
          :data="logStaticInfo?.log_backend_info_list"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="logStaticInfo?.log_backend_info_list.length ?? 0 > 0"
        >
          <el-table-column prop="type" label="类型" min-width="15%" />
          <el-table-column label="配置" min-width="10%">
            <template #default="scope">
              <el-button
                size="small"
                type="primary"
                class="descriptions-button"
                @click="openResourceDrawer(scope.row.type, scope.row.options_id)"
                >查看</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="无日志信息"></el-empty>
      </div>

      <!-- 模块信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">模块信息</h3>
        <el-table
          :data="moduleStaticInfo?.module_info_list"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="moduleStaticInfo?.module_info_list.length ?? 0 > 0"
        >
          <el-table-column label="模块名称" min-width="20%">
            <template #default="scope">
              <span class="clickable-cell" @click="viewModuleDetail(undefined, scope.row.name)">
                {{ scope.row.name }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="日志等级" min-width="10%">
            <template #default="scope">
              <TagList :list="[scope.row.log_lvl]" />
            </template>
          </el-table-column>
          <el-table-column prop="pkg_path" label="包路径" min-width="35%" show-overflow-tooltip />
          <el-table-column prop="cfg_path" label="配置路径" min-width="35%" show-overflow-tooltip />
        </el-table>
        <el-empty v-else description="无模块信息"></el-empty>
      </div>

      <!-- rpc 信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">Rpc 信息</h3>
        <div style="margin-bottom: 36px"></div>
        <h4 class="descriptions-sub-title">基础信息</h4>
        <el-descriptions :column="1" class="descriptions-item">
          <el-descriptions-item label="可用 RPC Client 过滤器列表：">
            <TagList :list="rpcStaticInfo?.available_client_filter_list ?? []" />
          </el-descriptions-item>
          <el-descriptions-item label="可用 RPC Server 过滤器列表：">
            <TagList :list="rpcStaticInfo?.available_server_filter_list ?? []" />
          </el-descriptions-item>
        </el-descriptions>
        <h4 class="descriptions-sub-title">Rpc 后端列表</h4>
        <el-table
          :data="rpcStaticInfo?.rpc_backend_info_list"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="rpcStaticInfo?.rpc_backend_info_list.length ?? 0 > 0"
        >
          <el-table-column prop="type" label="类型" min-width="15%" />
          <el-table-column label="配置" min-width="10%">
            <template #default="scope">
              <el-button
                size="small"
                type="primary"
                class="descriptions-button"
                @click="openResourceDrawer(scope.row.type, scope.row.options_id)"
                >查看</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="无 Rpc 后端列表信息"></el-empty>
        <h4 class="descriptions-sub-title">Rpc 客户端列表</h4>
        <el-table
          :data="rpcClientInfoList"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="rpcClientInfoList.length > 0"
        >
          <el-table-column label="服务名" min-width="30%">
            <template #default="scope">
              <span class="clickable-cell" @click="viewRpcDetail(scope.row.func_name)">
                {{ scope.row.func_name }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="modules" label="模块" min-width="20%">
            <template #default="scope">
              <span class="clickable-cell">
                <TwoColumnList :firstColumn="scope.row.modules" @select="handleTwoColClick" />
              </span>
            </template>
          </el-table-column>
          <
          <el-table-column label="后端" min-width="15%">
            <template #default="scope">
              <TagList :list="scope.row.backends ?? []" />
            </template>
          </el-table-column>
          <el-table-column label="过滤器" min-width="15%">
            <template #default="scope">
              <TagList :list="scope.row.filters ?? []" colorScheme="peach" />
            </template>
          </el-table-column>
          <el-table-column label="连接服务端" min-width="20%">
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
        <el-empty v-else description="无客户端列表信息"></el-empty>
        <h4 class="descriptions-sub-title">Rpc 服务端列表</h4>
        <el-table
          :data="rpcServerInfoList"
          style="width: 100%"
          stripe
          class="descriptions-table"
          show-overflow-tooltip
          v-if="rpcServerInfoList.length > 0"
        >
          <el-table-column prop="func_name" label="服务名" min-width="30%">
            <template #default="scope">
              <span class="clickable-cell" @click="viewRpcDetail(scope.row.func_name)">
                {{ scope.row.func_name }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="modules" label="模块" min-width="20%">
            <template #default="scope">
              <span class="clickable-cell">
                <TwoColumnList :firstColumn="scope.row.modules" @select="handleTwoColClick" />
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="backends" label="后端" min-width="15%">
            <template #default="scope">
              <TagList :list="scope.row.backends ?? []" />
            </template>
          </el-table-column>
          <el-table-column prop="filters" label="过滤器" min-width="15%">
            <template #default="scope">
              <TagList :list="scope.row.filters ?? []" colorScheme="peach" />
            </template>
          </el-table-column>
          <el-table-column prop="connected_to_module" label="连接客户端" min-width="20%">
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
        <el-empty v-else description="无服务端列表信息"></el-empty>
      </div>

      <!-- channel信息部分-->
      <div class="bordered-box">
        <h3 class="descriptions-title">Channel 信息</h3>
        <div style="margin-bottom: 36px">
          <h4 class="descriptions-sub-title">基础信息</h4>
          <el-descriptions :column="1" class="descriptions-item">
            <el-descriptions-item label="可用 Channel Pub 过滤器列表：">
              <TagList :list="channelStaticInfo?.available_pub_filter_list ?? []" />
            </el-descriptions-item>
            <el-descriptions-item label="可用 Channel Sub 过滤器列表：">
              <TagList :list="channelStaticInfo?.available_sub_filter_list ?? []" />
            </el-descriptions-item>
          </el-descriptions>
          <h4 class="descriptions-sub-title">Channel 后端列表</h4>
          <el-table
            :data="channelStaticInfo?.channel_backend_info_list"
            style="width: 100%"
            stripe
            class="descriptions-table"
            show-overflow-tooltip
            v-if="channelStaticInfo?.channel_backend_info_list.length ?? 0 > 0"
          >
            <el-table-column prop="type" label="类型" min-width="15%" />
            <el-table-column label="配置" min-width="10%">
              <template #default="scope">
                <el-button
                  size="small"
                  type="primary"
                  class="descriptions-button"
                  @click="openResourceDrawer(scope.row.type, scope.row.options_id)"
                  >查看</el-button
                >
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无 Channel 后端列表信息"></el-empty>
          <h4 class="descriptions-sub-title">Channel 发布端列表</h4>
          <el-table
            :data="channelPubInfoList"
            style="width: 100%"
            stripe
            class="descriptions-table"
            show-overflow-tooltip
            v-if="channelPubInfoList.length > 0"
          >
            <el-table-column prop="topic" label="话题/消息类型" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewChannelDetail(scope.row.topic, scope.row.msg_type)">
                  {{ scope.row.topic }}/{{ scope.row.msg_type }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="modules" label="模块" min-width="20%">
              <template #default="scope">
                <span class="clickable-cell">
                  <TwoColumnList :firstColumn="scope.row.modules" @select="handleTwoColClick" />
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="backends" label="后端" min-width="15%">
              <template #default="scope">
                <TagList :list="scope.row.backends ?? []" />
              </template>
            </el-table-column>
            <el-table-column prop="filters" label="过滤器" min-width="15%">
              <template #default="scope">
                <TagList :list="scope.row.filters ?? []" colorScheme="peach" />
              </template>
            </el-table-column>
            <el-table-column label="连接订阅端" min-width="20%">
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
          <el-empty v-else description="无发布端列表信息"></el-empty>
          <h4 class="descriptions-sub-title">Channel 订阅端列表</h4>
          <el-table
            :data="channelSubInfoList"
            style="width: 100%"
            stripe
            show-overflow-tooltip
            class="descriptions-table"
            v-if="channelSubInfoList.length > 0"
          >
            <el-table-column label="话题/消息类型" min-width="30%">
              <template #default="scope">
                <span class="clickable-cell" @click="viewChannelDetail(scope.row.topic, scope.row.msg_type)">
                  {{ scope.row.topic }}/{{ scope.row.msg_type }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="modules" label="模块" min-width="20%">
              <template #default="scope">
                <span class="clickable-cell">
                  <TwoColumnList :firstColumn="scope.row.modules" @select="handleTwoColClick" />
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="backends" label="后端" min-width="15%">
              <template #default="scope">
                <TagList :list="scope.row.backends ?? []" />
              </template>
            </el-table-column>
            <el-table-column prop="filters" label="过滤器" min-width="15%">
              <template #default="scope">
                <TagList :list="scope.row.filters ?? []" colorScheme="peach" />
              </template>
            </el-table-column>
            <el-table-column label="连接发布端" min-width="20%">
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
          <el-empty v-else description="无订阅端列表信息"></el-empty>
        </div>
      </div>
    </div>
    <el-empty v-else description="暂无节点详细数据" />
  </div>
</template>

<script setup lang="ts">
import { ElButton, ElEmpty, ElTable, ElTableColumn, ElDescriptions, ElDescriptionsItem } from 'element-plus';

import TagList from '@/components/TagList.vue';
import StatusIndicator from '@/components/StatusIndicator.vue';
import { useViewModel } from './Detail.vm.tsx';
import TwoColumnList from '@/components/TwoColumnList.vue';
import { useNPageJump } from '@/hooks/usePageJump';
import { useResourceDrawer } from '@/hooks/useResourceDrawer';
const [
  {
    nodeBaseDynamicInfo,
    nodeBaseStaticInfo,
    logStaticInfo,
    pluginStaticInfo,
    executorStaticInfo,
    moduleStaticInfo,
    rpcStaticInfo,
    channelStaticInfo,
    strat_time_format,
    online_time_format,
    memory_usage_format,
    cpu_usage_format,
    configurationStaticInfo,
    rpcServerInfoList,
    rpcClientInfoList,
    channelPubInfoList,
    channelSubInfoList
  },
  {}
] = useViewModel();
const { MyDrawer, openResourceDrawer } = useResourceDrawer();
const { viewModuleDetail, handleTwoColClick, viewRpcDetail, viewChannelDetail } = useNPageJump();
</script>
