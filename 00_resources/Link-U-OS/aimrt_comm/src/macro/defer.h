// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <concepts>
#include <utility>

#include "./fancier.h"
#include "./unique.h"
#include "src/ref/ref.h"

/**
 * @brief 创建一个守护者，随着守护者被析构时，执行给定的过程。
 *
 * @code
 *  {
 *    AIMRTE(defer( foo() ));
 *  } // foo() 被调用
 * @endcode
 */
#define AIMRTE_DETAILS_defer(...) AIMRTE_DETAILS_defer_DO
#define AIMRTE_DETAILS_defer_DO(_defer_pack_)        \
  ::aimrte::Defer AIMRTE_COUNTER_UNIQUE(__defer__)(  \
    [&]() {                                          \
      AIMRTE_DETAILS_defer_DO_UNPACK_##_defer_pack_; \
    })
#define AIMRTE_DETAILS_defer_DO_UNPACK_defer(...) __VA_ARGS__

namespace aimrte::macro_details
{
template <class F>
concept DeferFunction = std::invocable<F> and std::same_as<void, std::invoke_result_t<F>>;
}

namespace aimrte
{
template <macro_details::DeferFunction F>
class Defer : public Ref<F>
{
 public:
  explicit Defer(F& func)
      : Ref<F>(func)
  {
  }

  explicit Defer(F&& func)
      : Ref<F>(std::move(func))
  {
  }

  ~Defer()
  {
    Ref<F>::ref()();
  }
};
}  // namespace aimrte
