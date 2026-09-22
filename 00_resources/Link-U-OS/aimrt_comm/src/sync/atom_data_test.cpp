// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/sync/sync.h"
#include "src/test/test.h"

namespace aimrte::test
{
class AtomDataTest : public ::testing::Test
{
 protected:
  void SetUp() override
  {
    ctrl.SetDefaultConfigContent();
    ctrl.LetInit();
    exe = ctrl.GetContext().InitExecutor(ctrl.GetDefaultConfig().exe);

    ctrl.LetStart();
  }

  ModuleTestController ctrl;
  res::Executor exe;
};

TEST_F(AtomDataTest, SetAndGet)
{
  sync::AtomData<int> data_;
  int get_data   = 0;
  int loop_count = 10000;
  for (int n = 0; n <= loop_count; ++n) {
    aimrt::co::AsyncScope scope;
    ctrl
      .GetContext()
      .exe(exe)
      .Post(
        scope,
        [&data_, n]() -> co::Task<void> {
          data_.Set(n);
          co_return;
        });
    aimrt::co::SyncWait(scope.complete());

    aimrt::co::AsyncScope scope2;
    ctrl
      .GetContext()
      .exe(exe)
      .Post(
        scope2,
        [&]() -> co::Task<void> {
          get_data = data_.Get();
          co_return;
        });
    aimrt::co::SyncWait(scope2.complete());
  }
  EXPECT_EQ(get_data, loop_count);
}

TEST_F(AtomDataTest, SetAndGetClear)
{
  sync::AtomData<int> data_;
  int get_data   = 0;
  int loop_count = 10000;
  for (int n = 0; n <= loop_count; ++n) {
    aimrt::co::AsyncScope scope;
    ctrl
      .GetContext()
      .exe(exe)
      .Post(
        scope,
        [&data_, n]() -> co::Task<void> {
          data_.Set(n);
          co_return;
        });
    aimrt::co::SyncWait(scope.complete());

    aimrt::co::AsyncScope scope2;
    ctrl
      .GetContext()
      .exe(exe)
      .Post(
        scope2,
        [&]() -> co::Task<void> {
          EXPECT_TRUE(data_.GetAndClear(get_data));
          co_return;
        });
    aimrt::co::SyncWait(scope2.complete());
  }
  EXPECT_EQ(get_data, loop_count);
}

TEST_F(AtomDataTest, SetAndTimeoutHas)
{
  sync::AtomData<int> data_(10);
  int set_data = 100;

  aimrt::co::AsyncScope scope;
  ctrl
    .GetContext()
    .exe(exe)
    .Post(
      scope,
      [&]() -> co::Task<void> {
        data_.Set(set_data);
        co_return;
      });
  aimrt::co::SyncWait(scope.complete());

  aimrte::ctx::Sleep(std::chrono::milliseconds(20)).Sync();

  EXPECT_FALSE(data_.Has());
  data_.Set(set_data + 1);
  EXPECT_TRUE(data_.Has());
}

TEST_F(AtomDataTest, SetWithGetAndClear)
{
  sync::AtomData<int> data_(10);
  int set_data = 100;

  aimrt::co::AsyncScope scope;
  ctrl
    .GetContext()
    .exe(exe)
    .Post(
      scope,
      [&]() -> co::Task<void> {
        data_.Set(set_data);
        co_return;
      });
  aimrt::co::SyncWait(scope.complete());

  aimrte::ctx::Sleep(std::chrono::milliseconds(20)).Sync();
  int get_data;
  EXPECT_FALSE(data_.Has());
  EXPECT_FALSE(data_.GetAndClear(get_data));

  data_.Set(set_data + 1);
  EXPECT_TRUE(data_.Has());

  EXPECT_TRUE(data_.GetAndClear(get_data));
  EXPECT_EQ(get_data, set_data + 1);
}

}  // namespace aimrte::test
