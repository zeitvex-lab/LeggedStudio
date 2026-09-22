// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./mock_subscriber.h"

#include "src/test/test.h"

namespace aimrte::test
{
class MockSubscriberTest : public TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetDefaultConfigContent();

    ctrl.LetInit();
  }

  ModuleTestController ctrl;
};

TEST_F(MockSubscriberTest, MockSubscriber)
{
  ctrl.LetStart();

  MockSubscriber<std::string> mock_subscriber;

  EXPECT_CALL(mock_subscriber, OnNullSubscriberError).WillRepeatedly([this]() {
    GTEST_FAIL();
  });
  EXPECT_CALL(mock_subscriber, AnalyzeAsync).WillRepeatedly([this]() {
    GTEST_FAIL();
  });

  res::Channel<std::string> ch = mock_subscriber.Init();

  // test nullptr
  EXPECT_CALL(mock_subscriber, OnNullSubscriberError).WillOnce(nullptr);
  mock_subscriber.Feed("abc");

  // test subcriber
  bool sub_flag = false;

  ctrl.GetContext().sub().SubscribeInline(
    ch,
    [&](const std::string &msg) {
      sub_flag = msg == "abc";
    });

  mock_subscriber.Feed("abc");
  GTEST_ASSERT_TRUE(sub_flag);

  // test executor
  int count = 0;
  EXPECT_CALL(mock_subscriber, AnalyzeAsync).WillRepeatedly([this, &count]() {
    ++count;
  });
  res::Executor exe = ctrl.GetContext().InitExecutor("work_thread_pool");
  ctrl.GetContext().exe(exe).Subscribe(
    ch,
    [](const std::string &) {
    });
  for (int i = 0; i < 100; ++i)
    mock_subscriber.FeedAsync("");

  // wait for all task ended
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  EXPECT_EQ(count, 100);
}
}  // namespace aimrte::test
