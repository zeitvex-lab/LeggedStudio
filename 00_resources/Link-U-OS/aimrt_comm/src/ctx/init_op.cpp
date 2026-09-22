// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./init_op.h"

namespace aimrte::ctx::init
{
core::Context::OpExe exe(const res::Executor& res, const std::source_location call_loc)
{
  return core::details::ExpectContext(call_loc)->exe(res, call_loc);
}

core::Context::OpExe exe(res::Executor&& res, const std::source_location loc)
{
  return core::details::ExpectContext(loc)->exe(std::move(res), loc);
}

std::shared_ptr<core::Context> GetCorePtr(const std::source_location loc)
{
  return core::details::ExpectContext(loc);
}
}  // namespace aimrte::ctx::init
