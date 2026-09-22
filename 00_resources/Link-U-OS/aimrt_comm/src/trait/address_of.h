// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>

namespace aimrte::trait
{
template <class T>
std::shared_ptr<T> AddressOf(T& ptr)
{
  return {
    &ptr,
    [](T*) {},
  };
}
}  // namespace aimrte::trait
