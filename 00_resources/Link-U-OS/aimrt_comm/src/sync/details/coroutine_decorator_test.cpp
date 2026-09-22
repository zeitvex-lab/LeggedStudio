// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./coroutine_decorator.h"
#include "src/test/test.h"
#include <unifex/when_all.hpp>

namespace aimrte::test
{
class CoroutineDecoratorTest : public ::testing::Test
{
 protected:
  void SetUp() override
  {
    ctrl.SetDefaultConfigContent();
    ctrl.LetInit();
    exe = ctx::init::Executor(ctrl.GetDefaultConfig().exe);

    ctrl.LetStart();
  }

 public:
  ModuleTestController ctrl;
  ctx::Executor exe;
};

namespace
{
template <class T>
using crt = typename co::details::ReturnValueTypeTrait<T>::Type;
}

TEST_F(CoroutineDecoratorTest, BasicUsage)
{
  auto co_task = []() -> co::Task<int> {
    co_return 1;
  };
  auto co_task_on_exe = co_task() | exe;
  auto co_task_then   = co_task() | [](int) -> double {
    return 2.0;
  };
  auto co_task_on_exe_then = co_task() | exe | [](int) -> std::size_t {
    return 3ull;
  };
  auto co_task_then_on_exe = co_task() | [](int) -> float {
    return 4.0f;
  } | exe;

  static_assert(std::is_same_v<crt<decltype(co_task)>, int>);
  static_assert(std::is_same_v<crt<decltype(co_task())>, int>);
  static_assert(std::is_same_v<crt<decltype(co_task_on_exe)>, int>);
  static_assert(std::is_same_v<crt<decltype(co_task_then)>, double>);
  static_assert(std::is_same_v<crt<decltype(co_task_on_exe_then)>, std::size_t>);
  static_assert(std::is_same_v<crt<decltype(co_task_then_on_exe)>, float>);

  auto co = co_task();

  unifex::sync_wait(
    unifex::when_all(
      co::details::IntoSender(std::move(co)),
      co::details::IntoSender(std::move(co_task)),
      IntoSender(std::move(co_task_on_exe)),
      IntoSender(std::move(co_task_then)),
      IntoSender(std::move(co_task_on_exe_then)),
      IntoSender(std::move(co_task_then_on_exe))));
}
}  // namespace aimrte::test
