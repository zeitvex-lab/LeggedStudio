// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <type_traits>
#include <utility>

namespace aimrte::trait
{
template <class T>
  requires(not std::is_rvalue_reference_v<T>)
constexpr T& as_is(std::remove_reference_t<T>& obj) noexcept
{
  return obj;
}

template <class T>
  requires(std::is_rvalue_reference_v<T>)
constexpr T&& as_is(std::remove_reference_t<T>& obj) noexcept
{
  return std::move(obj);
}
}  // namespace aimrte::trait
