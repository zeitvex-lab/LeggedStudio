// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/module/module.h"

#include "./monitor_plugin.h"
#include "./self_resource_info.h"
#include "backend/channel.h"
#include "backend/rpc.h"
#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_tools.h"

namespace aimrte::plugin::monitor
{

bool MonitorPlugin::Initialize(aimrt::runtime::core::AimRTCore* core) noexcept
{
  core_ptr_ = core;

  const YAML::Node& core_cfg_node =
    core_ptr_->GetPluginManager().GetPluginOptionsNode(Name());
  options_.executor = core_cfg_node["executor"].as<std::string>();
  if (core_cfg_node["node_name"]) {
    options_.node_name = core_cfg_node["node_name"].as<std::string>();
  }

  // // channel 注册
  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPreInitChannel, [this]() {
    RegisterMonitorChannelBackend();
  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPreInitRpc, [this]() {
    RegisterMonitorRpcBackend();
  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPreInitChannel, [this] {
    RegisterChannelFilter();
  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPreInitRpc, [this] {
    RegisterRpcFilter();
  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPreInitModules, [this]() {
    DoInitliaze();  // 初始化
  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPostInitModules, [this] {

  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPostStart, [this] {
    ctx_ptr_->LetMe();
    executor_.Post([this]() -> aimrt::co::Task<void> {
      while (runFlag_) {
        co_await data_manager_.CollectData();
        co_await aimrte::ctx::Sleep(std::chrono::seconds(2));
      }
    });

    executor_.Post([this]() -> aimrt::co::Task<void> {
      co_await HeartBeat();
    });

    executor_.Post([this]() -> aimrt::co::Task<void> {
      co_await CollectResourceInfo();
    });
  });

  core_ptr_->RegisterHookFunc(aimrt::runtime::core::AimRTCore::State::kPreShutdown, [this] {
    runFlag_ = false;
    data_manager_.ShutDown();
  });

  return true;
}

void MonitorPlugin::Shutdown() noexcept
{
  runFlag_ = false;
}

void MonitorPlugin::DoInitliaze()
{
  // 读取配置
  data_manager_.SetOriOptionRootConf(
    core_ptr_->GetConfiguratorManager()
      .GetOriRootOptionsNode());  // 完整配置

  data_manager_.SetOptionRootConf(
    core_ptr_->GetConfiguratorManager()
      .GetRootOptionsNode());  // aimrt配置

  // 统计插件信息
  auto aimrt_cfg = data_manager_.GetDumpRootConfig()["aimrt"];
  if (aimrt_cfg["plugin"] && aimrt_cfg["plugin"]["plugins"]) {
    for (const auto& one_plugin : aimrt_cfg["plugin"]["plugins"]) {
      if (one_plugin["name"] && one_plugin["options"]) {
        std::string name = one_plugin["name"].as<std::string>();
        YAML::Emitter out;
        out << one_plugin["options"];
        std::string options = out.c_str();
        plugin_cfg_[name]   = options;
      }
    }
  }

  // 初始化AimRT资源
  core_proxy_ = std::make_shared<CoreProxy>(core_ptr_);
  ctx_ptr_    = aimrte::ctx::internal::InitWithoutSubsystems(aimrt::CoreRef(core_proxy_->Get().NativeHandle()));
  executor_   = ctx::init::Executor(options_.executor);
  heartbeat_publisher_ =
    ctx::init::Publisher<aimdk::protocol::ProcessHeartbeatChannel>("/aima/heartbeat");
  runFlag_ = true;
}

aimrt::co::Task<void> MonitorPlugin::HeartBeat()
{
  while (runFlag_) {
    auto start_time = std::chrono::steady_clock::now();

    aimdk::protocol::ProcessHeartbeatChannel msg;
    msg.mutable_data()->set_name(options_.node_name);
    auto pub_topic_hz_map = data_manager_.GetPubTopicHzMap();
    auto sub_topic_hz_map = data_manager_.GetSubTopicHzMap();

    auto topic_info = msg.mutable_data()->mutable_middleware_info()->mutable_topic_info();

    // 订阅的topic以及频率
    for (auto one_topic : data_manager_.GetSubTopicInfoList()) {
      const auto& state = sub_topic_hz_map[common::TopicHzCalculator::TopicInfo{.topic_name = std::string(one_topic.topic_name), .msg_type = std::string(one_topic.msg_type)}];
      auto topic        = topic_info->add_sub_topics();
      topic->set_name(std::string(one_topic.topic_name));
      topic->set_type(std::string(one_topic.msg_type));
      topic->set_hz(state.rate);
      topic->set_max(state.maxDelta);                     // 最大时延（毫秒）
      topic->set_min(state.minDelta);                     // 最小时延（毫秒）
      topic->set_std_dev(state.stdDev);                   // 时延标准差（毫秒）
      topic->set_window(state.windowSize);                // 当前窗口大小
      topic->set_timeout_thres(state.timeout_threshold);  // 超时阈值（毫秒）
      topic->mutable_backends()->CopyFrom({one_topic.backends.begin(), one_topic.backends.end()});
      topic->set_is_active(state.is_active);
    }

    // 发布的topic以及频率
    for (auto one_topic : data_manager_.GetPubTopicInfoList()) {
      const auto& state = pub_topic_hz_map[common::TopicHzCalculator::TopicInfo{.topic_name = std::string(one_topic.topic_name), .msg_type = std::string(one_topic.msg_type)}];

      auto topic = topic_info->add_pub_topics();
      topic->set_name(std::string(one_topic.topic_name));
      topic->set_type(std::string(one_topic.msg_type));
      topic->set_hz(state.rate);
      topic->set_max(state.maxDelta);                     // 最大时延（秒）
      topic->set_min(state.minDelta);                     // 最小时延（秒）
      topic->set_std_dev(state.stdDev);                   // 时延标准差（秒）
      topic->set_window(state.windowSize);                // 当前窗口大小
      topic->set_timeout_thres(state.timeout_threshold);  // 超时阈值（秒）
      topic->mutable_backends()->CopyFrom({one_topic.backends.begin(), one_topic.backends.end()});
      topic->set_is_active(state.is_active);
    }

    // RPC 信息目前未用 先不加
    //  auto rpc_info = msg.mutable_data()->mutable_middleware_info()->mutable_rpc_info();
    //  // rpc客户端信息
    //  for (auto one_rpc : data_manager_.GetRpcClientInfoList()) {
    //    auto rpc = rpc_info->add_rpc_clients();
    //    rpc->set_func_name(std::string(one_rpc.func_name));
    //    rpc->set_req_type(std::string(one_rpc.req_type));
    //    rpc->set_rsp_type(std::string(one_rpc.rsp_type));
    //    rpc->mutable_backends()->CopyFrom({one_rpc.backends.begin(), one_rpc.backends.end()});
    //  }
    //
    //  // rpc 服务端信息
    //  for (auto one_rpc : data_manager_.GetRpcServiceInfoList()) {
    //    auto rpc = rpc_info->add_rpc_servers();
    //    rpc->set_func_name(std::string(one_rpc.func_name));
    //    rpc->set_req_type(std::string(one_rpc.req_type));
    //    rpc->set_rsp_type(std::string(one_rpc.rsp_type));
    //    rpc->mutable_backends()->CopyFrom({one_rpc.backends.begin(), one_rpc.backends.end()});
    //  }

    // 系统资源使用情况
    ProcessResourceInfo tmp_info;

    {
      std::unique_lock<std::mutex> lock(self_process_res_info_mutex_);
      tmp_info = self_process_res_info_;
    }

    msg.mutable_data()->mutable_resource_info()->set_pid(tmp_info.pid);
    msg.mutable_data()->mutable_resource_info()->set_mem_usage(tmp_info.mem_usage);
    msg.mutable_data()->mutable_resource_info()->set_mem_usage_ratio(tmp_info.mem_usage_ratio);
    msg.mutable_data()->mutable_resource_info()->set_cpu_usage_ratio(tmp_info.cpu_usage_ratio);
    msg.mutable_data()->mutable_resource_info()->set_thread_count(tmp_info.thread_count);
    msg.mutable_data()->mutable_resource_info()->set_cpu_sched_policy(tmp_info.cpu_sched_policy);
    msg.mutable_data()->mutable_resource_info()->set_cpu_sched_priority(tmp_info.cpu_sched_priority);
    msg.mutable_data()->mutable_resource_info()->mutable_bounding_cpus()->CopyFrom({tmp_info.bounding_cpus.begin(), tmp_info.bounding_cpus.end()});

    // 中间件插件信息
    auto plugin_info = msg.mutable_data()->mutable_middleware_info()->mutable_plugin_info();
    for (const auto& [key, value] : plugin_cfg_) {
      (*plugin_info)[key] = value;
    }

    AIMRTE_TRACE("send heartbeat:{}", aimrt::Pb2CompactJson(msg));
    heartbeat_publisher_.Publish(msg);

    auto end_time       = std::chrono::steady_clock::now();
    int elapsed_time    = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();
    auto sleep_duration = std::max(0, std::stoi(aimrte::utils::Env("AIMRTE_HEARTBEAT_INTERVAL", "1000")) - elapsed_time);
    co_await aimrte::ctx::Sleep(std::chrono::milliseconds(sleep_duration));
  }
  co_return;
}

/**
 * @brief 1S 统计一次系统资源信息
 * @return
 */
aimrt::co::Task<void> MonitorPlugin::CollectResourceInfo()
{
  while (runFlag_) {
    ProcessResourceInfo tmp_info;
    auto self_pid = getpid();
    tmp_info.pid  = self_pid;
    // 获取当前进程的内存使用
    tmp_info.mem_usage       = get_process_memory_usage();
    tmp_info.mem_usage_ratio = 100.0 * (double)tmp_info.mem_usage / get_system_total_memory();
    // 获取当前进程的 CPU 使用比例
    tmp_info.cpu_usage_ratio = get_process_cpu_usage(self_pid);
    // 获取当前进程的线程数
    tmp_info.thread_count = get_process_thread_count();
    // 进程调度策略及优先级
    auto sched_info             = get_process_sched_info(self_pid);
    tmp_info.cpu_sched_policy   = sched_info.first;
    tmp_info.cpu_sched_priority = sched_info.second;
    // 进程绑核
    tmp_info.bounding_cpus = get_bound_cpus();

    {
      std::unique_lock<std::mutex> lock(self_process_res_info_mutex_);
      self_process_res_info_ = tmp_info;
    }

    co_await aimrte::ctx::Sleep(std::chrono::milliseconds(1000));
  }
  co_return;
}

void MonitorPlugin::RegisterMonitorChannelBackend()
{
  std::unique_ptr<MonitorChannelBackend> front_channel_backend_ptr =
    std::make_unique<MonitorChannelBackend>();

  static_cast<MonitorChannelBackend*>(front_channel_backend_ptr.get())
    ->SetDataManager(&data_manager_);
  core_ptr_->GetChannelManager().RegisterChannelBackend(
    std::move(front_channel_backend_ptr));
}

void MonitorPlugin::RegisterChannelFilter()
{
  auto& channel_manager = core_ptr_->GetChannelManager();

  channel_manager.RegisterPublishFilter(
    "monitor",
    [this](aimrt::runtime::core::channel::MsgWrapper& msg_wrapper, aimrt::runtime::core::channel::FrameworkAsyncChannelHandle&& h) {
      data_manager_.OnPublishFilter(msg_wrapper.info.topic_name, msg_wrapper.info.msg_type);
      h(msg_wrapper);
    });

  channel_manager.RegisterSubscribeFilter(
    "monitor",
    [this](aimrt::runtime::core::channel::MsgWrapper& msg_wrapper, aimrt::runtime::core::channel::FrameworkAsyncChannelHandle&& h) {
      if (core_ptr_->GetState() < aimrt::runtime::core::AimRTCore::State::kPreStart)
        return;

      data_manager_.OnSubscribeFilter(msg_wrapper.info.topic_name, msg_wrapper.info.msg_type);
      h(msg_wrapper);
    });
}

void MonitorPlugin::RegisterRpcFilter()
{
  auto& rpc_manager = core_ptr_->GetRpcManager();

  rpc_manager.RegisterServerFilter(
    "monitor",
    [this](const std::shared_ptr<aimrt::runtime::core::rpc::InvokeWrapper>& invoke_wrapper, aimrt::runtime::core::rpc::FrameworkAsyncRpcHandle&& h) {
      if (core_ptr_->GetState() < aimrt::runtime::core::AimRTCore::State::kPreStart)
        return;

      h(invoke_wrapper);
    });
}

void MonitorPlugin::RegisterMonitorRpcBackend()
{
  std::unique_ptr<MonitorRpcBackend> front_rpc_backend_ptr =
    std::make_unique<MonitorRpcBackend>(core_ptr_);
  static_cast<MonitorRpcBackend*>(front_rpc_backend_ptr.get())
    ->SetDataManager(&data_manager_);
  core_ptr_->GetRpcManager().RegisterRpcBackend(
    std::move(front_rpc_backend_ptr));
}

}  // namespace aimrte::plugin::monitor
