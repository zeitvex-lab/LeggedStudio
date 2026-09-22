// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::trait
{
/**
 * @brief 用于 std::visit()
 * @code
 *  std::variant<int, double> var;
 *  std::visit(var,
 *    trait::impl {
 *      [](int) {},
 *      [](double) {}
 *    }
 *  );
 * @endcode
 */
template <class... TOps>
struct impl : TOps... {
  using TOps::operator()...;
};
}  // namespace aimrte::trait
