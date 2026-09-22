// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"

namespace aimrte::ctx::details
{
/**
 * @brief 运行时执行器操作接口
 */
class RunningExecutorRef
{
 public:
  RunningExecutorRef(const res::Executor& exe, const std::source_location call_loc)
      : exe_(exe), call_loc_(call_loc)
  {
  }

  RunningExecutorRef(res::Executor&& exe, const std::source_location call_loc)
      : temp_exe_(std::move(exe)), exe_(temp_exe_), call_loc_(call_loc)
  {
  }

  /**
   * @brief 使用当前上下文中、已有的执行器信息，执行给定函数（线程）或协程。
   */
  template <class F>
    requires core::concepts::SupportedInvoker<F>
  RunningExecutorRef& Post(F f)
  {
    core::details::ExpectContext(call_loc_)->exe(exe_, call_loc_).Post(std::move(f));
    return *this;
  }

  /**
   * @brief 使用当前上下文中、已有的执行器信息，执行给定函数（线程）或协程，
   *        但使用用户提供的异步管理器对该任务进行生命周期管理。
   */
  template <class F>
    requires core::concepts::SupportedInvoker<F>
  RunningExecutorRef& Post(aimrt::co::AsyncScope& scope, F f)
  {
    core::details::ExpectContext(call_loc_)->exe(exe_, call_loc_).Post(scope, std::move(f));
    return *this;
  }

  /**
   * @brief 在本执行器中，原地执行完给定函数或协程。
   *        一般可以用来让给定函数或协程获取执行器上下文，从而让其可以使用 ctx::exe().Post() 接口。
   */
  template <class F>
    requires core::concepts::SupportedInvoker<F>
  RunningExecutorRef& Inline(F&& f)
  {
    core::details::ExpectContext(call_loc_)->exe(exe_, call_loc_).Inline(std::forward<F>(f));
    return *this;
  }

 private:
  const res::Executor temp_exe_;
  const res::Executor& exe_;
  const std::source_location call_loc_;
};
}  // namespace aimrte::ctx::details

// 仅用于运行时阶段（init 之后）的上下文操作接口
namespace aimrte::ctx
{
/**
 * @brief 取出当前上下文中的执行器接口，仅可以进行运行时能用的操作
 * @param exe 指定的执行器资源
 * @param loc 仅用于记录调用处的信息
 */
[[nodiscard]] details::RunningExecutorRef exe(res::Executor&& exe, AIMRTE(src(loc)));

/**
 * @brief 取出当前上下文中的执行器接口，仅可以进行运行时能用的操作
 * @param exe 指定的执行器资源。若不指定，则默认为当前所在的执行器的资源。
 * @param loc 仅用于记录调用处的信息
 */
[[nodiscard]] details::RunningExecutorRef exe(
  const res::Executor& exe = core::details::g_thread_ctx.exe, AIMRTE(src(loc)));

/**
 * @brief 基于当前的上下文信息，发布指定资源的数据。
 */
template <class T>
void Publish(const res::Channel<T>& res, const T& msg, AIMRTE(src(loc)))
{
  core::details::ExpectContext(loc)->pub(loc).Publish(res, msg);
}

/**
 * @brief 使用指定服务资源，发起远程调用。
 * @tparam Q 请求数据类型
 * @tparam P 响应数据类型
 * @param q 请求数据
 * @param p 响应数据
 * @return 服务处理结果
 */
template <class Q, class P>
[[nodiscard]] co::Task<aimrt::rpc::Status> Call(
  const res::Service<Q, P>& srv, const Q& q, P& p, AIMRTE(src(loc)))
{
  return core::details::ExpectContext(loc)->cli(loc).Call(srv, q, p);
}

/**
 * @brief 与上一个接口类似，但可指定服务调用的相关配置（如超时等）。
 */
template <class Q, class P>
[[nodiscard]] co::Task<aimrt::rpc::Status> Call(
  const res::Service<Q, P>& srv, aimrt::rpc::ContextRef ctx, const Q& q, P& p, AIMRTE(src(loc)))
{
  return core::details::ExpectContext(loc)->cli(loc).Call(srv, ctx, q, p);
}

/**
 * @brief 调用给定的服务资源，执行其中绑定的服务函数。
 * @note 该函数一般只在 AimRT service impl 子类中使用。
 * @tparam Q 请求数据类型
 * @tparam P 响应数据类型
 * @return 处理结果
 */
template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P>
[[nodiscard]] aimrt::co::Task<aimrt::rpc::Status> Serving(
  const res::Service<Q, P>& srv, aimrt::rpc::ContextRef ctx, const Q& q, P& p, AIMRTE(src(loc)))
{
  co_return co_await core::details::ExpectContext(loc)->srv(loc).Serving(srv, ctx, q, p);
}

/**
 * @brief 在当前上下文中（线程或协程），睡眠给定时间
 * @param duration 睡眠时间
 */
[[nodiscard]] co::Task<void> Sleep(const std::chrono::steady_clock::duration& duration, AIMRTE(src(loc)));

/**
 * @brief 让出本协程的执行
 */
[[nodiscard]] co::Task<void> Yield(AIMRTE(src(loc)));
}  // namespace aimrte::ctx

// 引入各个子系统的操作接口
#include "src/hds/interface.h"
#include "src/trace/interface.h"
