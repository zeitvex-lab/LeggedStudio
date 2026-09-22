// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./mock_publisher.h"

#include "src/test/test.h"

namespace aimrte::test
{
class MockPublisherTest : public TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetDefaultConfigContent();

    ctrl.LetInit();
  }

  ModuleTestController ctrl;
};

TEST_F(MockPublisherTest, MockPublisher)
{
  ctrl.LetStart();

  MockPublisher<std::string> mock_publisher;
  res::Channel<std::string> ch = mock_publisher.Init();

  EXPECT_CALL(mock_publisher, Analyze).WillRepeatedly([this](const std::string& msg) {
    if (msg == "abc")
      std::cout << "123" << std::endl;
    else
      std::cout << "456" << std::endl;
  });

  ctrl.GetContext().pub().Publish(ch, std::string("abc"));
  GTEST_ASSERT_TRUE(ExpectOutputContent("123"));

  ctrl.GetContext().pub().Publish(ch, std::string("edf"));
  GTEST_ASSERT_TRUE(ExpectOutputContent("456"));
}
}  // namespace aimrte::test
