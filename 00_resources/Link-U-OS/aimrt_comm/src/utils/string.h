// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>
#include <vector>

namespace aimrte::utils
{
/**
 * @brief 使用给定分割子字符串，分割指定字符串，并将分割产生的多个子字符串进行前后空格删除
 */
std::vector<std::string> SplitTrim(const std::string_view& str, char separator);
}  // namespace aimrte::utils
