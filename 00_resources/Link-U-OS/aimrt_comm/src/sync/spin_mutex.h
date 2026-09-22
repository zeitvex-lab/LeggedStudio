// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/coroutine.h"
#include <atomic>
#include <memory>

namespace aimrte::sync
{
class SpinMutex
{
 public:
  explicit SpinMutex(int spin_counter = 1024);

  /**
   * @brief 尝试加锁，返回成功与否
   */
  bool TryLock();

  /**
   * @brief 加锁本互斥量
   */
  co::Task<void> Lock();

  /**
   * @brief 加锁本互斥量，并返回一个自动解锁的对象
   */
  co::Task<std::unique_lock<SpinMutex>> ScopedLock();

  /**
   * @brief 解锁本对象
   */
  void Unlock();

 public:
  // 为 std::unique_lock 提供接口
  void lock() { Lock().Sync(); }
  void unlock() { Unlock(); }

 private:
  // 快速轮询次数
  int spin_counter_{};

  // 是否上锁
  std::atomic_bool locked_{false};
};
}  // namespace aimrte::sync
