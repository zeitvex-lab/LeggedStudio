// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <chrono>
#include <cstdint>
#include "./run.h"

namespace aimrte::ctx
{
class Loop
{
 public:
  Loop() = default;
  explicit Loop(std::chrono::steady_clock::duration period);
  explicit Loop(std::uint32_t hz);

  co::Task<bool> Ok(AIMRTE(src(loc)));

 private:
  std::chrono::steady_clock::duration period_{};
  std::chrono::steady_clock::time_point tp_{};
};
}  // namespace aimrte::ctx
