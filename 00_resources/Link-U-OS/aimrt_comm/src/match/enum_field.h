// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "./enum_class.h"
#include "./enum_value.h"

namespace aimrte::match_details
{
template <class TEnumClass, class Tag, std::size_t FIELD_INDEX, class... Ts>
class EnumField
{
 public:
  using ValueType = EnumValue<Tag, FIELD_INDEX, Ts...>;

 private:
  template <class F, std::size_t... I>
  class Arm
  {
   public:
    Arm(F &&func, std::index_sequence<I...>)
        : func_(std::forward<F>(func))
    {
    }

    using ArmType = ValueType;

   public:
    auto operator()(const ValueType &value) const
    {
      return func_(std::get<I>(value)...);
    }

    auto operator()(ValueType &value) const
    {
      return func_(std::get<I>(value)...);
    }

    auto operator()(ValueType &&value) const
    {
      return func_(std::get<I>(std::move(value))...);
    }

   private:
    F func_;
  };

 public:
  template <class... Es>
  TEnumClass operator()(Es &&...args) const
  {
    return TEnumClass(ValueType(std::forward<Es>(args)...), BuildByEnumValue());
  }

  template <class F>
  auto operator|(F &&func) const
  {
    return Arm(std::forward<F>(func), std::make_index_sequence<sizeof...(Ts)>());
  }
};
}  // namespace aimrte::match_details
