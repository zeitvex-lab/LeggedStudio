// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_context.h"
#include "src/panic/panic.h"
#include "src/res/res.h"
#include <memory>

namespace aimrte::core
{
class Context;
}

namespace aimrte::core::details
{
struct ThreadContext {
  // 模块的上下文
  std::weak_ptr<Context> ctx_ptr;

  // 执行器资源标识符，可能非法。
  res::Executor exe;

  // 正在处理的 rpc 上下文
  std::optional<aimrt::rpc::ContextRef> active_rpc_context;
};

inline thread_local ThreadContext g_thread_ctx;

/**
 * @brief 取出当前的上下文数据，若上下文数据无效时，提示用户并报错退出程序
 * @return 有效的上下文数据
 */
inline std::shared_ptr<Context> ExpectContext(const std::source_location& call_loc)
{
  const std::shared_ptr ctx_ptr = g_thread_ctx.ctx_ptr.lock();

  if (ctx_ptr != nullptr) [[likely]]
    return ctx_ptr;

  panic(call_loc).wtf("Broken context !");
}
}  // namespace aimrte::core::details
