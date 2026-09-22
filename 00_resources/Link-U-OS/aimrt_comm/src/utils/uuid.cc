// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./uuid.h"
#include <atomic>
#include <thread>
#include "boost/uuid/uuid.hpp"
#include "boost/uuid/uuid_generators.hpp"
#include "boost/uuid/uuid_io.hpp"

namespace aimrte::utils
{

uint64_t GenerateUniqueID()
{
  static thread_local uint16_t count     = 0;      // 当前线程计数器
  static thread_local uint16_t thread_id = 0;      // 当前线程ID
  static std::atomic<uint16_t> next_thread_id{0};  // 记录全局的下一个线程ID

  // 如果当前线程ID为0或计数器即将溢出，则获取新的线程ID
  if (thread_id == 0 || count == UINT16_MAX) [[unlikely]] {
    thread_id = ++next_thread_id;
    count     = 0;  // 重置计数器
  }

  uint64_t uid = 0;
  // 高32位设置为进程ID
  uid = static_cast<uint64_t>(getpid()) << 32;
  // 中间16位设置为线程ID
  uid |= static_cast<uint64_t>(thread_id) << 16;
  // 低16位设置为计数器
  uid |= count++;

  return uid;
}

std::string GenerateUuid()
{
  boost::uuids::random_generator gen;
  boost::uuids::uuid u = gen();
  return boost::uuids::to_string(u);
}

}  // namespace aimrte::utils
