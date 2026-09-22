// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <source_location>

/**
 * @brief 万能扩展宏
 */
#define AIMRTE(_head_, ...) AIMRTE_DETAILS_##_head_(_head_ __VA_OPT__(, ) __VA_ARGS__)

/**
 * @brief 声明一个 noexcept 的函数实现体，并返回要求的值。
 *        AIMRTE(noexcept(Some Return Values))
 * @code
 *   int AnotherFunc() noexcept {
 *     return 1;
 *   }
 *
 *   // Func() 的 noexcept 属性继承于 AnotherFunc()
 *   auto Func() AIMRTE(noexcept(AnotherFunc()))
 * @endcode
 */
#define AIMRTE_DETAILS_noexcept(...) AIMRTE_DETAILS_noexcept_DO
#define AIMRTE_DETAILS_noexcept_DO(_noexcept_pack_) AIMRTE_DETAILS_noexcept_DO_UNPACK_##_noexcept_pack_
#define AIMRTE_DETAILS_noexcept_DO_UNPACK_noexcept(...) \
  noexcept(noexcept(__VA_ARGS__))                       \
  {                                                     \
    return __VA_ARGS__;                                 \
  }

/**
 * @brief 创建一个带有默认值的参数，用于获取调用该函数的代码位置
 *        AIMRTE(src(The std::source_location parameter variable))
 * @code
 *   void Func(int a, int b, AIMRTE(src(loc)) {
 *     std::cout << loc.file_name() << std::endl;
 *   }
 * @endcode
 */
#define AIMRTE_DETAILS_src(...) AIMRTE_DETAILS_src_DO
#define AIMRTE_DETAILS_src_DO(_src_pack_) \
  const std::source_location AIMRTE_DETAILS_src_DO_UNPACK_##_src_pack_ = std::source_location::current()
#define AIMRTE_DETAILS_src_DO_UNPACK_src(_param_var_) _param_var_
