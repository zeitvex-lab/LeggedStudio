// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <optional>

namespace aimrte
{
template <class T>
class Ref
{
 public:
  explicit Ref(T&& rvalue)
      : tmp_(std::move(rvalue)), ref_(tmp_.value())
  {
  }

  explicit Ref(T& value)
      : ref_(value)
  {
  }

  T& ref()
  {
    return ref_;
  }

  const T& ref() const
  {
    return ref_;
  }

 private:
  std::optional<T> tmp_;
  T& ref_;
};
}  // namespace aimrte
