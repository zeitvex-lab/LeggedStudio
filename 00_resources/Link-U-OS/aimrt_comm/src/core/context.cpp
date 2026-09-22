// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./context.h"
#include "src/sys/internal/config.h"

namespace aimrte::core
{
std::atomic_int Context::global_unique_id_ = 0;

Context::Context(const aimrt::CoreRef core)
    : id_(++global_unique_id_), core_(core)
{
  enable_trace_ = sys::config::EnableTrace();
}

Context::~Context()
{
  aimrt::co::SyncWait(async_scope_.complete());
}

res::Executor Context::InitExecutor(const std::string_view& name, const std::source_location call_loc)
{
  // 获取指定名称的执行器
  const aimrt::executor::ExecutorRef executor = core_.GetExecutorManager().GetExecutor(name);
  check(executor, call_loc).ErrorThrow("Get executor [{}] failed.", name);

  // 初始化成功，维护该执行器
  executors_.push_back(executor);
  log(call_loc).Info("Init executor [{}] succeeded.", name);

  // 返回该执行器的资源描述
  res::Executor res;
  res.name_       = name;
  res.idx_        = executors_.size() - 1;
  res.context_id_ = id_;
  return res;
}

void Context::LetMe()
{
  details::g_thread_ctx = {weak_from_this()};
}

bool Context::Ok() const
{
  return is_ok_;
}

void Context::RequireToShutdown()
{
  is_ok_ = false;
}

bool Context::EnableTrace() const
{
  return enable_trace_;
}

Context::OpBase::OpBase(Context& ctx, const std::source_location loc)
    : ctx_(ctx), loc_(loc)
{
}

Context::OpPub Context::pub(std::source_location loc) &
{
  return {*this, loc};
}

Context::OpSub Context::sub(const std::source_location loc) &
{
  return {*this, loc};
}

Context::OpCli Context::cli(const std::source_location loc) &
{
  return {*this, loc};
}

Context::OpSrv Context::srv(const std::source_location loc) &
{
  return {*this, loc};
}

Context::OpExe Context::exe(const res::Executor& res, const std::source_location loc) &
{
  return {*this, res, loc};
}

Context::OpExe Context::exe(res::Executor&& res, const std::source_location loc) &
{
  return {*this, std::move(res), loc};
}

Context::OpLog Context::log(const std::source_location loc) &
{
  return {*this, loc};
}

Context::OpCheck Context::check(bool con, const std::source_location loc) &
{
  return {*this, con, loc};
}

Context::OpRaise Context::raise(const std::source_location loc) &
{
  return {*this, loc};
}

aimrt::CoreRef Context::GetRawRef(const Context& ctx)
{
  return ctx.core_;
}

aimrt::co::AsyncScope& Context::GetAsyncScope(Context& ctx)
{
  return ctx.async_scope_;
}
}  // namespace aimrte::core
