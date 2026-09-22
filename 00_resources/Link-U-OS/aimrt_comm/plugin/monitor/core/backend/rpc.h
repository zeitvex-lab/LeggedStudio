// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>

#include "src/interface/aimrt_module_cpp_interface/co/aimrt_context.h"
#include "src/interface/aimrt_module_cpp_interface/co/schedule.h"
#include "src/interface/aimrt_module_cpp_interface/co/sync_wait.h"
#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_handle.h"
#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_status.h"
#include "plugin/monitor/core/utils.h"
#include "boost/asio.hpp"
#include "src/runtime/core/aimrt_core.h"
#include "src/runtime/core/rpc/rpc_backend_base.h"

namespace aimrte::plugin::monitor
{

class DataManager;

class MonitorRpcBackend : public aimrt::runtime::core::rpc::RpcBackendBase
{
 public:
  struct Options {
    std::string executor;
  };

 public:
  MonitorRpcBackend(aimrt::runtime::core::AimRTCore* aimrt_ptr);

  ~MonitorRpcBackend() override = default;

  std::string_view Name() const noexcept override { return "monitor"; }

  void Initialize(YAML::Node options_node) override;

  void SetRpcRegistry(const aimrt::runtime::core::rpc::RpcRegistry* channel_registry_ptr) noexcept override;

  void Start() override;

  void Shutdown() override;

  bool RegisterServiceFunc(
    const aimrt::runtime::core::rpc::ServiceFuncWrapper& service_func_wrapper) noexcept override;

  bool RegisterClientFunc(
    const aimrt::runtime::core::rpc::ClientFuncWrapper& client_func_wrapper) noexcept override;

  void Invoke(const std::shared_ptr<aimrt::runtime::core::rpc::InvokeWrapper>& client_invoke_wrapper_ptr) noexcept override{};

  void SetDataManager(DataManager* manager)
  {
    data_manager_ = manager;
  }

 private:
  enum class Status : uint32_t {
    PreInit,
    Init,
    Start,
    Shutdown,
  };

  Options options_;

  std::atomic<Status> status_ = Status::PreInit;

  aimrt::runtime::core::AimRTCore* core_ptr_;

  const aimrt::runtime::core::rpc::RpcRegistry* rpc_registry_ptr_ = nullptr;

  aimrt::rpc::ContextRef context_ref_;

  const aimrt_rpc_handle_base_t* rpc_handler_ptr_ = nullptr;

  std::map<std::string, std::set<std::string>> moudle_func_map_;

  using ServiceFuncIndexMap =
    std::map<std::string_view,                       // func_name
             std::map<std::string_view,              // lib_path
                      std::set<std::string_view>>>;  // module_name

  ServiceFuncIndexMap service_func_register_index_;

  DataManager* data_manager_;

 private:
  std::vector<std::string> GetBackendsByRules(
    std::string_view topic_name,
    const std::vector<std::pair<std::string, std::vector<std::string>>>& rules);
};

}  // namespace aimrte::plugin::monitor
