// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>

#include <shared_mutex>
#include <string_view>
#include "src/interface/aimrt_module_cpp_interface/executor/executor.h"
#include "plugin/monitor/core/data_manager.h"
#include "plugin/monitor/core/utils.h"
#include "src/runtime/core/aimrt_core.h"
#include "src/runtime/core/channel/channel_backend_base.h"

namespace aimrte::plugin::monitor
{

class MonitorChannelBackend : public aimrt::runtime::core::channel::ChannelBackendBase
{
 public:
  struct Options {
    std::string executor;
  };

 private:
  enum class Status : uint32_t {
    PreInit,
    Init,
    Start,
    Shutdown,
  };
  DataManager* data_manager_;
  Options options_;
  std::atomic<Status> status_ = Status::PreInit;

  const aimrt::runtime::core::channel::ChannelRegistry* channel_registry_ptr_ = nullptr;

  std::shared_mutex rw_mutex_;  // 读写锁

  std::vector<std::pair<std::string, std::vector<std::string>>> pub_topics_backends_rules;
  std::vector<std::pair<std::string, std::vector<std::string>>> sub_topics_backends_rules;

 public:
  MonitorChannelBackend();
  ~MonitorChannelBackend() override = default;

  std::string_view Name() const noexcept override { return "monitor"; }

  void Initialize(YAML::Node options_node) override;

  void SetChannelRegistry(const aimrt::runtime::core::channel::ChannelRegistry* channel_registry_ptr) noexcept override;

  void Start() override;

  void Shutdown() override;

  bool RegisterPublishType(
    const aimrt::runtime::core::channel::PublishTypeWrapper& publish_type_wrapper) noexcept override { return true; };

  bool Subscribe(const aimrt::runtime::core::channel::SubscribeWrapper& subscribe_wrapper) noexcept override { return true; };

  void Publish(aimrt::runtime::core::channel::MsgWrapper& publish_wrapper) noexcept override{};

  void SetDataManager(DataManager* manager)
  {
    data_manager_ = manager;
  }

 private:
  std::vector<std::string> GetBackendsByRules(
    std::string_view topic_name,
    const std::vector<std::pair<std::string, std::vector<std::string>>>& rules);
};

}  // namespace aimrte::plugin::monitor
