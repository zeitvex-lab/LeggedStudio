// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/co/inline_scheduler.h"
#include "src/interface/aimrt_module_cpp_interface/co/on.h"
#include "src/interface/aimrt_module_cpp_interface/co/task.h"

#include "./details/thread_context.h"
#include "src/macro/macro.h"
#include "src/interface/aimrt_module_cpp_interface/co/async_scope.h"
#include "src/interface/aimrt_module_cpp_interface/co/sync_wait.h"

namespace aimrte::co::details
{
template <class TFinal, class T>
class ReturnValueOrVoid;

template <class TFinal, class T>
class ReturnValueOrVoid
{
 public:
  auto return_value(const T& value)
  {
    return static_cast<TFinal*>(this)->promise_.return_value(value);
  }

  auto return_value(T&& value)
  {
    return static_cast<TFinal*>(this)->promise_.return_value(std::move(value));
  }
};

template <class TFinal>
class ReturnValueOrVoid<TFinal, void>
{
 public:
  auto return_void()
  {
    return static_cast<TFinal*>(this)->promise_.return_void();
  }
};
}  // namespace aimrte::co::details

namespace aimrte::co
{
inline thread_local bool synchronized{false};

/**
 * @brief 对 AimRT 协程的封装，在协程执行之前，初始化上下文信息
 */
template <class T>
class Task : public aimrt::co::Task<T>
{
 public:
  class Promise : public details::ReturnValueOrVoid<Promise, T>
  {
   public:
    auto get_return_object() noexcept
    {
      return Task{promise_.get_return_object()};
    }

    decltype(auto) initial_suspend() noexcept
    {
      struct Awaiter final {
        core::details::ThreadContext ctx;

        constexpr bool await_ready() const noexcept { return false; }

        constexpr void await_suspend(std::coroutine_handle<>) const noexcept {}

        void await_resume() noexcept
        {
          // 协程唤醒时，准备好执行上下文，协程中的过程将用到它
          core::details::g_thread_ctx = std::move(ctx);
        }
      };

      // 协程初始化时，记录 core::Context 为其准备的上下文
      ctx_ = core::details::g_thread_ctx;

      return Awaiter{ctx_};
    }

    auto final_suspend() const noexcept
    {
      struct Awaiter final {
        constexpr bool await_ready() noexcept { return false; }

        constexpr void await_resume() noexcept {}

        auto await_suspend(std::coroutine_handle<Promise> h) noexcept
        {
          return h.promise().promise_.continuation_.handle();
        }
      };

      return Awaiter{};
    }

    template <class Value>
    decltype(auto) await_transform(Value&& value)
    {
      struct Awaiter final {
        decltype(promise_.await_transform(std::forward<Value>(value)))
          awaiter;

        core::details::ThreadContext ctx;

        bool await_ready() noexcept
        {
          return awaiter.await_ready();
        }

        auto await_resume() noexcept
        {
          // 协程唤醒时，准备好执行上下文，协程中的过程将用到它
          core::details::g_thread_ctx = std::move(ctx);
          return awaiter.await_resume();
        }

        auto await_suspend(std::coroutine_handle<Promise> h) noexcept
        {
          return awaiter.await_suspend(
            std::coroutine_handle<typename aimrt::co::Task<T>::promise_type>::from_promise(
              h.promise().promise_));
        }
      };

      return Awaiter{promise_.await_transform(std::forward<Value>(value)), ctx_};
    }

    auto unhandled_done() noexcept
    {
      return promise_.unhandled_done();
    }

    auto unhandled_exception() noexcept
    {
      return promise_.unhandled_exception();
    }

   private:
    // AimRT 协程的核心实现
    typename aimrt::co::Task<T>::promise_type promise_;

    // 该协程的上下文信息
    core::details::ThreadContext ctx_;

    friend class details::ReturnValueOrVoid<Promise, T>;
  };

 public:
  using promise_type = Promise;
  using Base         = aimrt::co::Task<T>;

  explicit Task(Base base, const std::source_location created_loc = std::source_location::current()) noexcept
      : Base(std::move(base)), created_loc_(created_loc)
  {
  }

  Task(Task&& task) noexcept
      : Base(std::move(static_cast<Base&>(task))), used_(task.used_), created_loc_(task.created_loc_)
  {
    task.used_ = true;
  }

  ~Task()
  {
    auto* co_ptr = reinterpret_cast<
      ::unifex::coro::coroutine_handle<typename Base::promise_type>*>(this);

    if (*co_ptr and not used_)
      panic(created_loc_).wtf(R"(It makes no sense to create a coroutine but never use it !
Perhaps use 'co_await your_co_func()' or 'your_co_func().Sync()' ?)");
  }

 public:
  /**
   * @brief 在原地等待协程执行完。
   * @return 协程返回值
   */
  T Sync() &&
  {
    used_ = true;

    // 告知相关协程过程，当前协程被同步在线程上
    synchronized = true;
    AIMRTE(defer(synchronized = false));

    if constexpr (std::is_void_v<T>)
      aimrt::co::SyncWait(std::move(*this));
    else
      return aimrt::co::SyncWait(std::move(*this)).value();
  }

  /**
   * @brief 显式地将 task 标记为已经送入 unifex 框架
   */
  friend Task&& MoveIntoSender(Task& task)
  {
    task.used_ = true;
    return std::move(task);
  }

 private:
  // 本协程是否被调度，如果协程仅创建、不使用，将会 panic
  bool used_ = false;

  // 本协程创建的地方，仅用于日志打印
  const std::source_location created_loc_;
};

/**
 * @brief 原地将一个协程执行完
 */
template <class F, class... TArgs>
void SyncInline(F&& f, TArgs&&... args)
{
  aimrt::co::SyncWait(
    aimrt::co::On(aimrt::co::InlineScheduler(), f(std::forward<TArgs>(args)...)));
}

/**
 * @brief 用于提供停止协程语义
 */
using StopToken = unifex::inplace_stop_token;

/**
 * @brief 简单封住协程 async scope
 */
struct AsyncScope : aimrt::co::AsyncScope {
  void Complete()
  {
    aimrt::co::SyncWait(this->complete());
  }

  void Cancel()
  {
    aimrt::co::SyncWait(this->cleanup());
  }

  StopToken GetStopToken() noexcept
  {
    return this->get_stop_token();
  }
};
}  // namespace aimrte::co
