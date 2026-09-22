// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once


namespace aimrte::core
{
template <class T, concepts::SupportedSubscriber<T> TCallback>
Context::OpExe& Context::OpExe::Subscribe(const res::Channel<T>& ch, TCallback callback)
{
  ctx_.sub(loc_).DoSubscribe(ch, std::move(callback), res_);
  return *this;
}

template <class Q, class P, concepts::SupportedServer<Q, P> TServer>
Context::OpExe& Context::OpExe::Serve(const res::Service<Q, P>& srv, TServer server)
{
  ctx_.srv(loc_).DoServe(srv, std::move(server), res_);
  return *this;
}

template <class F>
  requires concepts::SupportedInvoker<F>
Context::OpExe& Context::OpExe::Post(F f)
{
  return Post(ctx_.async_scope_, std::move(f));
}

template <class F>
  requires concepts::SupportedInvoker<F>
Context::OpExe& Context::OpExe::Post(aimrt::co::AsyncScope& scope, F f)
{
  // 为即将创建的协程，准备好上下文数据，该协程将在 init 时取走
  details::g_thread_ctx = {ctx_.weak_from_this(), res_};

  // 启动协程
  scope.spawn_on(
    aimrt::co::AimRTScheduler(executor_),
    [](auto _f) -> co::Task<void> {
      co_return co_await _f();
    }(StandardizeInvoker(std::move(f))));

  return *this;
}

template <class F>
  requires concepts::SupportedInvoker<F>
Context::OpExe& Context::OpExe::Inline(F&& f)
{
  details::g_thread_ctx = {ctx_.weak_from_this(), res_};
  StandardizeInvoker(std::forward<F>(f))().Sync();
  return *this;
}

template <concepts::SupportedInvoker F>
constexpr auto Context::OpExe::StandardizeInvoker(F &&cb) {
  if constexpr (concepts::InvokerFunction<F>) {
    return [cb = std::forward<F>(cb)]() -> co::Task<void> {
      co_return cb();
    };
  } else if constexpr (concepts::InvokerCoroutine<F>) {
    return cb;
  } else if constexpr (concepts::InvokerRawCoroutine<F>) {
    return [cb = std::forward<F>(cb)]() -> co::Task<void> {
      co_return co_await cb();
    };
  } else
    static_assert(trait::always_false_v<F>);
}
}
