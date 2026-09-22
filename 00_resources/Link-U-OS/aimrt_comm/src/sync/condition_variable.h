// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/coroutine.h"
#include <memory>

#include "./mutex.h"

namespace aimrte::sync
{
template <class TMutex>
class ConditionVariable
{
  struct Awaiter {
    ConditionVariable& cv;
    TMutex& mutex;
    std::coroutine_handle<> continuation_;
    Awaiter* next_{nullptr};

    static constexpr bool await_ready() { return false; }
    void await_suspend(std::coroutine_handle<> continuation);
    static constexpr void await_resume() {}
  };

 public:
  /**
   * @brief 开始等待本 cv 信号
   * @param lock 已经上锁的锁对象
   */
  co::Task<void> Wait(std::unique_lock<TMutex>& lock);

  /**
   * @brief 在前置条件不成立的情况下，等待本 cv 信号，若信号到来时，条件仍然不满足，将继续等待
   * @tparam FPred 返回可用于 bool 判断类型的无参函数
   * @param lock 已经上锁的锁对象
   */
  template <class FPred>
  co::Task<void> Wait(std::unique_lock<TMutex>& lock, FPred&& func);

  /**
   * @brief 尝试唤醒一个等待者
   */
  void NotifyOne();

  /**
   * @brief 尝试唤醒所有的等待者
   */
  void NotifyAll();

 private:
  void Notify(bool all);

 private:
  std::atomic<Awaiter*> awaiter_{nullptr};
};
}  // namespace aimrte::sync

namespace aimrte::sync
{
template <class TMutex>
void ConditionVariable<TMutex>::Awaiter::await_suspend(std::coroutine_handle<> continuation)
{
  continuation_ = continuation;

  // 用于解锁
  std::unique_lock lock(mutex, std::adopt_lock);

  // 将本 awaiter 压入队列中，同时，还要记住原本在队列头的 awaiter，
  // 本函数可能会和 notify 流程并发
  next_ = cv.awaiter_.load(std::memory_order::relaxed);
  while (not cv.awaiter_.compare_exchange_weak(next_, this, std::memory_order::acquire, std::memory_order::relaxed))
    ;
}

template <class TMutex>
co::Task<void> ConditionVariable<TMutex>::Wait(std::unique_lock<TMutex>& lock)
{
  co_await Awaiter{*this, *lock.mutex()};
  co_await lock.mutex()->Lock();
}

template <class TMutex>
template <class FPred>
co::Task<void> ConditionVariable<TMutex>::Wait(std::unique_lock<TMutex>& lock, FPred&& func)
{
  while (not func()) {
    co_await Wait(lock);
  }
}

template <class TMutex>
void ConditionVariable<TMutex>::NotifyOne()
{
  Notify(false);
}

template <class TMutex>
void ConditionVariable<TMutex>::NotifyAll()
{
  Notify(true);
}

template <class TMutex>
void ConditionVariable<TMutex>::Notify(const bool all)
{
  // 尝试取出 awaiter LIFO 队列的头元素，并将下一个（或空指针，若取全部的话）计入
  Awaiter* head = awaiter_.load(std::memory_order::relaxed);

  do {
    if (head == nullptr)
      return;
  } while (not awaiter_.compare_exchange_weak(head, all ? nullptr : head->next_, std::memory_order::release, std::memory_order::relaxed));

  // 唤醒 awaiter
  if (not all)
    head->next_ = nullptr;

  do {
    head->continuation_.resume();
    head = head->next_;
  } while (head != nullptr);
}
}  // namespace aimrte::sync
