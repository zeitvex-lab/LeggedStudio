// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <concepts>

namespace aimrte::trait::details
{
template <class F>
concept VoidFunctionTrait =
  requires(F&& func) {
    {
      func()
      } -> std::same_as<void>;
  };
}  // namespace aimrte::trait::details

namespace aimrte::trait
{
template <details::VoidFunctionTrait TVoidOp>
struct otherwise : TVoidOp {
  using TVoidOp::operator();
};

template <details::VoidFunctionTrait TVoidOp>
constexpr void operator||(const bool con, otherwise<TVoidOp>&& ops)
{
  if (not con)
    ops();
}
}  // namespace aimrte::trait
