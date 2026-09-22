// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#include "aimrt_module_cpp_interface/co/async_scope.h"
#include "aimrt_module_cpp_interface/module_base.h"
#include "viz_module/common.h"
#include "viz_module/data_manager.h"
#include "viz_module/service.h"
#ifdef GOOGLE_PROTOBUF_USING_BAZEL
  #include "src/protocols/viz_plugin/viz_plugin.aimrt_rpc.pb.h"
#else
  #include "viz_plugin.aimrt_rpc.pb.h"
#endif

namespace aimrt_viz::viz_module {
class VizModule : public aimrt::ModuleBase {
 public:
  struct Options {
    SystemInfo base_info_options;
    std::string work_executor_name;
    uint64_t timer_interval_ms = 3000;
    std::vector<std::string> node_service_list;
  };

 public:
  VizModule() = default;
  ~VizModule() override = default;

  aimrt::ModuleInfo Info() const override {
    return aimrt::ModuleInfo{.name = "VizModule"};
  }

  bool Initialize(aimrt::CoreRef core) override;

  bool Start() override;

  void Shutdown() override;

 private:
  void MainLoop();

  aimrt::co::Task<void> RequestNodeInfo(std::string& node_name);

 private:
  aimrt::CoreRef core_;
  Options options_;

  std::atomic_bool run_flag_ = false;

  aimrt::executor::ExecutorRef work_executor_;

  std::shared_ptr<VizModuleServiceImpl> service_ptr_;

  std::unordered_map<std::string, std::optional<aimrt::protocols::viz_plugin::NodeInfoResponse>>
      response_map_;

  std::unordered_map<std::string, std::shared_ptr<aimrt::protocols::viz_plugin::NodeServiceCoProxy>>
      proxy_map_;

  std::shared_ptr<DataManager> data_manager_ptr_;
  std::mutex response_map_mutex_;
};
}  // namespace aimrt_viz::viz_module