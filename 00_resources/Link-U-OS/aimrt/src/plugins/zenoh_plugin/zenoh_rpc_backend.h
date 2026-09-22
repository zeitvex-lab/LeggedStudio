// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_status.h"
#include "src/interface/aimrt_module_cpp_interface/util/type_support.h"
#include "src/runtime/core/rpc/rpc_backend_base.h"
#include "src/runtime/core/rpc/rpc_backend_tools.h"
#include "src/runtime/core/util/rpc_client_tool.h"
#include "src/common/util/buffer_util.h"
#include "src/common/util/url_encode.h"
#include "zenoh.h"
#include "src/plugins/zenoh_plugin/util.h"
#include "src/plugins/zenoh_plugin/zenoh_buffer_array_allocator.h"
#include "src/plugins/zenoh_plugin/zenoh_manager.h"

namespace aimrt::plugins::zenoh_plugin {
class ZenohRpcBackend : public runtime::core::rpc::RpcBackendBase {
 public:
  struct Options {
    std::string timeout_executor;
    struct ClientOptions {
      std::string func_name;
      bool shm_enabled = false;
    };
    std::vector<ClientOptions> clients_options;

    struct ServerOptions {
      std::string func_name;
      bool shm_enabled = false;
    };
    std::vector<ServerOptions> servers_options;
  };

 public:
  ZenohRpcBackend(
      std::shared_ptr<ZenohManager>& zenoh_manager_ptr, std::string& limit_domain)
      : zenoh_manager_ptr_(zenoh_manager_ptr),
        limit_domain_(limit_domain) {}
  ~ZenohRpcBackend() = default;

  std::string_view Name() const noexcept override { return "zenoh"; }

  void Initialize(YAML::Node options_node) override;
  void Start() override;
  void Shutdown() override;

  bool RegisterServiceFunc(
      const runtime::core::rpc::ServiceFuncWrapper& service_func_wrapper) noexcept override;
  bool RegisterClientFunc(
      const runtime::core::rpc::ClientFuncWrapper& client_func_wrapper) noexcept override;
  void Invoke(
      const std::shared_ptr<runtime::core::rpc::InvokeWrapper>& client_invoke_wrapper_ptr) noexcept override;

  void RegisterGetExecutorFunc(const std::function<executor::ExecutorRef(std::string_view)>& get_executor_func);

 private:
  void ReturnRspWithStatusCode(
      const std::string& pattern,
      std::string_view serialization_type,
      const char* req_id_buf,
      uint32_t code);

  enum class State : uint32_t {
    PreInit,
    Init,
    Start,
    Shutdown,
  };

  Options options_;
  std::atomic<State> state_ = State::PreInit;

  std::function<executor::ExecutorRef(std::string_view)> get_executor_func_;

  std::atomic_uint32_t req_id_ = 0;

  std::shared_mutex z_shared_mutex_;

  std::shared_ptr<ZenohManager> zenoh_manager_ptr_;
  std::string limit_domain_;

  std::unique_ptr<runtime::core::util::RpcClientTool<std::shared_ptr<runtime::core::rpc::InvokeWrapper>>> client_tool_ptr_;

  std::unordered_map<std::string, uint64_t> z_node_shm_size_map_;

  uint64_t shm_init_loan_size_ = 1024;
};

}  // namespace aimrt::plugins::zenoh_plugin