// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./ball.h"

namespace aimrte::impl
{
template <>
void Convert<aimdk::protocol::BallChannel, example::pong::Ball>(
  const aimdk::protocol::BallChannel& src, example::pong::Ball& dst)
{
  dst.msg = src.ball().msg();
  dst.seq = src.header().seq();
}

template <>
void Convert<example::pong::Ball, aimdk::protocol::GetLatestBallResponse>(
  const example::pong::Ball& src, aimdk::protocol::GetLatestBallResponse& dst)
{
  dst.mutable_ball()->set_msg(src.msg + " " + std::to_string(src.seq));
}
}  // namespace aimrte::impl
