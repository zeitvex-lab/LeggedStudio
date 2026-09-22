// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "./concat.h"

/**
 * @brief 创建出现次数唯一命名（同一份文件内）
 * @code
 *   int AIMRTE_COUNTER_UNIQUE(a) = 1;
 *   int AIMRTE_COUNTER_UNIQUE(a) = 2;
 *   int AIMRTE_COUNTER_UNIQUE(a) = 3;
 * @endcode
 */
#define AIMRTE_COUNTER_UNIQUE(_x_) AIMRTE_CONCAT(_x_, _COUNTER_UNIQUE_, __COUNTER__)

/**
 * @brief 创建代码行内唯一命名
 * @code
 *   int AIMRTE_LINE_UNIQUE(a) = 1; AIMRTE_LINE_UNIQUE(a) = -1;
 *   int AIMRTE_LINE_UNIQUE(a) = 2; AIMRTE_LINE_UNIQUE(a) = -2;
 * @endcode
 */
#define AIMRTE_LINE_UNIQUE(_x_) AIMRTE_CONCAT(_x_, _LINE_UNIQUE_, __LINE__)
