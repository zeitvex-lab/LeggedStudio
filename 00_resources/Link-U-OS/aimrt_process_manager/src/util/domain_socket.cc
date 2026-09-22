// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "domain_socket.h"

namespace process_manager
{

void Session::ParseRecvData(const char* data, size_t data_len) {
  // AIMRT_INFO("recv log data: {}", data_len);
  static size_t struct_len = sizeof(DomainSocketStruct);
  recv_cache_.append(data, data_len);

  while(recv_cache_.length() > struct_len) {
    if (recv_cache_.length() < struct_len) {
      return;
    }

    const DomainSocketStruct* domain_docket_st = reinterpret_cast<const DomainSocketStruct*>(recv_cache_.data());
    size_t len = (size_t)ntohl(domain_docket_st->len);
    uint32_t magic = ntohl(domain_docket_st->magic);
    if (magic != MAGIC) {
      AIMRT_ERROR("Parse msg failed, clean recv buffer: {}", recv_cache_.size());
      recv_cache_.clear();
      return;
    }

    if (len <= recv_cache_.length()) {
      if (loop_handle_)
        loop_handle_(domain_docket_st);
      recv_cache_.erase(0, len);
      // AIMRT_INFO("recv_cache_ leave: {}, len: {}", recv_cache_.size(), len);
    } else {
      return;
    }
  }
}

void Server::DoAccept() {
  acceptor_.async_accept(
      [this, self = shared_from_this() ](boost::system::error_code ec, stream_protocol::socket sock) {
        // 如果已被 stop()，或者 acceptor 被 cancel，直接返回
        if (!self->open_ || ec == boost::asio::error::operation_aborted) {
          return;
        }

        if (!ec) {
            AIMRT_INFO_P("[{}]: Server, read to create Session, fd: {}", app_name_, sock.native_handle());
            auto ptr = std::make_shared<Session>(std::move(sock), app_name_, read_loop_data_handle_);
            ptr->ReadLoop();
            std::lock_guard<std::mutex> lock(session_map_mtx_);
            fd_to_session_map_.emplace(sock.native_handle(), ptr);
        }

        if (self->open_) {
          self->DoAccept();
        }
      });
}


bool Client::Connect() {
  int sock = socket(AF_UNIX, SOCK_STREAM, 0);
  if (sock < 0) {
    AIMRT_ERROR("socker failed...");
    return false;
  }

  sockaddr_un addr{};
  addr.sun_family = AF_UNIX;
  strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);

  if (connect(sock, (sockaddr*)&addr, sizeof(addr)) < 0) {
    AIMRT_ERROR("connect failed...");
    return false;
  }

  sock_ = sock;

  return true;
}


ProcessErrorCode Client::SendMsg(std::string&& str) {
  return SendMsg(str.data(), str.length());
}

ProcessErrorCode Client::SendMsg(const char* data, size_t len) {
  size_t n = ::write(sock_, data, len);
  // ptr->SendMsg(reinterpret_cast<char*>(log_struct), log_str.size() + sizeof(LogStruct));
  if (n < 0) {
    AIMRT_ERROR("send failed... fd: {}", sock_);
    return ProcessErrorCode::DOMAIN_SOCKET_SEND_ERROR;
  }
  return ProcessErrorCode::SUCCESS;
}

DomainSocketStruct* FormatStruct(uint16_t cmd, const char* data, uint32_t len) {
  uint32_t buffer_len = len + sizeof(DomainSocketStruct);
  char* buffer = new char[buffer_len];
  memset(buffer, 0, buffer_len);

  DomainSocketStruct* log_st = reinterpret_cast<DomainSocketStruct*>(buffer);
  log_st->magic = htonl(MAGIC);
  log_st->cmd = htons(cmd);
  log_st->len = htonl(buffer_len);
  memcpy(log_st->payload, data, len);
  return log_st;
}


}
