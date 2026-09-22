// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <functional>

#include "nlohmann/json.hpp"

#include "net/asio_http_svr.h"
#include "net/asio_tools.h"

#include "src/module/process_manager_proxy.h"

namespace process_manager
{

namespace asio = boost::asio;
namespace http = boost::beast::http;

using AsioHttpServer = aimrt::common::net::AsioHttpServer;

using HttpHandleCB = std::function<http::status(const std::string&, std::string&)>;

class ConfigManager;

// 供 aima-cli 调用
class JsonHttpServer
{
 public:
  JsonHttpServer(std::shared_ptr<ConfigManager> config_mgr,
                 const std::shared_ptr<boost::asio::io_context>& io_ptr,
                 const std::shared_ptr<aimrt::common::net::AsioHttpServer>& http_svr_ptr,
                 ProcessManagerProxy& proxy)
    : config_mgr_(config_mgr), io_ptr_(io_ptr), http_svr_ptr_(http_svr_ptr), proxy_(proxy) {}

  ~JsonHttpServer() {}

  bool Initialize();

  void Shutdown();

 private:
  void RegisterHttpHandle(const std::string& str, HttpHandleCB cb);

  http::status HandleStartApp(const std::string& req, std::string& rsp);
  http::status HandleStopApp(const std::string& req, std::string& rsp);
  http::status HandleResetApp(const std::string& req, std::string& rsp);
  http::status HandleStopAllApps(const std::string& req, std::string& rsp);
  http::status HandleGetAppInfo(const std::string& req, std::string& rsp);
  http::status HandleGetAllAppsInfo(const std::string& req, std::string& rsp);
  http::status HandleGetAllAppsConfig(const std::string& req, std::string& rsp);
  http::status HandleSetAppEnv(const std::string& req, std::string& rsp);

  http::status HandleGetKilledAppList(const std::string&, std::string& rsp);

  http::status CommResponse(ProcessErrorCode code, const std::string& success_msg, std::string& rsp);

 private:
  std::shared_ptr<ConfigManager> config_mgr_;

  std::shared_ptr<boost::asio::io_context> io_ptr_;
  std::shared_ptr<AsioHttpServer> http_svr_ptr_;

  ProcessManagerProxy& proxy_;
};

}
