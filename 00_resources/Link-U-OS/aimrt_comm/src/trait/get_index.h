// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <tuple>
#include <variant>

namespace aimrte::trait
{
namespace details
{
template <class>
struct Tag {
};
}  // namespace details

template <class T, class TContainer>
struct get_index;

template <class T, class TContainer>
struct get_index<T, TContainer&>
    : get_index<T, std::remove_cvref_t<TContainer>> {
};

template <class T, class... Ts>
struct get_index<T, std::variant<Ts...>>
    : std::integral_constant<std::size_t, std::variant<details::Tag<Ts>...>(details::Tag<T>()).index()> {
};
}  // namespace aimrte::trait
