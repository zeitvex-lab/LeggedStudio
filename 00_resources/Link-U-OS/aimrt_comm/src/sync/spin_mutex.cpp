// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/ctx/ctx.h"

#include "./spin_mutex.h"

namespace aimrte::sync
{
SpinMutex::SpinMutex(int spin_counter)
    : spin_counter_(spin_counter)
{
}

bool SpinMutex::TryLock()
{
  return locked_.exchange(true, std::memory_order::acquire) == false;  // 交换出来的旧值是 false，说明该互斥量被我们加锁
}

co::Task<void> SpinMutex::Lock()
{
  while (not TryLock()) {
    int counter = spin_counter_;

    while (locked_.load(std::memory_order::relaxed)) {
      if (--counter < 0) {
        co_await ctx::Yield();
        counter = spin_counter_;
      }
    }
  }
}

co::Task<std::unique_lock<SpinMutex>> SpinMutex::ScopedLock()
{
  co_await Lock();
  co_return std::unique_lock{*this, std::adopt_lock};
}

void SpinMutex::Unlock()
{
  locked_.store(false, std::memory_order::release);
}
}  // namespace aimrte::sync
