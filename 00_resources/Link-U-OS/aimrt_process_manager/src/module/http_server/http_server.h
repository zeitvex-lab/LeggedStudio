// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "aimrt_module_cpp_interface/executor/executor.h"

#include "src/module/process_manager_proxy.h"

#include "net/asio_http_svr.h"

#include "net/asio_tools.h"

namespace process_manager
{

class NodeControl;
class JsonHttpServer;
class ConfigManager;

/**
 * @brief http通讯服务
*/
class HttpServer
{
 public:
  HttpServer(std::shared_ptr<ConfigManager> config_mgr, aimrt::CoreRef core, aimrt::executor::ExecutorRef sm_executor,
             ProcessManagerProxy& proxy)
    : config_mgr_(config_mgr), core_(core), sm_executor_(sm_executor),
      process_manager_proxy_(proxy)
      {}

  ~HttpServer() {}

  bool Initialize();

  bool Start();

  void Shutdown();

 private:
  std::shared_ptr<ConfigManager> config_mgr_;
  aimrt::CoreRef core_;

  // sm_executor
  aimrt::executor::ExecutorRef sm_executor_;
  // aima-cli  executor
  std::shared_ptr<aimrt::common::net::AsioExecutor> aima_executor_ptr_;
  std::shared_ptr<aimrt::common::net::AsioHttpServer> aima_cli_svr_ptr_;

  // node_ctrl  executor
  std::shared_ptr<aimrt::common::net::AsioExecutor> node_ctrl_executor_ptr_;
  std::shared_ptr<aimrt::common::net::AsioHttpServer> node_ctrl_srv_ptr_;

  ProcessManagerProxy& process_manager_proxy_;

  // 主从控制 http服务
  std::shared_ptr<NodeControl> node_control_;

  // aima-cli http服务
  std::shared_ptr<JsonHttpServer> json_http_server_;
};

}
