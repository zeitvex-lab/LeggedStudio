// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/macro/macro.h"

/**
 * @brief 创建一个协程锁域
 *
 * @code
 *   // 已知存在一个协程互斥量
 *   aimrte::sync::Mutex m;
 *
 *   // 基于它创建一个锁域
 *   AIMRTE(co_sync(m)) {
 *     // m 加锁的范围，离开该范围时，自动解锁。
 *   }
 * @endcode
 */
#define AIMRTE_DETAILS_co_sync(...) AIMRTE_DETAILS_co_sync_DO
#define AIMRTE_DETAILS_co_sync_DO(_co_sync_pack_)                              \
  if constexpr (                                                               \
    std::unique_lock AIMRTE_LINE_UNIQUE(_lock_) =                              \
      co_await AIMRTE_DETAILS_co_sync_DO_UNPACK_##_co_sync_pack_.ScopedLock(); \
    false)                                                                     \
    ;                                                                          \
  else
#define AIMRTE_DETAILS_co_sync_DO_UNPACK_co_sync(_mutex_) _mutex_
