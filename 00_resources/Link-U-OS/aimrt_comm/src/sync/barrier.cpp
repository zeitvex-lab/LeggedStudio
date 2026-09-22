// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "barrier.h"

namespace aimrte::sync
{
void Barrier::Init()
{
  condition_.Init();
}

void Barrier::Wait()
{
  if (--count_ == 0) {
    count_ = thread_nums_;
    condition_.Satisfy();
  } else {
    condition_.Wait();
  }
}
}  // namespace aimrte::sync
