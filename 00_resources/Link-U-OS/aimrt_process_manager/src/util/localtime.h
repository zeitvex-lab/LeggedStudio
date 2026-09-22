// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <time.h>

// 使用redis里面 fork-safe 的localtime 函数, 避免子进程死锁
/* We use a private localtime implementation which is fork-safe. The logging
 * function of Redis may be called from other threads. */
void nolocks_localtime(struct tm *tmp, time_t t, time_t tz, int dst);


// 获取时区偏移全局变量
long getTimeZone(void);
