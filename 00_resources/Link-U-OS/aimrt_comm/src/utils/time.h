// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <chrono>
#include <cstdint>

namespace aimrte::utils
{
/**
 * @brief 获取当前毫秒时间戳
 */
uint64_t GetCurrentTimestamp();

/**
 * @brief 为 protobuf 的 Timestamp 设置当前系统时间戳
 * @tparam TTimestamp aimdk::protocol::Timestamp
 */
template <class TTimestamp>
void SetCurrentTimestamp(TTimestamp& msg)
{
  const std::chrono::nanoseconds t = std::chrono::system_clock::now().time_since_epoch();
  msg.set_seconds(t.count() / 1'000'000'000);
  msg.set_nanos(t.count() - msg.seconds() * 1'000'000'000);
}
}  // namespace aimrte::utils
