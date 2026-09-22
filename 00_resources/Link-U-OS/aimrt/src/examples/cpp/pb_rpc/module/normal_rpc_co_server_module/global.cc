// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/examples/cpp/pb_rpc/module/normal_rpc_co_server_module/global.h"

namespace aimrt::examples::cpp::pb_rpc::normal_rpc_co_server_module {

aimrt::logger::LoggerRef global_logger;
void SetLogger(aimrt::logger::LoggerRef logger) { global_logger = logger; }
aimrt::logger::LoggerRef GetLogger() { return global_logger; }

}  // namespace aimrt::examples::cpp::pb_rpc::normal_rpc_co_server_module
