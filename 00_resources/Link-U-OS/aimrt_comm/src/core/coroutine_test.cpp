// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./coroutine.h"
#include "src/interface/aimrt_module_cpp_interface/co/sync_wait.h"
#include <gtest/gtest.h>

namespace aimrte::test
{
class CoTaskTest : public ::testing::Test
{
 protected:
  void SetUp() override
  {
  }

  void TearDown() override
  {
  }
};

co::Task<void> MyVoidFunc()
{
  co_return;
}

co::Task<void> MyVoidFuncCaller()
{
  co_return co_await MyVoidFunc();
}

co::Task<int> MyValueFunc(const int a)
{
  co_return a;
}

co::Task<int> MyValueFuncCaller(const int a)
{
  co_return co_await MyValueFunc(a * 2);
}

TEST_F(CoTaskTest, ReturnVoid)
{
  MyVoidFunc().Sync();
  aimrt::co::SyncWait(MyVoidFunc());

  MyVoidFuncCaller().Sync();
  aimrt::co::SyncWait(MyVoidFuncCaller());
}

TEST_F(CoTaskTest, ReturnValue)
{
  GTEST_ASSERT_EQ(MyValueFunc(1).Sync(), 1);
  GTEST_ASSERT_EQ(aimrt::co::SyncWait(MyValueFunc(2)), 2);

  GTEST_ASSERT_EQ(MyValueFuncCaller(3).Sync(), 6);
  GTEST_ASSERT_EQ(aimrt::co::SyncWait(MyValueFuncCaller(4)), 8);
}
}  // namespace aimrte::test
