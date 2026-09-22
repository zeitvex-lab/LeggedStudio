#include "viz_module/viz_module.h"
#include <cstdio>
#include "aimrt_module_cpp_interface/co/aimrt_context.h"
#include "aimrt_module_cpp_interface/co/inline_scheduler.h"
#include "aimrt_module_cpp_interface/co/on.h"
#include "aimrt_module_cpp_interface/co/schedule.h"
#include "aimrt_module_cpp_interface/co/sync_wait.h"
#include "aimrt_module_cpp_interface/executor/executor.h"
#include "aimrt_module_protobuf_interface/util/protobuf_tools.h"
#include "viz_module/common.h"
#include "viz_module/global.h"
#include "yaml-cpp/yaml.h"

namespace YAML {
template <>
struct convert<aimrt_viz::viz_module::VizModule::Options> {
  using Options = aimrt_viz::viz_module::VizModule::Options;
  static Node encode(const Options &rhs) {
    Node node;

    node["system_name"] = rhs.base_info_options.system_name;
    node["aimrt_viz_version"] = rhs.base_info_options.aimrt_viz_version;
    node["work_executor_name"] = rhs.work_executor_name;
    node["timer_interval_ms"] = rhs.timer_interval_ms;

    Node service_list;
    for (const auto &service : rhs.node_service_list) {
      service_list.push_back(service);
    }
    node["node_service_list"] = service_list;

    Node attributes;
    for (const auto &attr_map : rhs.base_info_options.attributes) {
      Node map_node;
      for (const auto &[key, value] : attr_map) {
        map_node[key] = value;
      }
      attributes.push_back(map_node);
    }
    node["attributes"] = attributes;

    return node;
  }

  static bool decode(const Node &node, Options &rhs) {
    if (!node.IsMap()) return false;

    if (node["system_name"])
      rhs.base_info_options.system_name = node["system_name"].as<std::string>();

    if (node["work_executor_name"])
      rhs.work_executor_name = node["work_executor_name"].as<std::string>();

    if (node["timer_interval_ms"])
      rhs.timer_interval_ms = node["timer_interval_ms"].as<uint64_t>();

    if (node["node_service_list"]) {
      rhs.node_service_list.clear();
      const Node &services = node["node_service_list"];
      for (const auto &service : services) {
        rhs.node_service_list.push_back(service.as<std::string>());
      }
    }

    if (node["attributes"]) {
      rhs.base_info_options.attributes.clear();
      const Node &attributes = node["attributes"];
      for (const auto &attr_map : attributes) {
        std::unordered_map<std::string, std::string> map_item;
        for (const auto &attr_pair : attr_map) {
          map_item[attr_pair.first.as<std::string>()] = attr_pair.second.as<std::string>();
        }
        rhs.base_info_options.attributes.push_back(map_item);
      }
    }

    return true;
  }
};
}  // namespace YAML

namespace aimrt_viz::viz_module {
bool VizModule::Initialize(aimrt::CoreRef core) {
  core_ = core;
  SetLogger(core_.GetLogger());

  try {
    // Read cfg
    std::string file_path = std::string(core_.GetConfigurator().GetConfigFilePath());
    if (!file_path.empty()) {
      YAML::Node cfg_node = YAML::LoadFile(file_path);
      options_ = cfg_node.as<Options>();
    }
    data_manager_ptr_ = std::make_shared<DataManager>();
    data_manager_ptr_->SetSystemInfo(options_.base_info_options);
    // Register rpc service
    service_ptr_ = std::make_shared<VizModuleServiceImpl>();
    AIMRT_CHECK_ERROR_THROW(core_.GetRpcHandle().RegisterService(service_ptr_.get()), "Register service failed.");
    service_ptr_->SetDataManagerPtr(data_manager_ptr_);
    // Register rpc client
    auto rpc_handle = core_.GetRpcHandle();
    AIMRT_CHECK_ERROR_THROW(rpc_handle, "Get rpc handle failed.");
    for (auto &node_serivce : options_.node_service_list) {
      AIMRT_CHECK_ERROR_THROW(aimrt::protocols::viz_plugin::RegisterNodeServiceClientFunc(rpc_handle, node_serivce), "Register client failed.");
      proxy_map_[node_serivce] = std::make_shared<aimrt::protocols::viz_plugin::NodeServiceCoProxy>(rpc_handle, node_serivce);
      response_map_[node_serivce] = aimrt::protocols::viz_plugin::NodeInfoResponse();
    }
    // Register executor
    AIMRT_ASSERT(!options_.work_executor_name.empty(), "work executor name is empty.");
    work_executor_ = core_.GetExecutorManager().GetExecutor(options_.work_executor_name);
    AIMRT_ASSERT(work_executor_, "Invalid executor name: {}", options_.work_executor_name);
  } catch (const std::exception &e) {
    AIMRT_ERROR("Init failed, {}", e.what());
    return false;
  }

  AIMRT_INFO("Init succeeded.");

  return true;
}

bool VizModule::Start() {
  try {
    run_flag_ = true;
    work_executor_.Execute(std::bind(&VizModule::MainLoop, this));
  } catch (const std::exception &e) {
    AIMRT_ERROR("Start failed, {}", e.what());
    return false;
  }

  AIMRT_INFO("Start succeeded.");
  return true;
}

void VizModule::Shutdown() {
  run_flag_ = false;
}

void VizModule::MainLoop() {
  AIMRT_INFO("Start loop.");

  while (run_flag_) {
    aimrt::co::AsyncScope scope;

    for (auto &node_service : options_.node_service_list) {
      scope.spawn(aimrt::co::On(aimrt::co::AimRTScheduler(work_executor_), RequestNodeInfo(node_service)));
    }
    aimrt::co::SyncWait(scope.complete());
    std::this_thread::sleep_for(std::chrono::milliseconds(options_.timer_interval_ms));
    data_manager_ptr_->UpdateData(response_map_);
  }

  AIMRT_INFO("Exit loop.");
}

aimrt::co::Task<void> VizModule::RequestNodeInfo(std::string &node_name) {
  auto it = proxy_map_.find(node_name);
  if (it == proxy_map_.end()) {
    AIMRT_ERROR("Invalid node name: {}", node_name);
    co_return;
  }
  auto &proxy = it->second;
  try {
    aimrt::protocols::viz_plugin::NodeInfoRequest req;
    aimrt::protocols::viz_plugin::NodeInfoResponse rsp;
    data_manager_ptr_->SetNodeRequire(req, node_name);

    const int max_retries = 2;
    const std::chrono::milliseconds retry_delay(500);  // 500ms重试间隔
    int retry_count = 0;
    bool success = false;

    while (retry_count < max_retries && !success) {
      auto ctx = proxy->NewContextSharedPtr();
      ctx->SetTimeout(std::chrono::seconds(1));

      auto status = co_await proxy->GetNodeInfo(ctx, req, rsp);
      if (status.OK()) {
        success = true;
        std::lock_guard<std::mutex> lock(response_map_mutex_);
        response_map_[node_name] = std::move(rsp);
      } else {
        retry_count++;
        if (retry_count < max_retries) {
          co_await aimrt::co::ScheduleAfter(aimrt::co::AimRTScheduler(work_executor_), retry_delay);
        } else {
          std::lock_guard<std::mutex> lock(response_map_mutex_);
          response_map_[node_name] = std::nullopt;
        }
      }
    }
  } catch (const std::exception &e) {
    AIMRT_ERROR("RequestNodeInfo exception: {}, node_name: {}", e.what(), node_name);
  }

  co_return;
}
}  // namespace aimrt_viz::viz_module