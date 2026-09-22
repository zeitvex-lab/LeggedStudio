// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

/**
 * @brief 在头文件中使用，创建一个 helper 类型，用于避免某些源文件因为
 * 没有被用户显式使用而被优化器优化。
 *
 * @code
 *   // my_used_module.h
 *   AIMRTE_NOT_OPTIMIZE_OUT_HELPER_DECLARE(my_helper);
 * @endcode
 */
#define AIMRTE_NOT_OPTIMIZE_OUT_HELPER_DECLARE(_name_)         \
  namespace details_no_optimize_out                            \
  {                                                            \
  struct NotOptimizeOutHelper##_name_ {                        \
    NotOptimizeOutHelper##_name_() noexcept;                   \
  };                                                           \
                                                               \
  [[maybe_unused]] static NotOptimizeOutHelper##_name_ _name_; \
  }

/**
 * @brief 在源文件中使用，与 NOX_NOT_OPTIMIZE_OUT_HELPER_DECLARE 宏
 * 相配合，可执行某些类型的显式使用过程，以避免这些类型被编译器优化。
 *
 * @code
 *   // my_used_module.cpp
 *   AIMRTE_NOT_OPTIMIZE_OUT_HELPER_IMPL(my_helper)
 *   {
 *       // 显式地使用一些不直接在 main 流程中使用的类，以免它们被编译器优化：
 *
 *       // 调用全局唯一函数的取实例接口，使该实例被初始化。
 *       SomeGlobalUniqueInstance<MyUnusedType2>::ref();
 *   }
 * @endcode
 */
#define AIMRTE_NOT_OPTIMIZE_OUT_HELPER_IMPL(_name_) \
  details_no_optimize_out::NotOptimizeOutHelper##_name_::NotOptimizeOutHelper##_name_() noexcept
