// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>

namespace aimrte::utils
{
/**
 * @brief 获取指定的环境变量值
 * @param name 环境变量名称
 * @param fallback 如果环境变量不存在，则代替返回的值
 */
std::string Env(const std::string_view& name, const std::string_view& fallback = "");
}  // namespace aimrte::utils
