// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/coroutine.h"
#include <unifex/async_mutex.hpp>

namespace aimrte::sync::v1
{
class Mutex
{
 public:
  co::Task<void> Lock();

  co::Task<std::unique_lock<Mutex>> ScopedLock();

  bool TryLock();

  void Unlock();

 public:
  // 为 std::unique_lock 提供接口
  void lock() { Lock().Sync(); }
  void unlock() { Unlock(); }

 private:
  unifex::async_mutex impl_;
};
}  // namespace aimrte::sync::v1

namespace aimrte::sync::v2
{
class Mutex
{
  struct Awaiter {
    Mutex& mutex;
    std::coroutine_handle<> continuation_;
    Awaiter* next_{nullptr};

    bool await_ready() const;
    bool await_suspend(std::coroutine_handle<> continuation);
    static constexpr void await_resume() {}
  };

 public:
  Mutex();

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
  co::Task<std::unique_lock<Mutex>> ScopedLock();

  /**
   * @brief 解锁本互斥量
   */
  void Unlock();

 public:
  // 为 std::unique_lock 提供接口
  void lock() { Lock().Sync(); }
  void unlock() { Unlock(); }

 private:
  /**
   * @brief 在 Awaiter 的 suspend 中调用，将 Awaiter 自己加入排队等待加锁的 LIFO 队列中
   * @return 是否挂起。若在这一步中抢到了锁，则无需挂起协程，继续执行即可。
   */
  bool LockAndSuspend(Awaiter* awaiter);

  /**
   * @return 用于代表本互斥量未加锁的状态值，也即本互斥量的指针地址
   */
  void* UnlockedState() const;

 private:
  // this mutex  : unlocked.
  // nullptr     : locked, no user is queued to lock.
  // some awaiter: locked, some users are queued to lock.
  std::atomic<void*> state_;

  // 等待被唤醒的 Awaiater 的 FIFO 队列。仅加锁的用户在 Unlock 时操作
  Awaiter* awaiter_{nullptr};
};
}  // namespace aimrte::sync::v2

namespace aimrte::sync
{
using Mutex = v2::Mutex;
}
