// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "domain_socket.h"

namespace process_manager
{

class DomainSocketChannel
{
 public:
  DomainSocketChannel(boost::asio::io_context& io_ctx, const std::string& app_name, ReadLoopDataHandle handle)
    : io_ctx_(io_ctx),
      app_name_(app_name),
      handle_(handle)
      {
        socket_path_ = "/agibot/sys/em/" + app_name_ + ".sock";
        // client_ptr_ 在重置状态时,也保持有效, 无需彻底 reset智能指针
        client_ptr_ = std::make_shared<Client>(socket_path_, app_name_);
        InitBase();
      }

  ~DomainSocketChannel() {
    CleanServer();
    CleanClient();
  }

  bool InitChannelSrv() {
    server_ptr_->StartDaemonAccept(handle_);
    return true;
  }

  bool InitChannelClient() {
    bool ret = client_ptr_->Connect();
    if (ret) {
      // 等待通讯建立
      while (true) {
        size_t num = server_ptr_->GetSessionNum();
        if (num > 0) break;

        std::this_thread::sleep_for(std::chrono::milliseconds(100));
      }
    }
    return ret;
  }

  ProcessErrorCode SendStartMsg(DomainSocketCmd cmd,const char* buffer, size_t len) {
    DomainSocketStruct* domain_socket_st = FormatStruct(cmd, buffer, len);
    auto code = client_ptr_->SendMsg(reinterpret_cast<char*>(domain_socket_st), len + sizeof(DomainSocketStruct));
    delete [] reinterpret_cast<char*>(domain_socket_st);
    return code;
  }

  void CleanServer() {
    if (server_ptr_) {
      server_ptr_->Stop();
      server_ptr_.reset();
    }
  }

  void CleanClient() {
    if (client_ptr_) {
      client_ptr_->Stop();
    }
  }

  void ShutdownClient() {
    if (client_ptr_) {
      client_ptr_->Shutdown();
    }
  }

  void Reset() {
    CleanServer();
    CleanClient();
    InitBase();
  }

 private:
  void InitBase() {
    std::filesystem::path file_path(socket_path_);
    if (std::filesystem::exists(file_path)) {
      std::filesystem::remove(file_path);
    }

    server_ptr_ = std::make_shared<Server>(io_ctx_, socket_path_, app_name_);
  }

 private:
  boost::asio::io_context& io_ctx_;
  std::string app_name_;
  ReadLoopDataHandle handle_;

  std::string socket_path_;

  std::shared_ptr<Client> client_ptr_;
  std::shared_ptr<Server> server_ptr_;
};

}
