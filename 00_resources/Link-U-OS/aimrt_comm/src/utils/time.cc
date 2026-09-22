// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./time.h"

namespace aimrte::utils
{

uint64_t GetCurrentTimestamp()
{
  auto now      = std::chrono::system_clock::now();
  auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch());
  return duration.count();
}

}  // namespace aimrte::utils
