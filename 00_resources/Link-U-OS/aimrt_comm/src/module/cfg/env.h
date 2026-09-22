// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>

namespace aimrte::cfg::details
{
static constexpr std::string_view ENV_PROCESS_NAME{"__AIMRTE_PROCESS_NAME"};

/**
 * @return 进程名称
 */
std::string ProcName();
}  // namespace aimrte::cfg::details
