// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <any>
#include "src/interface/aimrt_module_c_interface/rpc/rpc_handle_base.h"
#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_context.h"
#include "src/interface/aimrt_module_cpp_interface/util/function.h"

namespace aimrt::context {

struct RpcResource {
  std::any call_f;
  std::any serve_f;
  std::string func_name;
};

}  // namespace aimrt::context
