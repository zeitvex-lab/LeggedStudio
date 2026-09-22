// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include <cstdio>
#include <functional>
#include <memory>
#include <string_view>
#include <vector>

#include "core/aimrt_core.h"
#include "core/channel/channel_msg_wrapper.h"
#include "core/executor/executor_base.h"
// #include "log_util.h"
// #include "utils/sys_tools.h"
#include "aimrt_viz_plugin.h"
#include "process_info.h"
#include "yaml-cpp/yaml.h"

namespace YAML {

template <>
struct convert<aimrt::plugins::viz_plugin::AimrtVizPlugin::Options> {
  using Options = aimrt::plugins::viz_plugin::AimrtVizPlugin::Options;

  static Node encode(const Options& rhs) {
    Node node;
    node["node_name"] = rhs.node_name;
    node["soc"] = rhs.soc;
    node["service_name"] = rhs.service_name;
    node["executor"] = rhs.executor;
    node["update_interval_ms"] = rhs.update_interval_ms;
    return node;
  }

  static bool decode(const Node& node, Options& rhs) {
    if (node["node_name"]) {
      rhs.node_name = node["node_name"].as<std::string>();
    }
    if (node["soc"]) {
      rhs.soc = node["soc"].as<std::string>();
    }
    if (node["service_name"]) {
      rhs.service_name = node["service_name"].as<std::string>();
    }
    if (node["executor"]) {
      rhs.executor = node["executor"].as<std::string>();
    }
    if (node["update_interval_ms"]) {
      rhs.update_interval_ms = node["update_interval_ms"].as<uint64_t>();
    }
    return true;
  }
};

}  // namespace YAML

namespace aimrt::plugins::viz_plugin {

bool AimrtVizPlugin::Initialize(aimrt::runtime::core::AimRTCore* core_ptr) noexcept {
  core_ptr_ = core_ptr;

  YAML::Node plugin_options_node = core_ptr_->GetPluginManager().GetPluginOptionsNode(Name());
  if (plugin_options_node && !plugin_options_node.IsNull()) {
    options_ = plugin_options_node.as<Options>();
  }

  init_flag_ = true;

  data_manager_ptr_ = std::make_shared<DataManager>();
  viz_service_impl_ptr_ = std::make_unique<VizServiceImpl>();

  viz_service_impl_ptr_->RegisterDataManager(data_manager_ptr_);
  if (!options_.service_name.empty()) {
    viz_service_impl_ptr_->SetServiceName(options_.service_name);
  } else {
    viz_service_impl_ptr_->SetServiceName(options_.node_name);
  }

  Doinit();

  core_ptr_->RegisterHookFunc(runtime::core::AimRTCore::State::kPreStart,
                              [this] {for (const auto& task : pre_start_hook_task_vec_) task(); });
  core_ptr_->RegisterHookFunc(runtime::core::AimRTCore::State::kPostInitModules, [this] {
    RegisterRpcService();
  });

  core_ptr_->RegisterHookFunc(runtime::core::AimRTCore::State::kPreShutdown, [this] {
    if (update_timer_) {
      update_timer_->Cancel();
    }
  });

  core_ptr_->RegisterHookFunc(runtime::core::AimRTCore::State::kPostInitExecutor, [this] {
    executor_ref_ = core_ptr_->GetExecutorManager().GetExecutor(options_.executor);
    AIMRT_CHECK_ERROR_THROW(executor_ref_,
                            "Can not get executor {}!", options_.executor);
    AIMRT_CHECK_ERROR_THROW(executor_ref_.SupportTimerSchedule(),
                            "Executor {} didn't support TimerSchedule!", options_.executor);

    update_timer_ = executor::CreateTimer(
        executor_ref_, std::chrono::milliseconds(options_.update_interval_ms), [this] {
          data_manager_ptr_->DoUpdateDynamicInfo();
        },
        false);
    update_timer_->Reset();
  });

  return true;
}

void AimrtVizPlugin::Doinit() {
  data_manager_ptr_->Initialize(core_ptr_);
  pre_start_hook_task_vec_.emplace_back((
      [this] {
        data_manager_ptr_->SetConfig();
        data_manager_ptr_->SetBaseInfo(options_.node_name, options_.soc);
        data_manager_ptr_->SetLog();
        data_manager_ptr_->SetBackends();
        data_manager_ptr_->SetPluginList();
        data_manager_ptr_->SetExecutorList();
        data_manager_ptr_->SetPubChannel();
        data_manager_ptr_->SetSubChannel();
        data_manager_ptr_->SetRpcClient();
        data_manager_ptr_->SetRpcServer();
        data_manager_ptr_->SetModuleInfo();
      }));
  core_ptr_->GetChannelManager().RegisterPublishFilter("viz", [this](aimrt::runtime::core::channel::MsgWrapper& msg_wrapper,
                                                                     aimrt::runtime::core::channel::FrameworkAsyncChannelHandle&& h) {
    h(msg_wrapper);
    data_manager_ptr_->OnPublish(msg_wrapper);
  });
  core_ptr_->GetChannelManager().RegisterSubscribeFilter("viz", [this](aimrt::runtime::core::channel::MsgWrapper& msg_wrapper,
                                                                       aimrt::runtime::core::channel::FrameworkAsyncChannelHandle&& h) {
    h(msg_wrapper);
    data_manager_ptr_->OnSubscribe(msg_wrapper);
  });

  core_ptr_->GetRpcManager().RegisterClientFilter("viz", [this](const std::shared_ptr<aimrt::runtime::core::rpc::InvokeWrapper>& wrapper_ptr,
                                                                aimrt::runtime::core::rpc::FrameworkAsyncRpcHandle&& h) {
    auto begin_time_stamp_us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    wrapper_ptr->callback =
        [this, wrapper_ptr, callback{std::move(wrapper_ptr->callback)}, begin_time_stamp_us](aimrt::rpc::Status status) {
          data_manager_ptr_->OnRpcClient(wrapper_ptr, status, begin_time_stamp_us);
          callback(status);
        };
    h(wrapper_ptr);
  });
  core_ptr_->GetRpcManager().RegisterServerFilter("viz", [this](const std::shared_ptr<aimrt::runtime::core::rpc::InvokeWrapper>& wrapper_ptr,
                                                                aimrt::runtime::core::rpc::FrameworkAsyncRpcHandle&& h) {
    auto begin_time_stamp_us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    wrapper_ptr->callback =
        [this, wrapper_ptr, callback{std::move(wrapper_ptr->callback)}, begin_time_stamp_us](aimrt::rpc::Status status) {
          data_manager_ptr_->OnRpcServer(wrapper_ptr, status, begin_time_stamp_us);
          callback(status);
        };
    h(wrapper_ptr);
  });
}

void AimrtVizPlugin::RegisterRpcService() {
  auto rpc_handle_ref = aimrt::rpc::RpcHandleRef(
      core_ptr_->GetRpcManager().GetRpcHandleProxy().NativeHandle());
  bool ret = rpc_handle_ref.RegisterService(viz_service_impl_ptr_.get());
  AIMRT_CHECK_ERROR(ret, "Register service failed.");
}

void AimrtVizPlugin::Shutdown() noexcept {
  try {
    if (!init_flag_) return;

  } catch (const std::exception& e) {
    AIMRT_ERROR("Shutdown failed, {}", e.what());
  }
}

}  // namespace aimrt::plugins::viz_plugin