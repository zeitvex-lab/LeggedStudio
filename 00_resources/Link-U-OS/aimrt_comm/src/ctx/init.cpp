// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./init.h"
#include "./anytime.h"
#include "./res.h"

namespace aimrte::ctx::init
{
ctx::Executor Executor(const std::string_view& name, const std::source_location call_loc)
{
  return {core::details::ExpectContext(call_loc)->InitExecutor(name, call_loc)};
}

ctx::Executor ThreadSafeExecutor(const std::string_view& name, const std::source_location call_loc)
{
  // 取出指定名称的执行器
  ctx::Executor exe = core::details::ExpectContext(call_loc)->InitExecutor(name, call_loc);

  // 检查它是否为线程安全的
  check(exe.ThreadSafe(), call_loc)
    .ErrorThrow("Executor [{}] is NOT thread safe !", name);

  // 返回该执行器
  return exe;
}
}  // namespace aimrte::ctx::init
