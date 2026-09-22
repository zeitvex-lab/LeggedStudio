// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "json_http_server.h"

#include "src/process_manager/process_monitor.h"

#include "aimdk/protocol/em/api.pb.h"

#include "src/util/global.h"
#include "src/util/process_error_code.h"
#include "src/util/process_state.h"

#include "src/config_manager/config_mgr.h"

namespace process_manager
{

namespace asio = boost::asio;
namespace http = boost::beast::http;

using AsioHttpServer = aimrt::common::net::AsioHttpServer;


std::string TransEmAppInfoStateToName(EmAppInfo_State state) {
  std::string str;
  switch(state) {
    case EmAppInfo_State_State_UNDEFINED:
    {
      str = "UnDefined";
    } break;
    case EmAppInfo_State_State_IDLE:
    {
      str = "Idel";
    } break;
    case EmAppInfo_State_State_STARTING:
    {
      str = "Starting";
    } break;
    case EmAppInfo_State_State_RUNNING:
    case EmAppInfo_State_State_RUNNING_IN_PASS:
    {
      str = "Running";
    } break;
    case EmAppInfo_State_State_STOPPING:
    {
      str = "Stopping";
    } break;
    case EmAppInfo_State_State_EXITED:
    {
      str = "Stopped";
    } break;
  }

  return str;
}

bool JsonHttpServer::Initialize() {
  try
  {
    RegisterHttpHandle("/json/start_app", std::bind(&JsonHttpServer::HandleStartApp, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/stop_app", std::bind(&JsonHttpServer::HandleStopApp, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/reset_app", std::bind(&JsonHttpServer::HandleResetApp, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/stop_all_apps", std::bind(&JsonHttpServer::HandleStopAllApps, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/get_app_info", std::bind(&JsonHttpServer::HandleGetAppInfo, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/get_all_apps_info", std::bind(&JsonHttpServer::HandleGetAllAppsInfo, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/get_all_apps_config", std::bind(&JsonHttpServer::HandleGetAllAppsConfig, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/set_app_env", std::bind(&JsonHttpServer::HandleSetAppEnv, this, std::placeholders::_1, std::placeholders::_2));
    RegisterHttpHandle("/json/get_killed_app_list", std::bind(&JsonHttpServer::HandleGetKilledAppList, this, std::placeholders::_1, std::placeholders::_2));
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("Initialize, exception: {}", e.what());
    return false;
  }

  return true;
}

void JsonHttpServer::Shutdown() {

}


void JsonHttpServer::RegisterHttpHandle(const std::string& str, HttpHandleCB cb) {
  http_svr_ptr_->RegisterHttpHandleFunc<http::string_body>(str,
    [this, cb](const http::request<http::dynamic_body>& req,
        http::response<http::string_body>& rsp,
        std::chrono::nanoseconds /*timeout*/)
    -> asio::awaitable<AsioHttpServer::HttpHandleStatus> {

      // set access_control_allow_origin (this is set all)
      rsp.set(http::field::access_control_allow_origin, "*");

      // if is a options request
      if (req.method() == http::verb::options) {
        rsp.set(http::field::access_control_allow_methods, "POST, OPTIONS");
        rsp.set(http::field::access_control_allow_headers, "Content-Type, Authorization, X-Requested-With");
        rsp.set(http::field::access_control_max_age, "86400");

        rsp.result(http::status::ok);
        rsp.keep_alive(req.keep_alive());
        rsp.prepare_payload();
        co_return AsioHttpServer::HttpHandleStatus::kOk;
      }

      std::string req_str = boost::beast::buffers_to_string(req.body().data());
      std::string rsp_str;
      auto ret = cb(req_str, rsp_str);

      rsp = http::response<http::string_body>{http::status::ok, req.version()};
      rsp.set(http::field::server, BOOST_BEAST_VERSION_STRING);
      if (ret == http::status::ok) {
        rsp.set(http::field::content_type, "application/json");
      } else {
        rsp.set(http::field::content_type, "text/plain");
      }
      rsp.result(ret);
      rsp.keep_alive(req.keep_alive());
      rsp.body() = rsp_str;
      rsp.prepare_payload();

      co_return AsioHttpServer::HttpHandleStatus::kOk;
    });
    AIMRT_INFO("register cli-http: {}", str);
}

http::status JsonHttpServer::HandleStartApp(const std::string& req, std::string& rsp) {
  AIMRT_INFO("aima-cli: HandleStartApp req: {}", req);

  nlohmann::json req_data;
  try {
      req_data = nlohmann::json::parse(req);
  } catch (const nlohmann::json::parse_error& e) {
      AIMRT_ERROR("invalid json: {}",  e.what());
      rsp = "Stop app failed.";
      return http::status::internal_server_error;
  }

  std::string app_name = req_data["app_name"];
  std::string stdout_str, stderr_str;
  if (req_data.contains("stdout")) { stdout_str = req_data["stdout"]; }
  if (req_data.contains("stderr")) { stderr_str = req_data["stderr"]; }

  ProcessErrorCode ret;
  do {
    if (!stdout_str.empty()) {
      ret = proxy_.SetEnvCfg(app_name, "stdout", stdout_str);
      if (ret != ProcessErrorCode::SUCCESS)
        break;
    }

    if (!stderr_str.empty()) {
      ret = proxy_.SetEnvCfg(app_name, "stderr", stderr_str);
      if (ret != ProcessErrorCode::SUCCESS)
        break;
    }

    ret = proxy_.StartApp(app_name);
    if (ret != ProcessErrorCode::SUCCESS)
      break;

  } while (false);

  return CommResponse(ret, "start APP success", rsp);
}

http::status JsonHttpServer::HandleStopApp(const std::string& req, std::string& rsp) {
  AIMRT_INFO("aima-cli: HandleStopApp req: {}", req);

  nlohmann::json req_data;
  try {
      req_data = nlohmann::json::parse(req);
  } catch (const nlohmann::json::parse_error& e) {
      AIMRT_ERROR("invalid json: {}",  e.what());
      rsp = "Stop app failed.";
      return http::status::internal_server_error;
  }

  std::string app_name = req_data["app_name"];

  auto ret = proxy_.StopApp(app_name);

  return CommResponse(ret, "stop APP success", rsp);
}

http::status JsonHttpServer::HandleResetApp(const std::string& req, std::string& rsp) {
  AIMRT_INFO("aima-cli: HandleResetApp req: {}", req);

  nlohmann::json req_data;
  try {
      req_data = nlohmann::json::parse(req);
  } catch (const nlohmann::json::parse_error& e) {
      AIMRT_ERROR("invalid json: {}",  e.what());
      rsp = "Stop app failed.";
      return http::status::internal_server_error;
  }

  std::string app_name = req_data["app_name"];

  ProcessErrorCode ret = ProcessErrorCode::SUCCESS;
  do
  {
    MonitorAppInfo info;
    auto ret = proxy_.GetAppInfo(app_name, info);
    if (ret != ProcessErrorCode::SUCCESS) {
      break;
    }
    if (info.state != EmAppInfo_State::EmAppInfo_State_State_EXITED &&
        info.state != EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS &&
        info.state != EmAppInfo_State::EmAppInfo_State_State_IDLE) {
      ret = ProcessErrorCode::PROCESS_STATUS_BUSY;
      break;
    }

    ret = proxy_.ResetApp(app_name);

  } while (false);

  return CommResponse(ret, "reset app success", rsp);
}

http::status JsonHttpServer::HandleStopAllApps(const std::string& req, std::string& rsp) {
  AIMRT_INFO("aima-cli: HandleStopAllApps req: {}", req);

  auto ret = proxy_.StopAllApps();

  return CommResponse(ret, "stop all APP list", rsp);
}

http::status JsonHttpServer::HandleGetAppInfo(const std::string& req, std::string& rsp) {
  AIMRT_WARN("aima-cli: HandleGetAppInfo req: {}, need complete", req);
}

/**
{
  {"status", "success"},
  {
    "data",
    {
      {"gateway",
        {
          {"pid", 123},
          {"status", "Running(123)"},
          {"start", "2025-09-29T12:21:17.198406944Z"},
          {"from_resume", true}
        }
      },
      {"pnc",
        {
          {"pid", 1234},
          {"status", "Running(1234)"},
          {"start", "2025-09-29T12:21:17.196337344Z"},
          {"from_resume", true}
        }
      }
    }
  }
}

*/
http::status JsonHttpServer::HandleGetAllAppsInfo(const std::string& /*req*/, std::string& rsp) {

  std::vector<MonitorAppInfo> info_list;
  auto ret = proxy_.GetAllAppInfo(info_list);
  if (ret != ProcessErrorCode::SUCCESS) {
    rsp = "get all apps info failed. " + ProcessErrorCodeToString(ret);
    return http::status::internal_server_error;
  }

  nlohmann::json app_list;
  for (auto& ele : info_list) {
    nlohmann::json app_info;
    app_info["pid"] = ele.pid;
    app_info["status"] = TransEmAppInfoStateToName(ele.state) + "(" + std::to_string(ele.pid) + ")";
    app_info["start"] = GetNanoSecondTimestampStr(ele.time_stamp);
    app_info["from_resume"] = ele.from_reload;
    app_list[ele.app_name] = app_info;
  }

  nlohmann::json data;
  data["status"] = "success";
  data["data"] = app_list;

  rsp = data.dump();
  return http::status::ok;
}

http::status JsonHttpServer::HandleGetAllAppsConfig(const std::string& req, std::string& rsp) {
  AIMRT_WARN("aima-cli: HandleGetAllAppsConfig req: {}, need complete", req);
  return http::status::ok;
}

http::status JsonHttpServer::HandleSetAppEnv(const std::string& req, std::string& rsp) {
  AIMRT_WARN("aima-cli: HandleSetAppEnv req: {}, need complete", req);
  return http::status::ok;
}

http::status JsonHttpServer::HandleGetKilledAppList(const std::string&, std::string& rsp) {
  std::vector<std::string> info_list;
  auto ret = proxy_.GetUnexpectedKillAppList(info_list);
  if (ret != ProcessErrorCode::SUCCESS) {
    rsp = "get all killed app list failed. " + ProcessErrorCodeToString(ret);
    return http::status::internal_server_error;
  }

  nlohmann::json data;
  data["status"] = "success";
  data["app_list"] = nlohmann::json::array();
  for (auto &e : info_list) {
    data["app_list"].push_back(e);
  }

  rsp = data.dump();
  return http::status::ok;
}

http::status JsonHttpServer::CommResponse(ProcessErrorCode code, const std::string& success_msg, std::string& rsp) {
  nlohmann::json data;
  http::status status = http::status::ok;
  if (code == ProcessErrorCode::SUCCESS) {
    data["status"] = "success";
    data["message"] = success_msg;
    rsp = data.dump();
  } else {
    rsp = "return failed. msg: " + ProcessErrorCodeToString(code);
    status = http::status::internal_server_error;   // 设置500错误码
  }

  return status;
}

}
