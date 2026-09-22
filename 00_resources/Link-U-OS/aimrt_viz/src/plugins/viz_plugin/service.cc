// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "service.h"
#include "aimrt_module_protobuf_interface/util/protobuf_tools.h"
#include "global.h"

namespace aimrt::plugins::viz_plugin {

aimrt::co::Task<aimrt::rpc::Status> VizServiceImpl::GetNodeInfo(
    aimrt::rpc::ContextRef ctx_ref,
    const aimrt::protocols::viz_plugin::NodeInfoRequest& req,
    aimrt::protocols::viz_plugin::NodeInfoResponse& rsp) {
  data_manager_ptr_->ReportNodeInfo(req, rsp);
  // AIMRT_TRACE("GetNodeInfo. ctx: {}, req: {}, rsp: {}",
  //            ctx_ref.ToString(), aimrt::Pb2CompactJson(req), aimrt::Pb2CompactJson(rsp));
  co_return {};
}

}  // namespace aimrt::plugins::viz_plugin