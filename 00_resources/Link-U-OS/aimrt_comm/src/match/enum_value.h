// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <tuple>

namespace aimrte::match_details
{
template <class, std::size_t C_FIELD_INDEX, class... Ts>
class EnumValue : public std::tuple<Ts...>
{
 public:
  constexpr static std::size_t FIELD_INDEX = C_FIELD_INDEX;
  using std::tuple<Ts...>::tuple;
};
}  // namespace aimrte::match_details

namespace std
{
template <class Tag, std::size_t FIELD_INDEX, class... Ts>
struct tuple_size<aimrte::match_details::EnumValue<Tag, FIELD_INDEX, Ts...>>
    : integral_constant<size_t, sizeof...(Ts)> {
};

template <class Tag, size_t I, std::size_t FIELD_INDEX, class... Ts>
struct tuple_element<I, aimrte::match_details::EnumValue<Tag, FIELD_INDEX, Ts...>> {
  using type = tuple_element_t<I, std::tuple<Ts...>>;
};
}  // namespace std
