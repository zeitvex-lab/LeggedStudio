// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./get_scheduler.h"

namespace aimrte::core::details
{
aimrt::co::AimRTScheduler GetScheduler(const res::Executor& exe, std::source_location loc)
{
  return aimrt::co::AimRTScheduler(
    Context::OpExe::GetRawRef(
      ExpectContext(loc)->exe(exe)));
}
}  // namespace aimrte::core::details
