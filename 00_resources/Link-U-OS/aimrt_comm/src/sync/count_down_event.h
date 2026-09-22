// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>

#include "./condition_variable.h"
#include "./mutex.h"

namespace aimrte::sync
{
class CountDownEvent
{
 public:
  explicit CountDownEvent(int value);

 private:
  Mutex mutex_;
  ConditionVariable<Mutex> cv_;
  int count_{0};
};
}  // namespace aimrte::sync
