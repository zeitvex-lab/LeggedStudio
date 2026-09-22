// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <atomic>
#include <map>
#include <list>
#include <string_view>
#include <thread>

#include "boost/asio/io_context.hpp"

#include "process_data.h"

namespace process_manager
{

class ConfigManager;

struct ProcessReloadInfo {
  std::string app_name;
  std::string start_time;
  uint64_t time_stamp;
  int pid;
  uint64_t hash_val;
};

class ProcessManager
{
 public:
  ProcessManager(std::shared_ptr<ConfigManager> config_mgr)
    : config_mgr_(config_mgr),
      io_ctx_ptr_(std::make_shared<boost::asio::io_context>(config_mgr->GetWorkOption().domain_socket_thread_num)),
      work_guard_(io_ctx_ptr_->get_executor()) {}
  ~ProcessManager() {}

  bool Init();

  void Stop();

  // 线程安全
  ProcessErrorCode StartApp(const std::string& app_name);
  // 线程安全
  ProcessErrorCode StopApp(const std::string& app_name);

  const std::map<std::string, std::shared_ptr<ProcessData>>& GetProcessDataMap() {
    return process_name_to_data_map_;
  }

  ProcessErrorCode SetEnvCfg(const std::string& app_name, const std::string& key, const std::string& val);

  ProcessErrorCode ResetApp(const std::string& app_name);

 private:
  // 非线程安全
  ProcessErrorCode StartIntermediateProcess(std::shared_ptr<ProcessData> ptr);
  // intermediate_process

  ProcessErrorCode StartAppProcess(std::shared_ptr<ProcessData> ptr);

  // 非线程安全
  ProcessErrorCode StopProcess(std::shared_ptr<ProcessData> ptr);

  void StopAllProcess();

 private:
  void LoadProcessStateFile();

  bool ParseProcessState(const std::string& str, ProcessReloadInfo& info);

 private:
  std::shared_ptr<ConfigManager> config_mgr_;

  std::list<std::thread> threads_;
  std::shared_ptr<boost::asio::io_context> io_ctx_ptr_;
  boost::asio::executor_work_guard<boost::asio::io_context::executor_type> work_guard_;

  // 运行过程中, map结构保持稳定
  std::map<std::string, std::shared_ptr<ProcessData>> process_name_to_data_map_;

  std::atomic<bool> running_{false};
};

}
