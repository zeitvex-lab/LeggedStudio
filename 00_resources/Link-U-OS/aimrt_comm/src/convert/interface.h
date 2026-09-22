// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/panic/panic.h"
#include <utility>

namespace aimrte::impl
{
/**
 * @brief 类型转换统一接口，需要由特定类型特化实现
 * @tparam TFrom 原始类型
 * @tparam TTo   目标类型
 * @param src 原始类型的对象
 * @param dst 目标类型的对象
 */
template <class TFrom, class TTo>
void Convert(const TFrom& src, TTo& dst)
{
  AIMRTE_STATIC_PANIC(
    R"(
You forget to implement Convert() function for your types.

// such as
namespace aimrte::impl
{
  template <>
  void Convert(const YourOriginalType & src, YourTargetType & dst) {
    // ... some convertion
  }
}
)");
}

template <class TFrom, class TTo>
void ConvertMoved(TFrom&& src, TTo& dst)
{
  Convert<TFrom, TTo>(src, dst);
}
}  // namespace aimrte::impl

namespace aimrte::convert::details
{
/**
 * @brief 用于实现 convert::From<T>(src).To<E>() 函数。
 */
template <class TFrom>
class FromThenToOperator
{
 public:
  explicit FromThenToOperator(const TFrom& src)
      : src_(src)
  {
  }

  template <class TTo>
  TTo To() const
  {
    TTo dst;
    impl::Convert(src_, dst);
    return dst;
  }

 private:
  const TFrom& src_;
};

template <class TFrom>
class FromThenToOperator<TFrom&&>
{
 public:
  explicit FromThenToOperator(TFrom&& src)
      : src_(std::move(src))
  {
  }

  template <class TTo>
  TTo To() const
  {
    TTo dst;
    impl::Convert(src_, dst);
    return dst;
  }

 private:
  TFrom src_;
};
}  // namespace aimrte::convert::details

namespace aimrte::convert
{
/**
 * @brief 将指定类型的左值对象，转换为另外一种类型
 * 要求相关类型的 impl::Convert() 存在实现。
 * @code
 *  int src = 1;
 *  std::string dst = convert::From<int>(src).To<std::string>();
 * @endcode
 */
template <class TFrom>
details::FromThenToOperator<TFrom> From(const TFrom& src)
{
  return details::FromThenToOperator<TFrom>(src);
}

/**
 * @brief 将指定类型的右值对象，转换为另外一种类型。
 * 要求相关类型的 impl::Convert() 存在实现。
 * @code
 *  int dst = convert::From<std::string>("123").To<int>();
 * @endcode
 */
template <class TFrom>
details::FromThenToOperator<TFrom&&> From(TFrom&& src)
{
  return details::FromThenToOperator<TFrom&&>(std::forward<TFrom>(src));
}

/**
 * @brief 将指定类型的对象，转换为另外一种类型
 * @tparam TTo 目标类型
 * @tparam TFrom 原始类型
 * @param src 原来的对象
 * @return 转换后的对象
 */
template <class TTo, class TFrom>
TTo To(const TFrom& src)
{
  TTo dst;
  impl::Convert(src, dst);
  return dst;
}

/**
 * @brief 持有一个中间类型，可用于被转换、或者转换到它
 * @tparam TAnother 中间类型
 */
template <class TAnother>
struct By {
  using AnotherType = TAnother;

  template <class TOriginal>
  static constexpr auto FromOriginal()
  {
    return impl::Convert<TOriginal, TAnother>;
  }

  template <class TOriginal>
  static constexpr auto ToOriginal()
  {
    return impl::Convert<TAnother, TOriginal>;
  }
};

/**
 * @brief 定义一个类型的转换类型，需要用户使用特化去定义它的转换类型
 * @tparam TOriginal 原始类型
 * @code
 *   namespace aimrte::convert {
 *     template <>
 *     struct For<int> : By<double> {};
 *   }
 *
 *   template <class T>
 *   void foo() {
 *     // 一般会在框架中被使用：
 *     using Type = aimrte::convert::For<T>::AnotherType;
 *   }
 * @endcode
 */
template <class TOriginal>
struct For {
#if __GNUC__ > 11
  static_assert(false, R"("Unsupported type, you should define a converted type for it:
// such as:
namespace aimrte::convert
{
  template <>
  struct For<YourType> : By<YourAnotherType> {};
}
")");
#endif
};
}  // namespace aimrte::convert
