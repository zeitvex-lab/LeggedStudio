// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <poll.h>
#include <unistd.h>
#include <cstring>
#include <future>
#include <string>
#include <filesystem>

#include <iostream>

#include <boost/asio.hpp>

#include "process_error_code.h"
#include "src/util/global.h"
#include "src/util/process_log.h"

namespace process_manager
{

#define MAGIC 0x1111

#pragma pack(push, 1)
struct DomainSocketStruct
{
  uint32_t magic;    // 魔数
  uint16_t cmd;      // 类型
  uint32_t seq;      // seq标识
  uint32_t len;      // 整个报文长度
  char payload[0];   // buffer payload
};
#pragma pack(pop)


enum DomainSocketCmd {
  TRACE_LOG = 0,
  DEBUG_LOG = 1,
  INFO_LOG  = 2,
  WARN_LOG  = 3,
  ERROR_LOG = 4,
  FATAL_LOG = 5,

  APP_PID_INTE_TYPE = 100,        // 传输app_pid的信息
  APP_START_SUCCESS_FLAG = 101,   // 传输app 启动成功的标志信息
  APP_START_FAILED_FLAG = 102,    // 传输app 启动失败的标志信息
};


using boost::asio::local::stream_protocol;

using ReadLoopDataHandle = std::function<void(const DomainSocketStruct*)>;

class Session : public std::enable_shared_from_this<Session> {
 public:
  explicit Session(stream_protocol::socket socket, const std::string& app_name, ReadLoopDataHandle loop_handle = nullptr)
    : socket_(std::move(socket)),
      app_name_(app_name),
      loop_handle_(loop_handle) {}

  void ReadLoop() {
    auto self = shared_from_this();
    socket_.async_read_some(
      boost::asio::buffer(data_),
      [this, self](boost::system::error_code ec, std::size_t n) {
        if (self->stopped_) return;
        if (!ec) {

          // work
          ParseRecvData(data_.data(), n);
          data_.fill('\0');

          // continue;
          self->ReadLoop();
        }
      }
    );
  }

  void Stop() {
    if (stopped_.exchange(true)) return;

    boost::system::error_code ec;
    socket_.cancel(ec);                    // 取消所有挂起操作
    socket_.shutdown(stream_protocol::socket::shutdown_both, ec);
    socket_.close(ec);
  }

 private:
  void ParseRecvData(const char* data, size_t data_len);

 private:
  stream_protocol::socket socket_;
  std::string app_name_;
  ReadLoopDataHandle loop_handle_;

  std::array<char, 1024> data_;
  std::atomic<bool> stopped_{false};

  std::string recv_cache_;
};

class Server: public std::enable_shared_from_this<Server> {
 public:
  Server(boost::asio::io_context& ioc, const std::string& path, const std::string& app_name)
    : ioc_(ioc), acceptor_(ioc, stream_protocol::endpoint(path)), app_name_(app_name) {}

  ~Server() { Stop(); }

  void StartDaemonAccept(ReadLoopDataHandle handle) {
    read_loop_data_handle_ = std::move(handle);
    DoAccept();
  }

  size_t GetSessionNum() {
    std::lock_guard<std::mutex> lock(session_map_mtx_);
    return fd_to_session_map_.size();
  }

  // todo
  void RemoveSession() {}

  void Stop() {
    if (!open_.exchange(false)) return;

    boost::system::error_code ec;
    acceptor_.cancel(ec);
    acceptor_.close(ec);

    std::lock_guard<std::mutex> lock(session_map_mtx_);
    for (auto& pair : fd_to_session_map_) {
      pair.second->Stop();
    }
    fd_to_session_map_.clear();
  }

 private:
  void DoAccept();

 private:
  boost::asio::io_context& ioc_;
  stream_protocol::acceptor acceptor_;
  std::string app_name_;
  std::atomic<bool> open_{true};

  ReadLoopDataHandle read_loop_data_handle_;

  std::mutex session_map_mtx_;
  std::map<uint32_t, std::shared_ptr<Session>> fd_to_session_map_;
};

/**
 * @note boost::asio::io_context 在fork时状态拷贝不完整, 而且失去了多线程功能, 所以client端暂时不使用boost的组件
*/
class Client {
 public:
  Client(const std::string& socket_path, const std::string& app_name)
    : socket_path_(socket_path),
      app_name_(app_name) {}

  ~Client() {
    Stop();
  }

  bool Connect();

  void Stop() {
    if (sock_ != -1) {
      ::close(sock_);
      sock_ = -1;
    }
  }

  void Shutdown() {
    if (sock_ == -1) return;

    if (::shutdown(sock_, SHUT_WR) < 0) {
      AIMRT_ERROR_P("shutdown fd failed, app_name: {}", app_name_);
      return;
    }

    ::close(sock_);
    sock_ = -1;
  }

  ProcessErrorCode SendMsg(const std::string& str) {
    return SendMsg(std::move(std::string(str)));
  }

  ProcessErrorCode SendMsg(std::string&& str);

  ProcessErrorCode SendMsg(const char* data, size_t len);

 private:
  int sock_{-1};
  std::string socket_path_;
  std::string app_name_;
};


DomainSocketStruct* FormatStruct(uint16_t cmd, const char* data, uint32_t len);

}
