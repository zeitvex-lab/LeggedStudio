// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./service_proxy_builder.h"
#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_tools.h"
#include <fmt/format.h>

namespace aimrte::ctx::details
{
std::string ToHumanReadable(const aimrt::rpc::ContextRef& cfg, const void* msg_ptr)
{
  const std::string_view type_str = cfg.GetSerializationType();

  if (type_str == "pb") {
    return aimrt::Pb2CompactJson(*static_cast<const google::protobuf::Message*>(msg_ptr));
  }

  // FIXME: 若这里发来的消息里，可以被序列化、且内容就是下文所述，将产生误导。但这种情况几乎不存在。
  return ::fmt::format("UNKNOWN serialization type [{}]", type_str);
}
}  // namespace aimrte::ctx::details
