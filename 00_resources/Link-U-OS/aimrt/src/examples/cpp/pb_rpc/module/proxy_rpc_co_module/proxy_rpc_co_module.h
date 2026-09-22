// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/co/async_scope.h"
#include "src/interface/aimrt_module_cpp_interface/co/task.h"
#include "src/interface/aimrt_module_cpp_interface/module_base.h"
#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_co_filter.h"
#include "src/examples/cpp/pb_rpc/module/proxy_rpc_co_module/service.h"

#include "src/protocols/pb/example/rpc/rpc.aimrt_rpc.pb.h"

namespace aimrt::examples::cpp::pb_rpc::proxy_rpc_co_module {
class ProxyRpcCoModule : public aimrt::ModuleBase {
 public:
  ProxyRpcCoModule() = default;
  ~ProxyRpcCoModule() override = default;

  ModuleInfo Info() const override {
    return ModuleInfo{.name = "ProxyRpcCoModule"};
  }

  bool Initialize(aimrt::CoreRef core) override;

  bool Start() override;

  void Shutdown() override;

 private:
  auto GetLogger() { return core_.GetLogger(); }

 private:
  aimrt::CoreRef core_;
  aimrt::executor::ExecutorRef executor_;

  std::string service_name_for_client_;
  std::string service_name_for_server_;

  std::shared_ptr<aimrt::protocols::example::ExampleServiceCoProxy> proxy_;
  std::shared_ptr<ExampleCoComplexCoServiceImpl> service_ptr_;
};

}  // namespace aimrt::examples::cpp::pb_rpc::proxy_rpc_co_module