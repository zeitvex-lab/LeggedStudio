// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./loop.h"
#include "src/panic/panic.h"
#include "./anytime.h"

namespace aimrte::ctx
{
Loop::Loop(const std::chrono::steady_clock::duration period)
    : period_(period)
{
}

Loop::Loop(const std::uint32_t hz)
    : Loop(std::chrono::nanoseconds(1000'000'000ull / hz))
{
}

co::Task<bool> Loop::Ok(const std::source_location loc)
{
  // 无睡眠的循环，直接返回
  if (period_.count() == 0)
    co_return ctx::Ok(loc);

  // 尽量减少系统调用。使用 += dt 的方式更新时间点，虽略有误差，但能减少开销；
  // 若 sleep 后被重新调度的时机很靠后， += dt 的时间点会比实际更早，但也说明 loop 已滞后，需要被快速再次调用
  const auto now_tp = std::chrono::steady_clock::now();
  const auto dt     = period_ - (now_tp - tp_);

  if (dt.count() > 0) {
    co_await ctx::Sleep(dt, loc);
    tp_ += dt;
  } else {
    tp_ = now_tp;
  }

  co_return ctx::Ok(loc);
}
}  // namespace aimrte::ctx
