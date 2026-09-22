// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"

namespace aimrte::ctx
{
/**
 * @brief 初始化 AimRTe 上下文并返回它，
 *        用户需要确保该上下文、与使用了 aimrte::ctx 接口的模块保持一样的生命周期。
 */
std::shared_ptr<core::Context> Init(aimrt::CoreRef core_ref);

namespace internal
{
/**
 * @brief 初始化 AimRTe 上下文，但不挂载子系统，仅用于插件。
 */
std::shared_ptr<core::Context> InitWithoutSubsystems(aimrt::CoreRef core_ref);
}  // namespace internal
}  // namespace aimrte::ctx
