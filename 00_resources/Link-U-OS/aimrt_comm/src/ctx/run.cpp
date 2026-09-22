// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./run.h"

namespace aimrte::ctx
{
details::RunningExecutorRef exe(res::Executor&& exe, const std::source_location call_loc)
{
  return {std::move(exe), call_loc};
}

details::RunningExecutorRef exe(const res::Executor& exe, const std::source_location call_loc)
{
  return {exe, call_loc};
}

co::Task<void> Sleep(const std::chrono::steady_clock::duration& duration, const std::source_location loc)
{
  if (const res::Executor& exe = core::details::g_thread_ctx.exe; exe.IsValid())
    co_await aimrt::co::ScheduleAfter(core::details::GetScheduler(exe, loc), duration);
  else
    std::this_thread::sleep_for(duration);
}

co::Task<void> Yield(const std::source_location loc)
{
  if (const res::Executor& exe = core::details::g_thread_ctx.exe; not co::synchronized and exe.IsValid())
    co_await aimrt::co::Schedule(core::details::GetScheduler(exe, loc));
  else
    std::this_thread::yield();  // FIXME ，如果在一个 exe 上，且该 exe sync await，如果执行 this_thread::yield() 会导致其他协程不会进来调度。导致一个协程一直 yield，会拉高 CPU
}
}  // namespace aimrte::ctx
