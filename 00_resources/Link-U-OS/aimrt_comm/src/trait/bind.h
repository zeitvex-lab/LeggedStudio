// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <functional>

namespace aimrte::trait::details
{
template <class... FArgs, size_t... N>
auto bind(FArgs&&... f_args, std::index_sequence<N...>)
{
  return std::bind(std::forward<FArgs>(f_args)..., std::_Placeholder<N + 1>()...);
}
}  // namespace aimrte::trait::details

namespace aimrte::trait
{
/**
 * @brief 绑定指定参数数量的函数，将自动产生一系列 std::placeholders 用于 std::bind
 * @tparam N 参数的数量
 * @param f_args 函数指针、函数所属对象指针（若为静态函数，则无需该项）
 *
 * @code
 * void f(int a, bool b) {}
 *
 * auto binder = aimrte::utils::bind_<2>(&f);
 * binder(3, true);
 * @endcode
 */
template <size_t N, class... FArgs>
auto bind_(FArgs&&... f_args)
{
  return details::bind<FArgs...>(std::forward<FArgs>(f_args)..., std::make_index_sequence<N>());
}

/**
 * @brief 用于绑定不定长参数的模板函数
 * @tparam TArgs 不定长模板参数（若没有模板，也可以不指定，将退化为一般的 std::bind ）
 * @param f_args 函数指针、函数所属对象指针（若为静态函数，则无需该项）
 *
 * @code
 * template<class ... Args>
 * class A
 * {
 * public:
 *     void f(Args ... args) {}
 *
 *     void g(Args ... args)
 *     {
 *         auto binder = aimrte::utils::bind<Args ...>(&A::f, this);
 *         binder(args ...);
 *     }
 * };
 * @endcode
 */
template <class... TArgs, class... FArgs>
auto bind(FArgs&&... f_args)
{
  return bind_<sizeof...(TArgs), FArgs...>(std::forward<FArgs>(f_args)...);
}
}  // namespace aimrte::trait
