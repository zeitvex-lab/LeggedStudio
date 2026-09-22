// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "http_server.h"

#include "src/module/http_server/node_control/node_control.h"
#include "src/module/http_server/aima_cli/json_http_server.h"

#include "src/config_manager/config_mgr.h"

#include "src/util/global.h"

namespace process_manager
{

auto WrapAimRTLoggerRef(aimrt::logger::LoggerRef logger_ref)
    -> std::shared_ptr<aimrt::common::util::LoggerWrapper> {
  return std::make_shared<aimrt::common::util::LoggerWrapper>(
      aimrt::common::util::LoggerWrapper{
          .get_log_level_func = [logger_ref]() -> uint32_t {
            return logger_ref.GetLogLevel();
          },
          .log_func = [logger_ref](uint32_t lvl,
                                   uint32_t line,
                                   const char* file_name,
                                   const char* function_name,
                                   const char* log_data,
                                   size_t log_data_size) {
            logger_ref.Log(
                lvl, line, file_name, function_name, log_data, log_data_size);  //
          }});
}

bool HttpServer::Initialize() {
  // aima
  aima_executor_ptr_ = std::make_shared<aimrt::common::net::AsioExecutor>(config_mgr_->GetWorkOption().aima_req_thread_num);
  aima_cli_svr_ptr_ = std::make_shared<aimrt::common::net::AsioHttpServer>(aima_executor_ptr_->IO());

  json_http_server_ = std::make_shared<JsonHttpServer>(config_mgr_, aima_executor_ptr_->IO(), aima_cli_svr_ptr_, process_manager_proxy_);
  if (!json_http_server_->Initialize()) {
    AIMRT_ERROR("json_http_server Initialize failed. stop process...");
    return false;
  }

  aima_executor_ptr_->Start();

  // node_ctrl
  // todo
  node_ctrl_executor_ptr_ = std::make_shared<aimrt::common::net::AsioExecutor>(config_mgr_->GetWorkOption().node_control_thread_num);

  node_ctrl_executor_ptr_->Start();

  return true;
}

bool HttpServer::Start() {
  // start
  aima_cli_svr_ptr_->SetLogger(WrapAimRTLoggerRef(GetLogger()));
  aima_cli_svr_ptr_->Initialize(aimrt::common::net::AsioHttpServer::Options{
      .ep = {boost::asio::ip::make_address_v4(config_mgr_->GetWorkOption().aima_listen_ip),
              config_mgr_->GetWorkOption().aima_req_port}});
  aima_cli_svr_ptr_->Start();

  AIMRT_INFO("aima_cli_http server start finish...");
  return true;
}

void HttpServer::Shutdown() {
  if (json_http_server_) {
    json_http_server_->Shutdown();
  }

  if (aima_cli_svr_ptr_) {
    aima_cli_svr_ptr_->Shutdown();
  }

  if (aima_executor_ptr_) {
      aima_executor_ptr_->Shutdown();
      aima_executor_ptr_->Join();
  }

  if (node_ctrl_executor_ptr_) {
      node_ctrl_executor_ptr_->Shutdown();
      node_ctrl_executor_ptr_->Join();
  }
}

}
