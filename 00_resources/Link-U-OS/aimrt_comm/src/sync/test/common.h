// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/test/test.h"

#include "../macro.h"

namespace aimrte::test
{
class SyncTest : public ::testing::Test
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

template <class TMutex>
void SyncMutexBasicUsage(SyncTest& test)
{
  TMutex mutex;
  int x = 0, y = 0;

  for (int n = 0; n < 10000; ++n) {
    x = y = 0;

    aimrt::co::AsyncScope scope;
    test.exe
      .Post(
        scope,
        [&]() -> co::Task<void> {
          co_await mutex.Lock();
          if (y == 0)
            x = 1;
          mutex.Unlock();
        })
      .Post(
        scope,
        [&]() -> co::Task<void> {
          co_await mutex.Lock();
          if (x == 0)
            y = 1;
          mutex.Unlock();
        });

    aimrt::co::SyncWait(scope.complete());
    GTEST_ASSERT_EQ(x + y, 1);
  }
}

template <class TMutex>
void SyncMutexLotsOfParallel(SyncTest& test)
{
  TMutex mutex;

  int value_sum = 0;
  int test_sum  = 0;
  bool flag     = false;

  for (int i = 1; i <= 10000; ++i) {
    value_sum += i;
    test.exe.Post(
      [&, i]() -> co::Task<void> {
        std::unique_lock lock = co_await mutex.ScopedLock();

        if (not flag)
          flag = true;
        else
          std::terminate();

        flag = false;
        test_sum += i;
      });
  }

  // 让所有协程执行完毕
  test.ctrl.LetEnd();
  GTEST_ASSERT_EQ(value_sum, test_sum);
}

template <class TMutex>
void SyncMutexMacro(SyncTest& test)
{
  TMutex mutex;

  bool flag = false;

  for (int i = 0; i < 100; ++i) {
    test.exe.Post(
      [&]() -> co::Task<void> {
        AIMRTE(co_sync(mutex))
        {
          if (not flag)
            flag = true;
          else
            std::terminate();

          flag = false;
        }
      });
  }

  // 让所有协程执行完毕
  test.ctrl.LetEnd();
  GTEST_ASSERT_FALSE(flag);
}

template <template <class TMutex> class TConditionVariable, class TMutex>
void SyncCVBasicUsage(SyncTest& test)
{
  TMutex m;
  TConditionVariable<TMutex> cv;

  int x = 0, y = 0;

  test.exe
    .Post(
      [&]() -> co::Task<void> {
        std::unique_lock lock = co_await m.ScopedLock();

        std::cout << "[1] wait for signal ..." << std::endl;
        co_await cv.Wait(lock);

        if (y == 0)
          x = 1;
      })
    .Post(
      [&]() -> co::Task<void> {
        std::unique_lock lock = co_await m.ScopedLock();

        std::cout << "[2] wait for signal ..." << std::endl;
        co_await cv.Wait(lock);

        if (x == 0)
          y = 1;
      })
    .Post(
      [&]() -> co::Task<void> {
        co_await ctx::Sleep(std::chrono::milliseconds(300));
        std::cout << "Notify One" << std::endl;
        cv.NotifyOne();
      })
    .Post(
      [&]() -> co::Task<void> {
        co_await ctx::Sleep(std::chrono::milliseconds(700));
        std::cout << "Notify All" << std::endl;
        cv.NotifyAll();
      });

  test.ctrl.LetEnd();
  GTEST_ASSERT_EQ(x + y, 1);
}

template <template <class TMutex> class TConditionVariable, class TMutex>
void SyncCVPreCondition(SyncTest& test)
{
  TMutex m;
  TConditionVariable<TMutex> cv;

  bool flag = false;
  int value = 0;

  test.exe
    .Post(
      [&]() -> co::Task<void> {
        std::unique_lock lock = co_await m.ScopedLock();
        co_await cv.Wait(lock, [&]() {
          return flag;
        });
        value = 1;
      })
    .Post(
      [&]() -> co::Task<void> {
        co_await ctx::Sleep(std::chrono::milliseconds(100));
        cv.NotifyOne();

        // flag 没有翻转前，wait 不应该被唤醒
        co_await ctx::Sleep(std::chrono::milliseconds(100));
        if (value == 1)
          value = 2;

        flag = true;
        cv.NotifyOne();
      });

  // 让协程全部执行结束
  test.ctrl.LetEnd();
  GTEST_ASSERT_EQ(value, 1);
}

template <template <class TMutex> class TConditionVariable, class TMutex>
void SyncCVNotify(SyncTest& test)
{
  // 使用素数来控制我们的 wait 数量以及 notify 顺序
  const std::array primes = {2, 19, 7, 13, 3};
  int value_sum           = 0;
  int wait_count          = 0;

  for (const int prime : primes) {
    value_sum += prime * prime;
    wait_count += prime;
  }

  // 我们的 wait 协程根据当前使用的素数，进行累加
  TMutex m;
  TConditionVariable<TMutex> cv;
  std::size_t curr_idx     = 0;
  std::atomic_int test_sum = 0;

  for (int i = 0; i < wait_count; ++i) {
    test.exe.Post(
      [&]() -> co::Task<void> {
        std::unique_lock lock = co_await m.ScopedLock();
        co_await cv.Wait(lock);
        test_sum += primes[curr_idx];
      });
  }

  // notify 协程
  test.exe.Post(
    [&]() -> co::Task<void> {
      // 确保所有 wait 协程就绪
      co_await ctx::Sleep(std::chrono::milliseconds(100));

      for (curr_idx = 0; curr_idx < primes.size(); ++curr_idx) {
        if (curr_idx + 1 != primes.size()) {
          // 按当前的素数作为次数，并发 notify ，并让 wait 协程累加该素数
          for (int j = 0; j < primes[curr_idx]; ++j) {
            test.exe.Post([&]() {
              cv.NotifyOne();
            });
          }

          // 确保所有 notify one 执行完毕
          co_await ctx::Sleep(std::chrono::milliseconds(100));
        } else {
          // 最后一组 notify 直接 notify all
          cv.NotifyAll();
        }
      }
    });

  // 让协程全部执行结束
  std::this_thread::sleep_for(std::chrono::seconds(3));
  test.ctrl.LetEnd();
  GTEST_ASSERT_EQ(value_sum, test_sum);
}

template <template <class TMutex> class TConditionVariable, class TMutex>
void SyncCVLockAndNotify(SyncTest& test)
{
  TMutex m;
  TConditionVariable<TMutex> cv;

  bool flag = false;
  int value = 0;

  test.thread_safe_exe
    .Post(
      [&]() -> co::Task<void> {
        std::unique_lock lock = co_await m.ScopedLock();
        co_await cv.Wait(lock, [&]() {
          return flag;
        });
        value = 1;
      })
    .Post(
      [&]() -> co::Task<void> {
        co_await ctx::Sleep(std::chrono::milliseconds(100));

        std::unique_lock lock = co_await m.ScopedLock();
        flag                  = true;
        cv.NotifyOne();
      });

  // 让协程全部执行结束
  test.ctrl.LetEnd();
  GTEST_ASSERT_EQ(value, 1);
}
}  // namespace aimrte::test
