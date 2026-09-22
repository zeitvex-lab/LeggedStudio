// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once


#include <coroutine>
#include <tuple>
#include <variant>
#include "src/container/indexed_variant.h"
#include "src/core/core.h"
#include "src/ctx/ctx.h"
#include "src/panic/panic.h"

#include "./details/coroutine_decorator.h"

namespace aimrte
{
struct Void {
};
}  // namespace aimrte

namespace aimrte::sync
{
template <class... TTasks>
class any : std::tuple<TTasks&&...>
{
  static_assert(sizeof...(TTasks) != 0);
  using Base = std::tuple<TTasks&&...>;

  template <class E>
  struct TaskTypeTrait {
    using Task         = E;
    using DecayTask    = std::remove_reference_t<Task>;
    using MiddleResult = typename co::details::MiddleReturnValueTypeTrait<DecayTask>::Type;
    using RawResult    = typename co::details::ReturnValueTypeTrait<DecayTask>::Type;
    using Result       = std::conditional_t<std::is_void_v<RawResult>, Void, RawResult>;

    constexpr static bool has_executor = co::details::has_executor<DecayTask>;
  };

  template <std::size_t I>
  struct TypeTrait : TaskTypeTrait<std::tuple_element_t<I, Base>> {
  };

  using Result = IndexedVariant<typename TaskTypeTrait<TTasks>::Result...>;

 public:
  explicit any(TTasks&&... tasks)
      : Base(std::forward<TTasks>(tasks)...)
  {
    // 检查当前是否在执行器环境下运行本 any 操作，如果不是，需要报错
    if (not curr_exe_.IsValid())
      panic().wtf(R"(Never use aimrte::sync::any outside of aimrte::ctx::Executor !)");
  }

  any&& In(aimrt::co::AsyncScope& scope) &&
  {
    scope_ = &scope;
    return std::move(*this);
  }

  any&& Via(res::Executor exe) &&
  {
    exe_ = std::move(exe);
    return std::move(*this);
  }

  constexpr static bool await_ready()
  {
    return false;
  }

  bool await_suspend(std::coroutine_handle<> continuation)
  {
    ctx_ = std::make_shared<Context>(continuation, std::move(curr_exe_));
    DoSuspend(std::make_index_sequence<sizeof...(TTasks)>());

    if (ctx_->Done())
      return not ctx_->inline_resume;

    return true;
  }

  Result await_resume()
  {
    return std::move(ctx_->result).value();
  }

 private:
  template <std::size_t... I>
  void DoSuspend(std::index_sequence<I...>)
  {
    // 先取出 sender ，目的是为了将 Task 中的 used 标记为 true，避免因为协程不被调度，从而出现未使用协程错误
    auto into_sender_and_handler = []<class Task>(Task&& task) {
      return std::tuple{
        co::details::IntoMiddleSender(std::forward<Task>(task)),
        co::details::IntoFinalHandler(std::forward<Task>(task)),
      };
    };

    std::tuple sender_and_handlers = {
      into_sender_and_handler(std::forward<typename TypeTrait<I>::Task>(std::get<I>(*this)))...};

    (CallDoSuspend<I>(std::get<I>(std::move(sender_and_handlers))), ...);
  }

  template <std::size_t I, class ETuple>
  void CallDoSuspend(ETuple&& tuple)
  {
    DoSuspend<I>(std::get<0>(std::forward<ETuple>(tuple)), std::get<1>(std::forward<ETuple>(tuple)));
  }

  template <std::size_t I, class MiddleSender, class FinalHandler>
  void DoSuspend(MiddleSender&& middle_sender, FinalHandler&& final_handler)
  {
    using MiddleResult = typename TypeTrait<I>::MiddleResult;
    using RawResult    = typename TypeTrait<I>::RawResult;

    // 若当前该任务没有调度出去执行，则该任务会在此处执行到结束，我们需要避免它将本协程直接 resume，
    // 从而导致在该协程后的协程得不到调度
    const bool is_inline = not(TypeTrait<I>::has_executor or exe_.IsValid());

    if constexpr (std::is_void_v<MiddleResult>) {
      Spawn(
        unifex::then(
          std::forward<MiddleSender>(middle_sender),
          [ctx{ctx_}, final_handler{std::forward<FinalHandler>(final_handler)}, is_inline]() {
            if (not ctx->TryResume())
              return;

            if constexpr (std::is_void_v<RawResult>) {
              final_handler();
              ctx->template SetResultAndResume<I>(Void{}, is_inline);
            } else {
              ctx->template SetResultAndResume<I>(final_handler(), is_inline);
            }
          }));
    } else {
      Spawn(
        unifex::then(
          std::forward<MiddleSender>(middle_sender),
          [ctx{ctx_}, final_handler{std::forward<FinalHandler>(final_handler)}, is_inline](MiddleResult&& value) {
            if (not ctx->TryResume())
              return;

            if constexpr (std::is_void_v<RawResult>) {
              final_handler(std::move(value));
              ctx->template SetResultAndResume<I>(Void{}, is_inline);
            } else {
              ctx->template SetResultAndResume<I>(final_handler(std::move(value)), is_inline);
            }
          }));
    }
  }

  template <class Sender>
  void Spawn(Sender&& sender, AIMRTE(src(loc)))
  {
    if (exe_.IsValid())
      scope_->spawn_on(core::details::GetScheduler(exe_, loc), std::forward<Sender>(sender));
    else
      scope_->spawn(std::forward<Sender>(sender));
  }

 private:
  static aimrt::co::AsyncScope& GetGlobalScope()
  {
    return core::Context::GetAsyncScope(*core::details::ExpectContext(std::source_location::current()));
  }

  struct Context {
    std::coroutine_handle<> continuation;
    res::Executor original_executor;

    // 标记处理结果
    std::atomic_bool used{false};
    std::optional<Result> result;

    // 决定 any 的协程是否原地继续执行（若有协程在 any suspend 过程中执行完毕时，将设置该值）
    bool inline_resume{false};

    [[nodiscard]] bool Done() const
    {
      return used.load(std::memory_order::relaxed);
    }

    bool TryResume()
    {
      return used.exchange(true, std::memory_order::relaxed) == false;
    }

    template <std::size_t I, class Ri>
    void SetResultAndResume(Ri&& value, const bool is_inline)
    {
      result.emplace(MakeOfIdx<I>(std::forward<Ri>(value)));

      if (not is_inline) {
        if (original_executor.IsValid())
          // TODO: 不用 ctx 接口
          ctx::exe(original_executor).Post([h{continuation}]() {
            h.resume();
          });
        else
          continuation.resume();
      } else
        inline_resume = true;
    }
  };

  // 使用当前所在的执行器，在 any 被 resume 时继续所在协程的执行
  res::Executor curr_exe_{core::details::g_thread_ctx.exe};

  // any 等待的若干协程执行环境以及相关参数
  aimrt::co::AsyncScope* scope_{&GetGlobalScope()};
  res::Executor exe_{curr_exe_};

  // 这些协程以及 any 所在协程共同持有的一份上下文数据
  std::shared_ptr<Context> ctx_;
};
}  // namespace aimrte::sync
