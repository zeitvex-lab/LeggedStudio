// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <stdint.h>
#include <string>

namespace aimrte::utils
{

/**
 * @brief 生成唯一ID
 * 格式: | 32 bits | 16 bits | 16 bits |
 *       |   pid   | thr_id  |  count  |
 * @return 生成的64位唯一ID
 */
uint64_t GenerateUniqueID();

/**
 * @brief 生成UUID
 * 格式：7ab011a0-0a9d-41f5-9b43-36c71c449307
 * @return 生成的uuid字符串
 */
std::string GenerateUuid();

}  // namespace aimrte::utils
