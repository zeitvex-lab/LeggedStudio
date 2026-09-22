// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "viz_module/service.h"
#include <ranges>
#include "aimrt_module_protobuf_interface/util/protobuf_tools.h"
#include "viz_module/global.h"

namespace aimrt_viz::viz_module {

void VizModuleServiceImpl::GetSystemInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::SystemInfoRequest& req,
    ::aimrt::protocols::viz_web::SystemInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebSystemInfoResponse(rsp);

  AIMRT_DEBUG("GetSystemInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));

  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetNodeBaseInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::NodeBaseInfoRequest& req,
    ::aimrt::protocols::viz_web::NodeBaseInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebNodeBaseInfoResponse(rsp);
  AIMRT_DEBUG("GetNodeBaseInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));

  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetNodeDetailInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::NodeDetailInfoRequest& req,
    ::aimrt::protocols::viz_web::NodeDetailInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebNodeDetailInfoResponse(req.node_name(), rsp);
  AIMRT_DEBUG("GetNodeDetailInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetModuleDetailInfo(aimrt::rpc::ContextRef ctx,
                                               const ::aimrt::protocols::viz_web::ModuleDetailInfoRequest& req,
                                               ::aimrt::protocols::viz_web::ModuleDetailInfoResponse& rsp,
                                               std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebModuleDetailInfoResponse(req.node_name(), req.module_name(), rsp);
  AIMRT_DEBUG("GetModuleDetailInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetRpcIndexInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::RpcIndexInfoRequest& req,
    ::aimrt::protocols::viz_web::RpcIndexInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebRpcIndexInfoResponse(rsp);
  AIMRT_DEBUG("GetRpcIndexInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetRpcDetailInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::RpcDetailInfoRequest& req,
    ::aimrt::protocols::viz_web::RpcDetailInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebRpcDetailInfoResponse(req.func_name(), rsp);

  AIMRT_DEBUG("GetRpcDetailInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetChannelIndexInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::ChannelIndexInfoRequest& req,
    ::aimrt::protocols::viz_web::ChannelIndexInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebChannelIndexInfoResponse(rsp);
  AIMRT_DEBUG("GetChannelIndexInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetChannelDetailInfo(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::ChannelDetailInfoRequest& req,
    ::aimrt::protocols::viz_web::ChannelDetailInfoResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebChannelDetailInfoResponse(req.topic_name(), req.msg_type(), rsp);
  AIMRT_DEBUG("GetChannelDetailInfo. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

void VizModuleServiceImpl::GetResource(
    aimrt::rpc::ContextRef ctx,
    const ::aimrt::protocols::viz_web::GetResourceRequest& req,
    ::aimrt::protocols::viz_web::GetResourceResponse& rsp,
    std::function<void(aimrt::rpc::Status)>&& callback) {
  data_manager_ptr_->SetWebResourceResponse(req.resource_id(), rsp);
  AIMRT_DEBUG("GetResource. ctx: {}, req: {}, rsp: {}",
              ctx.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  callback(aimrt::rpc::Status());
}

}  // namespace aimrt_viz::viz_module
