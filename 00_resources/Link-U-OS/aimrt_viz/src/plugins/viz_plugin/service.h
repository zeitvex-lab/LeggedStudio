// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include "aimrt_module_cpp_interface/co/task.h"
#include "aimrt_module_cpp_interface/rpc/rpc_context.h"
#include "aimrt_module_cpp_interface/rpc/rpc_status.h"
#include "data_manager.h"
// #include "viz_plugin.aimrt_rpc.pb.h"

#ifdef GOOGLE_PROTOBUF_USING_BAZEL
  #include "src/protocols/viz_plugin/viz_plugin.aimrt_rpc.pb.h"
#else
  #include "viz_plugin.aimrt_rpc.pb.h"
#endif

namespace aimrt::plugins::viz_plugin {

class VizServiceImpl : public aimrt::protocols::viz_plugin::NodeServiceCoService {
 public:
  void RegisterDataManager(std::shared_ptr<DataManager> data_manager_ptr) {
    data_manager_ptr_ = data_manager_ptr;
  }

  aimrt::co::Task<aimrt::rpc::Status> GetNodeInfo(
      aimrt::rpc::ContextRef ctx_ref,
      const aimrt::protocols::viz_plugin::NodeInfoRequest& req,
      aimrt::protocols::viz_plugin::NodeInfoResponse& rsp);

 private:
  std::shared_ptr<DataManager> data_manager_ptr_;
};
}  // namespace aimrt::plugins::viz_plugin
