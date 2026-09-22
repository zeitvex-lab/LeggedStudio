// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/module/preparation.h"

#include <thread>
#include <chrono>

namespace process_manager
{

bool Preparation::Init(const std::string& file_name) {
  // todo
  SetAddress("127.0.0.1", 56999);
  return true;
}

bool Preparation::Start() {
  running_ = true;
  while (running_.load()) {
    if (CheckListenAddr()) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::seconds(1));
  }

  return true; 
}

void Preparation::Shutdown() {
  running_ = false;
}

void Preparation::SetAddress(const std::string& ip, uint16_t port) {
  listen_ep_ = boost::asio::ip::tcp::endpoint{boost::asio::ip::make_address_v4(ip), port};
}


bool Preparation::CheckListenAddr() {
  try {
    boost::asio::io_context io;
    boost::asio::ip::tcp::acceptor acceptor(io, listen_ep_);
    return true;
  } catch (...) {
    return false;
  }
}

}
