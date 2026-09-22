// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>
#include <memory>

#include <boost/asio.hpp>

#include "aimrt_module_c_interface/module_base.h"

namespace process_manager
{

class Preparation
{
 public:
  Preparation() {}
  ~Preparation() {}

  bool Init(const std::string& file_name);

  bool Start();

  void Shutdown();

 private:
  void SetAddress(const std::string& ip, uint16_t port);
  bool CheckListenAddr();

 private:
  std::atomic<bool> running_{false};

  boost::asio::ip::tcp::endpoint listen_ep_;
};

}
