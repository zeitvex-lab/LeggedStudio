// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "aimdk/protocol/demo/demo_service.h"
#include "aimdk/protocol/demo/demo_channel.pb.h"
#include "src/convert/convert.h"
#include <string>

namespace example::pong
{
struct Ball {
  std::size_t seq = 0;
  std::string msg;
};
}  // namespace example::pong

namespace aimrte::impl
{
/**
 * @brief 实现从 Ball 通信类型到内部类型的转换函数，以实现 Ball 类型的数据接收
 */
template <>
void Convert(const aimdk::protocol::BallChannel &src, example::pong::Ball &dst);

/**
 * @brief 实现从获取 Ball 请求通信数据类型到 std::nullptr_t 的转换函数，以忽略请求数据
 */
template <>
inline void Convert(const aimdk::protocol::GetLatestBallRequest &, std::nullptr_t &)
{
}

/**
 * @brief 实现从 Ball 类型到获取 Ball 响应通信数据类型的转换，以实现 Ball 类型的服务返回。
 */
template <>
void Convert(const example::pong::Ball &src, aimdk::protocol::GetLatestBallResponse &dst);
}  // namespace aimrte::impl
