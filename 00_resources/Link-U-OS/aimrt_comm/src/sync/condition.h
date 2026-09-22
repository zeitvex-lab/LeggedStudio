// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <condition_variable>
#include <mutex>

namespace aimrte::sync
{
/**
 * @brief 用于多线程同步的布尔条件类，对 mutex 与 condition_variable 的方便封装
 * @todo 改成同时支持协程的操作，类似 core::details::Sleeper，但让操作子本身是 awaiter
 */
class Condition
{
 public:
  Condition(bool value = false);  // NOLINT(google-explicit-constructor)

  /**
   * @brief 析构时，将调用 fail() 函数，使其他正在等待条件变换的线程退出等待。
   */
  ~Condition();

  /**
   * @brief 设置当前条件的值；但是，即使设置为 true，也不会释放其它正在等待条件满足的线程。
   * @param value
   */
  void Init(bool value = false);

  /**
   * @brief 等待条件成立。
   * @return 条件是否被满足；返回 false 只有一种可能：条件被标识为永远无法被满足（也即调用了 fail() 函数）。
   */
  bool Wait() const;

  /**
   * @brief 使条件满足，将释放所有正在等待条件满足的线程。
   */
  void Satisfy();

  /**
   * @brief 标识条件永远无法被满足，将释放所有正在等待条件满足的线程，并使他们返回 false.
   */
  void Fail();

  /**
   * @return 本条件的值
   */
  operator bool() const;  // NOLINT(google-explicit-constructor)

 private:
  mutable std::condition_variable condition_;
  mutable std::mutex mutex_;

  bool value_  = false;  // 标识本条件的成立状态
  bool failed_ = false;  // 标识本条件是否无法被满足
};
}  // namespace aimrte::sync
