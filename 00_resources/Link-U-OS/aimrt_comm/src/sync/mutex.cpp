// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./mutex.h"

namespace aimrte::sync::v1
{
co::Task<void> Mutex::Lock()
{
  co_return co_await impl_.async_lock();
}

co::Task<std::unique_lock<Mutex>> Mutex::ScopedLock()
{
  co_await Lock();
  co_return std::unique_lock{*this, std::adopt_lock};
}

bool Mutex::TryLock()
{
  return impl_.try_lock();
}

void Mutex::Unlock()
{
  impl_.unlock();
}
}  // namespace aimrte::sync::v1

namespace aimrte::sync::v2
{
bool Mutex::Awaiter::await_ready() const
{
  return mutex.TryLock();
}

bool Mutex::Awaiter::await_suspend(const std::coroutine_handle<> continuation)
{
  continuation_ = continuation;
  return mutex.LockAndSuspend(this);
}

Mutex::Mutex()
    : state_(UnlockedState())
{
}

bool Mutex::TryLock()
{
  void* curr_state = UnlockedState();
  return state_.compare_exchange_strong(curr_state, nullptr, std::memory_order::acquire, std::memory_order::relaxed);
}

co::Task<void> Mutex::Lock()
{
  co_await Awaiter(*this);
}

co::Task<std::unique_lock<Mutex>> Mutex::ScopedLock()
{
  co_await Lock();
  co_return std::unique_lock(*this, std::adopt_lock);
}

void Mutex::Unlock()
{
  // 当前互斥量带锁，以下操作不会被并发。
  // 若有 awaiter 在队列里等待，则保持互斥量上锁状态，直接唤醒它即可
  if (awaiter_ != nullptr) {
    Awaiter* awaiter_to_resume = awaiter_;
    awaiter_                   = awaiter_->next_;
    awaiter_to_resume->continuation_.resume();
    return;
  }

  // awaiter 队列为空，检查当前状态是否有被排队的 awaiter，
  // 若有，则将它们压入队列并唤醒；
  // 若没有，则解锁本互斥量。
  // 访问 state_ 会与其他期望上锁的用户并发。
  while (true) {
    void* old_value = state_.load(std::memory_order::relaxed);

    // 若只有当前用户持有本互斥量，则尝试解锁
    if (old_value == nullptr) {
      if (state_.compare_exchange_weak(old_value, UnlockedState(), std::memory_order::release, std::memory_order::relaxed))
        return;
      else
        continue;
    }

    // state 有非零值，必然是某个排队加锁的 awaiter 指针，因此我们需要保持加锁状态，
    // 使用 acquire，确保后边锁域内的读写不会被重排上来
    assert(old_value != UnlockedState());
    old_value = state_.exchange(nullptr, std::memory_order::acquire);

    assert(old_value != UnlockedState() and old_value != nullptr);
    awaiter_ = static_cast<Awaiter*>(old_value);

    // 取出排队中的 awaiter，准备对其进行操作
    break;
  }

  // 在 state_ 中的 awaiter 形成了 LIFO 队列，我们将其翻转为 FIFO 队列
  assert(awaiter_ != nullptr);
  Awaiter* next = nullptr;
  Awaiter* curr = awaiter_;

  do {
    Awaiter* next_curr = curr->next_;
    curr->next_        = next;

    next = curr;
    curr = next_curr;
  } while (curr != nullptr);

  // 弹出并唤醒第一个 awaiter
  assert(next != nullptr);
  awaiter_ = next->next_;
  next->continuation_.resume();
}

bool Mutex::LockAndSuspend(Awaiter* awaiter)
{
  while (true) {
    // 先获取互斥量的状态
    void* old_state = state_.load(std::memory_order::relaxed);

    if (old_state == UnlockedState()) {
      // 当前互斥量没有上锁，尝试进行加锁。加锁成功时，使用了 acquire，确保后边锁域内的读写不会被重排上来。
      // 加锁失败时，继续循环下一次尝试
      if (state_.compare_exchange_weak(old_state, nullptr, std::memory_order::acquire, std::memory_order::relaxed))
        return false;
    } else {
      // 尝试将自己放到等待上锁的队列里，并将原来在队列里的 Awaiter 挂在本 Awaiter 的下一个中。
      // 使用 release，和 Unlock() 中的取出 state_ 里正在排队的 awaiter 形成 happen-before 关系
      awaiter->next_ = static_cast<Awaiter*>(old_state);
      if (state_.compare_exchange_weak(old_state, awaiter, std::memory_order::release, std::memory_order::relaxed)) {
        return true;
      }
    }
  }
}

void* Mutex::UnlockedState() const
{
  return const_cast<Mutex*>(this);
}
}  // namespace aimrte::sync::v2
