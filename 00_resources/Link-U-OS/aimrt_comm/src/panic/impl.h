// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <fmt/format.h>
#include <iostream>
#include <source_location>
#include <stdexcept>
#include <string_view>

namespace aimrte::panic_details
{
void SetPanicByThrow(bool enable);

class PanicExeception final : public std::runtime_error
{
 public:
  explicit PanicExeception(std::string msg)
      : std::runtime_error(std::move(msg))
  {
  }
};
}  // namespace aimrte::panic_details

namespace aimrte::panic_details
{
class Panic
{
 public:
  explicit Panic(std::source_location call_loc);

 public:
  /**
   * \brief Print an error message before aborting the program.
   */
  template <class... TArgs>
  [[noreturn]] void operator()(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args) const
  {
    PrintAndAbort("panic", ::fmt::format(fmt, std::forward<TArgs>(args)...));
  }

  /**
   * \brief Print an error message about some implementation missing before aborting the program.
   */
  template <class... TArgs>
  [[noreturn]] void todo(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args) const
  {
    PrintAndAbort("panic.todo", ::fmt::format(fmt, std::forward<TArgs>(args)...));
  }

  /**
   * \brief Print an error message about some impossible things happening before aborting the program.
   */
  template <class... TArgs>
  [[noreturn]] void wtf(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args) const
  {
    PrintAndAbort("panic().wtf", ::fmt::format(fmt, std::forward<TArgs>(args)...));
  }

 private:
  [[noreturn]] void PrintAndAbort(const std::string_view& tag, const std::string& msg) const;

 private:
  const std::source_location call_loc_;
};
}  // namespace aimrte::panic_details

namespace aimrte
{
/**
 * @brief use this to break the control flow
 */
inline auto panic(const std::source_location call_loc = std::source_location::current())
{
  return panic_details::Panic(call_loc);
}
}  // namespace aimrte

/**
 * @brief 声明括号中的过程会导致 panic，仅在单元测试中使用。
 */
#define AIMRTE_TEST_SHOULD_PANIC(...)                              \
  do {                                                             \
    ::aimrte::panic_details::SetPanicByThrow(true);                \
    try {                                                          \
      __VA_ARGS__;                                                 \
      GTEST_FAIL();                                                \
    } catch (const ::aimrte::panic_details::PanicExeception& ec) { \
      std::cout << ec.what() << std::endl;                         \
      ::aimrte::panic_details::SetPanicByThrow(false);             \
    }                                                              \
  } while (0)

/**
 * @brief 声明某个编译分支非法
 */
#if __GNUC__ == 11
  #define AIMRTE_STATIC_PANIC(...) ::aimrte::panic().wtf(#__VA_ARGS__)
#else
  #define AIMRTE_STATIC_PANIC(...) static_assert(false, #__VA_ARGS__)
#endif
