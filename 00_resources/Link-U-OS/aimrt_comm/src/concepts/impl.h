// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <concepts>
#include <functional>
#include <utility>

namespace aimrte::concepts
{
namespace details
{
template <class F, class TSignature>
struct IsFunction;

template <class F, class TRet, class... TArgs>
concept SameReturnType =
  requires(F f, TArgs... args) {
    {
      f(std::forward<TArgs>(args)...)
      } -> std::same_as<TRet>;
  };

template <class F, class TRet, class... TArgs>
struct IsFunction<F, TRet(TArgs...)> {
  static constexpr bool value =
    std::is_constructible_v<std::function<TRet(TArgs...)>, F> and SameReturnType<F, TRet, TArgs...>;
};
}  // namespace details

/**
 * @brief 判断给定类型，是否符合要求的函数签名形式
 */
template <class F, class TSignature>
concept Function = details::IsFunction<F, TSignature>::value;

/**
 * @brief 判断给定的函数，是否是普通函数，且返回值为 void
 */
template <class F, class... TArgs>
concept ReturnVoidFunction =
  requires(F f, TArgs &&...args) {
    {
      f(std::forward<TArgs>(args)...)
      } -> std::same_as<void>;
  };
}  // namespace aimrte::concepts
