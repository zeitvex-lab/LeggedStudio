// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>
#include "./condition.h"

namespace aimrte::sync
{
/**
 * @brief 用于多线程同步的barrier类，用计数方式进行判断。
 */
class Barrier
{
 public:
  explicit Barrier(size_t count) : thread_nums_(count), count_(count) {}
  ~Barrier() { condition_.Fail(); }

  Barrier(Barrier const&)            = delete;
  Barrier& operator=(Barrier const&) = delete;

  void Init();
  void Wait();

 private:
  Condition condition_;

  size_t thread_nums_;
  std::atomic<size_t> count_;
};
}  // namespace aimrte::sync
