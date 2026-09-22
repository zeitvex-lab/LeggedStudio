// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./mock_server.h"

#include "src/test/test.h"

namespace aimrte::test
{
class MockServerTest : public TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetDefaultConfigContent();

    ctrl.LetInit();

    sum = 0;
  }

  ModuleTestController ctrl;
  std::atomic_int sum = 0;
};

TEST_F(MockServerTest, MockServer)
{
  ctrl.LetStart();

  MockServer<std::string, int> mock_server;
  auto srv = mock_server.Init();

  EXPECT_CALL(mock_server, OnNullServerError).WillRepeatedly([this]() {
    std::cout << "null server" << std::endl;
  });
  EXPECT_CALL(mock_server, Analyze).WillRepeatedly([this](const aimrt::rpc::ContextRef& rpc_ctx, const std::string& q, const int& p, const aimrt::rpc::Status& ret) {
    GTEST_FAIL();
  });
  EXPECT_CALL(mock_server, AnalyzeAsync).WillRepeatedly([this](const aimrt::rpc::ContextRef& rpc_ctx, const std::string& q, const int& p, const aimrt::rpc::Status& ret) {
    GTEST_FAIL();
  });

  // test null server
  mock_server.Feed("abc");
  GTEST_ASSERT_TRUE(ExpectOutputContent("null server"));

  // test server
  EXPECT_CALL(mock_server, Analyze).Times(2).WillRepeatedly([this](const aimrt::rpc::ContextRef& rpc_ctx, const std::string& q, const int& p, const aimrt::rpc::Status& ret) {
    if (q == "abc")
      GTEST_ASSERT_EQ(p, 1);
    else
      GTEST_ASSERT_EQ(p, 2);

    GTEST_ASSERT_EQ(ret.Code(), AIMRT_RPC_STATUS_UNKNOWN);
  });

  ctrl.GetContext().srv().ServeInline(
    srv,
    [](const std::string& q, int& p) {
      if (q == "abc")
        p = 1;
      else
        p = 2;
      return aimrt::rpc::Status{AIMRT_RPC_STATUS_UNKNOWN};
    });

  mock_server.Feed("abc");
  mock_server.Feed("edf");

  // test async server
  EXPECT_CALL(mock_server, AnalyzeAsync).WillRepeatedly([this](const aimrt::rpc::ContextRef& rpc_ctx, const std::string& q, const int& p, const aimrt::rpc::Status& ret) {
    this->sum += p;
  });
  res::Executor exe = ctrl.GetContext().InitExecutor("work_thread_pool");
  ctrl.GetContext().exe(exe).Serve(
    srv,
    [](const std::string& request, int& response) -> aimrt::rpc::Status {
      response = std::stoi(request);
      return {};
    });

  int sum = 0;
  for (int i = 0; i < 100; ++i) {
    sum += i;
    mock_server.FeedAsync(std::to_string(i));
  }

  // wait for all task ended
  std::this_thread::sleep_for(std::chrono::milliseconds(1000));
  GTEST_ASSERT_EQ(this->sum, sum);
}
}  // namespace aimrte::test
