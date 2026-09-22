// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::trait
{
template <class T>
constexpr decltype(auto) remove_const(const T& x)
{
  return const_cast<T&>(x);
}

template <class T>
constexpr decltype(auto) remove_const(const T* x)
{
  return const_cast<T*>(x);
}

template <class T>
constexpr decltype(auto) add_const(T& x)
{
  return const_cast<const T&>(x);
}

template <class T>
constexpr decltype(auto) add_const(T* x)
{
  return const_cast<const T*>(x);
}
}  // namespace aimrte::trait
