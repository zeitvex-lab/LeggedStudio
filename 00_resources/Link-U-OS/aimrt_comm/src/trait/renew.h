// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <utility>

namespace aimrte::trait
{
/**
 * @brief 重新构造一个对象。
 */
template <class T, class... Args>
void renew(T& obj, Args&&... args)
{
  obj.~T();
  new (&obj) T(std::forward<Args>(args)...);
}
}  // namespace aimrte::trait
