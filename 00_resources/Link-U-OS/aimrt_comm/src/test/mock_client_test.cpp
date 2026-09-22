// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./mock_client.h"

#include "src/test/test.h"

namespace aimrte::test
{
class MockClientTest : public TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetDefaultConfigContent();

    ctrl.LetInit();
  }

  ModuleTestController ctrl;
};

TEST_F(MockClientTest, MockClient)
{
  ctrl.LetStart();

  MockClient<std::string, int> mock_client;
  auto srv = mock_client.Init();

  EXPECT_CALL(mock_client, AnalyzeAndFeedback).WillRepeatedly([this](const aimrt::rpc::ContextRef &, const std::string &q, int &p, aimrt::rpc::Status &ret) {
    if (q == "abc")
      p = 1;
    else
      p = 2;

    ret = aimrt::rpc::Status{AIMRT_RPC_STATUS_UNKNOWN};
  });

  int response           = 0;
  aimrt::rpc::Status ret = ctrl.GetContext().cli().Call(srv, std::string("abc"), response).Sync();
  GTEST_ASSERT_EQ(ret.Code(), AIMRT_RPC_STATUS_UNKNOWN);
  GTEST_ASSERT_EQ(response, 1);

  ctrl.GetContext().cli().Call(srv, std::string("edf"), response).Sync();
  GTEST_ASSERT_EQ(response, 2);
}
}  // namespace aimrte::test
