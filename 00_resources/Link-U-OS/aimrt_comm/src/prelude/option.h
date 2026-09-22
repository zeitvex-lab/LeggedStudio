// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/match/match.h"
#include "src/panic/panic.h"

namespace aimrte::prelude_details
{
template <class TValue>
AIMRTE_ENUM_TEMPLATE_CLASS(
  OptionImpl,
  (TValue),
  (Some, TValue),
  (None));

class OptionNoneImpl
{
  template <class F>
  class Arm
  {
   public:
    explicit Arm(F&& func)
        : func_(std::forward<F>(func))
    {
    }

    template <class T>
      requires(std::tuple_size_v<std::remove_cvref_t<T>> == 0)
    auto operator()(T)
    {
      return func_();
    }

    constexpr static std::size_t ARM_INDEX = 1;

   private:
    F func_;
  };

 public:
  template <class F>
  auto operator|(F&& func)
  {
    return Arm(std::forward<F>(func));
  }
};

class OptionSomeImpl
{
  template <class F>
  class Arm
  {
   public:
    explicit Arm(F&& func)
        : func_(std::forward<F>(func))
    {
    }

    template <class T>
      requires(std::tuple_size_v<std::remove_cvref_t<T>> == 1)
    auto operator()(T&& obj)
    {
      return func_(std::get<0>(std::forward<T>(obj)));
    }

    constexpr static std::size_t ARM_INDEX = 0;

   private:
    F func_;
  };

 public:
  template <class T>
  auto operator()(T&& value) -> OptionImpl<T>
  {
    return OptionImpl<T>::Some(std::forward<T>(value));
  }

  template <class F>
  auto operator|(F&& func)
  {
    return Arm(std::forward<F>(func));
  }
};
}  // namespace aimrte::prelude_details

namespace aimrte
{
/**
 * @brief 在 Option<T> 中，代表没有值
 */
static inline prelude_details::OptionNoneImpl None;

/**
 * @brief 在 Option<T> 中，代表某个值。
 */
static inline prelude_details::OptionSomeImpl Some;

/**
 * @brief 模仿 rust Option<T> 语法，实现 std::optional<T> 类似的功能，
 *        支持 match 与 ifLet 语法。
 * @tparam TValue 可能持有的类型
 */
template <class TValue>
class Option final : public prelude_details::OptionImpl<TValue>
{
  using Super = prelude_details::OptionImpl<TValue>;

 public:
  AIMRTE_DECLARE_DEFAULT_COPY_MOVE(Option);

  Option(const Super& other)
      : Super(other)
  {
  }

  Option(Super&& other) noexcept
      : Super(std::move(other))
  {
  }

  Option(decltype(None))
      : Super(Super::None())
  {
  }

  Option& operator=(const Super& other)
  {
    Super::operator=(other);
    return *this;
  }

  Option& operator=(Super&& other) noexcept
  {
    Super::operator=(std::move(other));
    return *this;
  }

  Option& operator=(decltype(None))
  {
    Super::operator=(Super::None());
    return *this;
  }

  bool IsNone() const
  {
    return Super::is(Super::None);
  }

  bool IsSome() const
  {
    return Super::is(Super::Some);
  }

  TValue& Unwarp(AIMRTE(src(loc)))
  {
    return trait::remove_const(ConstUnwarp(loc));
  }

  const TValue& ConstUnwarp(AIMRTE(src(loc)))
  {
    return trait::add_const(this)->Unwarp(loc);
  }

  const TValue& Unwarp(AIMRTE(src(loc))) const
  {
    if AIMRTE (let(*this), as(Some), then(const TValue& res)) {
      return res;
    }

    panic(loc).wtf("unwarp None Option");
  }

  // 一些兼容性接口
 public:
  bool is(const prelude_details::OptionSomeImpl&) const
  {
    return IsSome();
  }

  bool is(const prelude_details::OptionNoneImpl&) const
  {
    return IsNone();
  }

  static const typename decltype(Super::Some)::ValueType& GetEnumValue(
    const Option& obj, const prelude_details::OptionSomeImpl&)
  {
    return Super::GetEnumValue(obj, Super::Some);
  }

  static typename decltype(Super::Some)::ValueType& GetEnumValue(Option& obj, const prelude_details::OptionSomeImpl&)
  {
    return Super::GetEnumValue(obj, Super::Some);
  }

  static typename decltype(Super::Some)::ValueType& GetEnumValue(Option&& obj, const prelude_details::OptionSomeImpl&)
  {
    return Super::GetEnumValue(std::move(obj), Super::Some);
  }
};
}  // namespace aimrte
