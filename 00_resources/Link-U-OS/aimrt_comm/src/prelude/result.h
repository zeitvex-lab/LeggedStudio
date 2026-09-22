// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/ctx/ctx.h"
#include "src/match/match.h"

namespace aimrte::prelude_details
{
template <class TValue, class TError>
AIMRTE_ENUM_TEMPLATE_CLASS(
  ResultImpl,
  (TValue, TError),
  (Ok, TValue),
  (Err, TError));

struct Void {
};

template <class T>
struct VoidableTrait {
  using Type = T;
};

template <>
struct VoidableTrait<void> {
  using Type = Void;
};

template <class T>
using Voidable = typename VoidableTrait<T>::Type;

template <class T>
struct ResultOk {
  Voidable<T> data;
};

template <class T>
struct ResultErr {
  Voidable<T> data;
};

template <class T>
concept OkClass = std::tuple_size_v<std::remove_cvref_t<T>> == 1 and std::remove_cvref_t<T>::FIELD_INDEX == 0;

template <class T>
concept ErrorClass = std::tuple_size_v<std::remove_cvref_t<T>> == 1 and std::remove_cvref_t<T>::FIELD_INDEX == 1;

template <class T>
concept VoidEnumFieldClass = std::is_same_v<Void, typename std::tuple_element<0, std::remove_cvref_t<T>>::type>;

template <class T, class TRaw>
concept RefClass = std::is_same_v<T, const TRaw&>;

template <class T>
concept LoggableClass = std::is_same_v<std::remove_cvref_t<T>, std::string>;

template <class T>
struct LoggableResultErr : ResultErr<T> {
  explicit LoggableResultErr(T&& data)
      : ResultErr<T>(std::forward<T>(data))
  {
  }

  ResultErr<T>& log(const std::source_location call_loc = std::source_location::current())
  {
    ctx::log(call_loc).Error("");
    return *this;
  }
};

template <>
struct LoggableResultErr<void> : ResultErr<void> {
  ResultErr& log(const std::source_location call_loc = std::source_location::current())
  {
    ctx::log(call_loc).Error("");
    return *this;
  }
};

template <LoggableClass T>
struct LoggableResultErr<T> : ResultErr<T> {
  explicit LoggableResultErr(T&& data)
      : ResultErr<T>(std::forward<T>(data))
  {
  }

  ResultErr<T>& log(const std::source_location call_loc = std::source_location::current())
  {
    ctx::log(call_loc).Error("{}", ResultErr<T>::data);
    return *this;
  }
};

class ResultOkImpl
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
      requires(OkClass<T>)
    auto operator()(T&& obj)
    {
      if constexpr (VoidEnumFieldClass<T>)
        return func_();
      else
        return func_(std::get<0>(std::forward<T>(obj)));
    }

    constexpr static std::size_t ARM_INDEX = 0;

   private:
    F func_;
  };

 public:
  template <class T>
  auto operator()(T&& value) const
  {
    if constexpr (std::is_lvalue_reference_v<T>)
      return ResultOk<const std::remove_cvref_t<T>&>(std::forward<T>(value));
    else
      return ResultOk<std::remove_cvref_t<T>>(std::forward<T>(value));
  }

  constexpr auto operator()() const
  {
    return ResultOk<void>();
  }

  template <class F>
  auto operator|(F&& func) const
  {
    return Arm(std::forward<F>(func));
  }
};

class ResultErrImpl
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
      requires(ErrorClass<T>)
    auto operator()(T&& obj)
    {
      if constexpr (VoidEnumFieldClass<T>)
        return func_();
      else
        return func_(std::get<0>(std::forward<T>(obj)));
    }

    constexpr static std::size_t ARM_INDEX = 1;

   private:
    F func_;
  };

 public:
  template <class T>
  auto operator()(T&& value) const
  {
    if constexpr (std::is_lvalue_reference_v<T>)
      return LoggableResultErr<const std::remove_cvref_t<T>&>(std::forward<T>(value));
    else
      return LoggableResultErr<std::remove_cvref_t<T>>(std::forward<T>(value));
  }

  constexpr auto operator()() const
  {
    return LoggableResultErr<void>();
  }

  template <class F>
  auto operator|(F&& func) const
  {
    return Arm(std::forward<F>(func));
  }
};
}  // namespace aimrte::prelude_details

namespace aimrte
{
/**
 * @brief 在 Result<TValue, TError> 中，代表正确值
 */
[[maybe_unused]] static inline prelude_details::ResultOkImpl Ok;

/**
 * @brief 在 Result<TValue, TError> 中，代表错误值
 */
[[maybe_unused]] static inline prelude_details::ResultErrImpl Err;

namespace prelude_details
{
/**
 * @brief 为 Result<TValue, TError> 实现 Unwarp, ConstUnwarp 函数。
 */
template <class TFinal, class TValue>
class UnwarpResultImpl
{
 public:
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
    if AIMRTE (let(static_cast<const TFinal&>(*this)), as(Ok), then(const TValue& res)) {
      return res;
    }

    panic(loc).wtf("unwarp Err Result");
  }
};

template <class TFinal>
class UnwarpResultImpl<TFinal, void>
{
};
}  // namespace prelude_details

/**
 * @brief 模仿 rust Result<T, E> 语法，实现 std::expected<T, E> 类似的功能，
 *        支持 match 与 ifLet 语法。
 * @tparam TValue 正确的值
 * @tparam TError 错误的值
 */
template <class TValue, class TError>
class Result final : public prelude_details::ResultImpl<prelude_details::Voidable<TValue>, prelude_details::Voidable<TError>>,
                     public prelude_details::UnwarpResultImpl<Result<TValue, TError>, TValue>
{
  using Super = prelude_details::ResultImpl<prelude_details::Voidable<TValue>, prelude_details::Voidable<TError>>;

 public:
  AIMRTE_DECLARE_DEFAULT_COPY_MOVE(Result);

  Result(prelude_details::ResultOk<TValue> value)
      : Super(Super::Ok(std::move(value.data)))
  {
  }

  template <prelude_details::RefClass<TValue> EValue>
  Result(prelude_details::ResultOk<EValue> value)
      : Super(Super::Ok(value.data))
  {
  }

  Result& operator=(prelude_details::ResultOk<TValue> value)
  {
    Super::operator=(Super::Ok(std::move(value.data)));
    return *this;
  }

  template <prelude_details::RefClass<TValue> EValue>
  Result& operator=(prelude_details::ResultOk<EValue> value)
  {
    Super::operator=(Super::Ok(value.data));
    return *this;
  }

  Result(prelude_details::ResultErr<TError> value)
      : Super(Super::Err(std::move(value.data)))
  {
  }

  template <prelude_details::RefClass<TError> EError>
  Result(prelude_details::ResultErr<EError> value)
      : Super(Super::Err(value.data))
  {
  }

  Result& operator=(prelude_details::ResultErr<TError> value)
  {
    Super::operator=(Super::Err(std::move(value.data)));
    return *this;
  }

  template <prelude_details::RefClass<TError> EError>
  Result& operator=(prelude_details::ResultErr<EError> value)
  {
    Super::operator=(Super::Err(value.data));
    return *this;
  }

  bool IsOk() const
  {
    return Super::is(Super::Ok);
  }

  bool IsErr() const
  {
    return Super::is(Super::Err);
  }

  // 一些兼容性接口
 public:
  bool is(const prelude_details::ResultOkImpl&) const
  {
    return IsOk();
  }

  bool is(const prelude_details::ResultErrImpl&) const
  {
    return IsErr();
  }

  static const typename decltype(Super::Ok)::ValueType& GetEnumValue(
    const Result& obj, const prelude_details::ResultOkImpl&)
  {
    return Super::GetEnumValue(obj, Super::Ok);
  }

  static typename decltype(Super::Ok)::ValueType& GetEnumValue(Result& obj, const prelude_details::ResultOkImpl&)
  {
    return Super::GetEnumValue(obj, Super::Ok);
  }

  static typename decltype(Super::Ok)::ValueType& GetEnumValue(Result&& obj, const prelude_details::ResultOkImpl&)
  {
    return Super::GetEnumValue(std::move(obj), Super::Ok);
  }

  static const typename decltype(Super::Err)::ValueType& GetEnumValue(
    const Result& obj, const prelude_details::ResultErrImpl&)
  {
    return Super::GetEnumValue(obj, Super::Err);
  }

  static typename decltype(Super::Err)::ValueType& GetEnumValue(Result& obj, const prelude_details::ResultErrImpl&)
  {
    return Super::GetEnumValue(obj, Super::Err);
  }

  static typename decltype(Super::Err)::ValueType& GetEnumValue(Result&& obj, const prelude_details::ResultErrImpl&)
  {
    return Super::GetEnumValue(std::move(obj), Super::Err);
  }
};
}  // namespace aimrte
