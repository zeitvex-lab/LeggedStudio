// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./any.h"
#include "src/test/test.h"
#include <string>

namespace aimrte::test
{
class SyncAnyTest : public ::testing::Test
{
 protected:
  void SetUp() override
  {
    ctrl.SetDefaultConfigContent();
    ctrl.LetInit();
    exe             = ctx::init::Executor(ctrl.GetDefaultConfig().exe);
    thread_safe_exe = ctx::init::Executor(ctrl.GetDefaultConfig().thread_safe_exe);

    ctrl.LetStart();
  }

 public:
  ModuleTestController ctrl;
  ctx::Executor exe;
  ctx::Executor thread_safe_exe;
};

namespace
{
co::Task<void> CoTask()
{
  co_return;
}

template <class T>
co::Task<T> CoTask(T n)
{
  std::cout << "CoTask " << n << std::endl;
  co_return n;
}
}  // namespace

TEST_F(SyncAnyTest, BasicUsage)
{
  bool flag = false;

  thread_safe_exe.Inline(
    [&]() -> co::Task<void> {
      IndexedVariant<int, int, int, double, std::string, Void> result =
        co_await sync::any{
          CoTask<int>(1),
          CoTask<int>(2),
          CoTask<int>(3),
          CoTask<double>(4.0),
          CoTask<std::string>({}),
          CoTask(),
        };

      if (result.Index() == 0 and result.Get<0>() == 1)
        flag = true;
    });

  GTEST_EXPECT_TRUE(flag);
}

namespace
{
co::Task<int> CoTask(int n, std::atomic_int& sum, bool sleep)
{
  if (sleep)
    co_await ctx::Sleep(std::chrono::milliseconds(1000));

  sum += n;
  co_return n;
}
}  // namespace

TEST_F(SyncAnyTest, DISABLED_UseScope)
{
  bool flag = false;

  thread_safe_exe.Inline(
    [&]() -> co::Task<void> {
      std::atomic_int sum{0};
      co::AsyncScope scope;

      auto result = co_await sync::any{
        CoTask(7, sum, true),
        CoTask(5, sum, false),
        CoTask(17, sum, true),
      }
                      .In(scope);

      // 在单线程的情况下，会卡死本线程
      if (result.Index() == 1 and result.Get<1>() == 5 and sum.load() == 5) {
        scope.Complete();

        if (sum.load() == 29)
          flag = true;
      }
    });

  GTEST_EXPECT_TRUE(flag);
}

TEST_F(SyncAnyTest, UseFinalHandler)
{
  std::atomic_int sum{0};
  co::AsyncScope scope;

  exe.Inline(
    [&]() -> co::Task<void> {
      co_await sync::any{
        CoTask<int>(2) | [&](const int value) {
          sum += value;
        },
        CoTask<int>(2) | [&](const int value) {
          sum += value;
        },
        CoTask<int>(2) | [&](const int value) {
          sum += value;
        },
      }
        .In(scope);

      scope.Complete();
    });

  GTEST_ASSERT_EQ(sum.load(), 2);
}

namespace
{
co::Task<int> CoTaskWithSleep(int n, const int ms)
{
  co_await ctx::Sleep(std::chrono::milliseconds(ms));
  co_return n;
}
}  // namespace

TEST_F(SyncAnyTest, UseExecutor)
{
  std::size_t index = 0;
  int value         = 0;

  exe.Inline(
    [&]() -> co::Task<void> {
      auto res1 = co_await sync::any{
        CoTaskWithSleep(1, 100),
        CoTaskWithSleep(2, 50),
        CoTaskWithSleep(3, 120),
      }
                    .Via(thread_safe_exe);

      res1.Visit(
        [&](const std::size_t idx, const int val) {
          index = idx;
          value = val;
        });
    });

  GTEST_ASSERT_EQ(index, 1);
  GTEST_ASSERT_EQ(value, 2);
}

}  // namespace aimrte::test
