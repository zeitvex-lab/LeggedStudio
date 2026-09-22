// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "./context.h"

namespace aimrte::core::details
{
/**
 * @brief 从当前模块上下文中，获取指定执行器的调度器
 */
aimrt::co::AimRTScheduler GetScheduler(const res::Executor& exe, std::source_location loc);
}  // namespace aimrte::core::details
