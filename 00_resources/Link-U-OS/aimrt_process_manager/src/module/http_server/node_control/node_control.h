// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "net/asio_http_svr.h"

#include "net/asio_tools.h"

namespace process_manager
{

// todo
class NodeControl
{
 public:
  NodeControl() = default;
  ~NodeControl() = default;

 public:
  // node_ctrl executor
  std::shared_ptr<aimrt::common::net::AsioExecutor> node_ctrl_executor_ptr_;
};

}
