// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <unordered_map>
#include "aimrt_module_cpp_interface/executor/executor.h"
#include "viz_module/common.h"
#include "viz_module/data_manager.h"
#ifdef GOOGLE_PROTOBUF_USING_BAZEL
  #include "src/protocols/viz_web/viz_web.aimrt_rpc.pb.h"
#else
  #include "viz_web.aimrt_rpc.pb.h"
#endif

namespace aimrt_viz::viz_module {
class VizModuleServiceImpl : public aimrt::protocols::viz_web::AgentServiceAsyncService {
 public:
  VizModuleServiceImpl() = default;
  ~VizModuleServiceImpl() override = default;

  void SetDataManagerPtr(std::shared_ptr<DataManager>& data_manager_ptr) {
    data_manager_ptr_ = data_manager_ptr;
  }

  void GetSystemInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::SystemInfoRequest& req,
      ::aimrt::protocols::viz_web::SystemInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetNodeBaseInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::NodeBaseInfoRequest& req,
      ::aimrt::protocols::viz_web::NodeBaseInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetNodeDetailInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::NodeDetailInfoRequest& req,
      ::aimrt::protocols::viz_web::NodeDetailInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetModuleDetailInfo(aimrt::rpc::ContextRef ctx,
                           const ::aimrt::protocols::viz_web::ModuleDetailInfoRequest& req,
                           ::aimrt::protocols::viz_web::ModuleDetailInfoResponse& rsp,
                           std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetRpcIndexInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::RpcIndexInfoRequest& req,
      ::aimrt::protocols::viz_web::RpcIndexInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetRpcDetailInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::RpcDetailInfoRequest& req,
      ::aimrt::protocols::viz_web::RpcDetailInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetChannelIndexInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::ChannelIndexInfoRequest& req,
      ::aimrt::protocols::viz_web::ChannelIndexInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetChannelDetailInfo(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::ChannelDetailInfoRequest& req,
      ::aimrt::protocols::viz_web::ChannelDetailInfoResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

  void GetResource(
      aimrt::rpc::ContextRef ctx,
      const ::aimrt::protocols::viz_web::GetResourceRequest& req,
      ::aimrt::protocols::viz_web::GetResourceResponse& rsp,
      std::function<void(aimrt::rpc::Status)>&& callback) override;

 public:
  std::shared_ptr<DataManager> data_manager_ptr_;
};

}  // namespace aimrt_viz::viz_module
