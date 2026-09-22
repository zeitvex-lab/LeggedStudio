// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"

/// 各种修饰下的协程类型
namespace aimrte::co::details
{
template <class T, class FThen>
  requires(std::invocable<FThen, T>)
struct TaskOnExeThen {
  Task<T> task;
  res::Executor exe;
  FThen f_then;
};

template <class T>
struct TaskOnExe {
  Task<T> task;
  res::Executor exe;

  template <class FThen>
  TaskOnExeThen<T, FThen> operator|(FThen&& f_then) &&
  {
    return {std::move(task), std::move(exe), std::forward<FThen>(f_then)};
  }
};

template <class T, class FThen>
  requires(std::invocable<FThen, T>)
struct TaskThen {
  Task<T> task;
  FThen f_then;

  TaskOnExeThen<T, FThen> operator|(const res::Executor& exe) &&
  {
    return {std::move(task), exe, std::move(f_then)};
  }
};
}  // namespace aimrte::co::details

namespace aimrte::co
{
template <class T>
details::TaskOnExe<T> operator|(Task<T>&& task, const res::Executor& exe)
{
  return {std::move(task), exe};
}

template <class T, class FThen>
details::TaskThen<T, FThen> operator|(Task<T>&& task, FThen&& f_then)
{
  return {std::move(task), std::forward<FThen>(f_then)};
}
}  // namespace aimrte::co

/// 获取任意协程类型的返回值
namespace aimrte::co::details
{
template <class TTask>
struct ReturnValueTypeTrait;

template <class T>
struct ReturnValueTypeTrait<Task<T>> {
  using Type = T;
};

template <class T>
struct ReturnValueTypeTrait<TaskOnExe<T>> {
  using Type = T;
};

template <class T, class FThen>
struct ReturnValueTypeTrait<TaskThen<T, FThen>> {
  using Type = decltype(std::declval<FThen>()(std::declval<T>()));
};

template <class T, class FThen>
struct ReturnValueTypeTrait<TaskOnExeThen<T, FThen>> {
  using Type = decltype(std::declval<FThen>()(std::declval<T>()));
};

template <class TTask>
  requires(std::invocable<TTask>)
struct ReturnValueTypeTrait<TTask> {
  using Type = typename ReturnValueTypeTrait<decltype(std::declval<TTask>()())>::Type;
};
}  // namespace aimrte::co::details

/// 将任意类型的协程转换为 unifex sender
namespace aimrte::co::details
{
template <class TTask>
struct IntoSenderTrait;

template <class T>
struct IntoSenderTrait<Task<T>> {
  static auto Do(Task<T>&& task, AIMRTE(src()))
  {
    return MoveIntoSender(task);
  }
};

template <class T>
struct IntoSenderTrait<TaskOnExe<T>> {
  static auto Do(TaskOnExe<T>&& task, AIMRTE(src(loc)))
  {
    return unifex::on(core::details::GetScheduler(task.exe, loc), MoveIntoSender(task.task));
  }
};

template <class T, class FThen>
struct IntoSenderTrait<TaskThen<T, FThen>> {
  static auto Do(TaskThen<T, FThen>&& task, AIMRTE(src()))
  {
    return unifex::then(MoveIntoSender(task.task), std::move(task.f_then));
  }
};

template <class T, class FThen>
struct IntoSenderTrait<TaskOnExeThen<T, FThen>> {
  static auto Do(TaskOnExeThen<T, FThen>&& task, AIMRTE(src(loc)))
  {
    return unifex::then(
      unifex::on(core::details::GetScheduler(task.exe, loc), MoveIntoSender(task.task)),
      std::move(task.f_then));
  }
};

template <class TTask>
  requires(std::invocable<TTask>)
struct IntoSenderTrait<TTask> {
  static auto Do(TTask&& f_task, AIMRTE(src(loc)))
  {
    return IntoSenderTrait<decltype(std::declval<TTask>()())>::Do(f_task(), loc);
  }
};

template <class TTask>
auto IntoSender(TTask&& task, AIMRTE(src(loc)))
{
  return IntoSenderTrait<TTask>::Do(std::forward<TTask>(task), loc);
}
}  // namespace aimrte::co::details

/// 获取任意协程类型的中间返回值（不考虑经过最终的处理函数的结果）
namespace aimrte::co::details
{
template <class TTask>
struct MiddleReturnValueTypeTrait;

template <class T>
struct MiddleReturnValueTypeTrait<Task<T>> {
  using Type = T;
};

template <class T>
struct MiddleReturnValueTypeTrait<TaskOnExe<T>> {
  using Type = T;
};

template <class T, class FThen>
struct MiddleReturnValueTypeTrait<TaskThen<T, FThen>> {
  using Type = T;
};

template <class T, class FThen>
struct MiddleReturnValueTypeTrait<TaskOnExeThen<T, FThen>> {
  using Type = T;
};

template <class TTask>
  requires(std::invocable<TTask>)
struct MiddleReturnValueTypeTrait<TTask> {
  using Type = typename MiddleReturnValueTypeTrait<decltype(std::declval<TTask>()())>::Type;
};
}  // namespace aimrte::co::details

/// 将任意类型的协程转换为 unifex sender，其中，排除最后一步的后处理
namespace aimrte::co::details
{
template <class TTask>
struct IntoMiddleSenderTrait;

template <class T>
struct IntoMiddleSenderTrait<Task<T>> {
  static auto Do(Task<T>&& task, AIMRTE(src(loc)))
  {
    return MoveIntoSender(task);
  }
};

template <class T>
struct IntoMiddleSenderTrait<TaskOnExe<T>> {
  static auto Do(TaskOnExe<T>&& task, AIMRTE(src(loc)))
  {
    return unifex::on(core::details::GetScheduler(task.exe, loc), MoveIntoSender(task.task));
  }
};

template <class T, class FThen>
struct IntoMiddleSenderTrait<TaskThen<T, FThen>> {
  static auto Do(TaskThen<T, FThen>&& task, AIMRTE(src()))
  {
    return MoveIntoSender(task.task);
  }
};

template <class T, class FThen>
struct IntoMiddleSenderTrait<TaskOnExeThen<T, FThen>> {
  static auto Do(TaskOnExeThen<T, FThen>&& task, AIMRTE(src(loc)))
  {
    return unifex::on(core::details::GetScheduler(task.exe, loc), MoveIntoSender(task.task));
  }
};

template <class TTask>
  requires(std::invocable<TTask>)
struct IntoMiddleSenderTrait<TTask> {
  static auto Do(TTask&& f_task, AIMRTE(src(loc)))
  {
    return IntoMiddleSenderTrait<decltype(std::declval<TTask>()())>::Do(f_task(), loc);
  }
};

template <class TTask>
auto IntoMiddleSender(TTask&& task, AIMRTE(src(loc)))
{
  return IntoMiddleSenderTrait<TTask>::Do(std::forward<TTask>(task), loc);
}
}  // namespace aimrte::co::details

/// 获取任意类型协程的后处理过程
namespace aimrte::co::details
{
template <class TTask>
struct IntoFinalHandlerTrait;

template <class T>
struct IntoFinalHandlerTrait<Task<T>> {
  static auto Do(Task<T>&&, AIMRTE(src()))
  {
    if constexpr (not std::is_void_v<T>)
      return [](T&& result) {
        return std::move(result);
      };
    else
      return []() {};
  }
};

template <class T>
struct IntoFinalHandlerTrait<TaskOnExe<T>> {
  static auto Do(TaskOnExe<T>&&, AIMRTE(src()))
  {
    if constexpr (not std::is_void_v<T>)
      return [](T&& result) {
        return std::move(result);
      };
    else
      return []() {};
  }
};

template <class T, class FThen>
struct IntoFinalHandlerTrait<TaskThen<T, FThen>> {
  static auto Do(TaskThen<T, FThen>&& task, AIMRTE(src()))
  {
    return std::move(task.f_then);
  }
};

template <class T, class FThen>
struct IntoFinalHandlerTrait<TaskOnExeThen<T, FThen>> {
  static auto Do(TaskOnExeThen<T, FThen>&& task, AIMRTE(src()))
  {
    return std::move(task.f_then);
  }
};

template <class TTask>
  requires(std::invocable<TTask>)
struct IntoFinalHandlerTrait<TTask> {
  static auto Do(TTask&& f_task, AIMRTE(src(loc)))
  {
    return IntoFinalHandlerTrait<decltype(std::declval<TTask>()())>::Do(f_task(), loc);
  }
};

template <class TTask>
auto IntoFinalHandler(TTask&& task, AIMRTE(src(loc)))
{
  return IntoFinalHandlerTrait<TTask>::Do(std::forward<TTask>(task), loc);
}
}  // namespace aimrte::co::details

/// 检查任意类型协程是否含有执行器
namespace aimrte::co::details
{
template <class TTask>
struct HasExecutorTrait;

template <class T>
struct HasExecutorTrait<Task<T>> {
  constexpr static bool value = false;
};

template <class T>
struct HasExecutorTrait<TaskOnExe<T>> {
  constexpr static bool value = true;
};

template <class T, class FThen>
struct HasExecutorTrait<TaskThen<T, FThen>> {
  constexpr static bool value = false;
};

template <class T, class FThen>
struct HasExecutorTrait<TaskOnExeThen<T, FThen>> {
  constexpr static bool value = true;
};

template <class TTask>
  requires(std::invocable<TTask>)
struct HasExecutorTrait<TTask> {
  constexpr static bool value = HasExecutorTrait<decltype(std::declval<TTask>()())>::value;
};

template <class TTask>
constexpr inline bool has_executor = HasExecutorTrait<TTask>::value;
}  // namespace aimrte::co::details
