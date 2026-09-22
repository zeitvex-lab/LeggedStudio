// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/test/test.h"

namespace aimrte::test
{
class MockTest : public TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetConfigContent(R"(
aimrt:
  configurator:
    temp_cfg_path: ./cfg/tmp # 生成的临时模块配置文件存放路径
  log: # log配置
    core_lvl: INFO # 内核日志等级，可选项：Trace/Debug/Info/Warn/Error/Fatal/Off，不区分大小写
    default_module_lvl: Trace # 模块默认日志等级
    backends: # 日志backends
      - type: console # 控制台日志
        options:
          color: true # 是否彩色打印
  executor: # 执行器配置
    executors: # 当前先支持thread型，未来可根据加载的网络模块提供更多类型
      - name: work_thread_pool # 线程池
        type: asio_thread
        options:
          thread_num: 5 # 线程数，不指定则默认单线程
)");

    ctrl.LetInit();
  }

  ModuleTestController ctrl;
};

TEST_F(MockTest, Publisher)
{
  class MockPublisher : public core::IMockPublisher<std::string>
  {
   public:
    int value = 0;

   protected:
    void Analyze(const std::string &msg) override
    {
      if (msg == "abc")
        value = 1;
      else if (msg == "edf")
        value = 2;
      else
        value = 0;
    }
  };

  MockPublisher mocker;
  res::Channel<std::string> ch = ctrl.GetContext().pub().InitMock("/mock/publisher", mocker);

  ctrl.GetContext().pub().Publish(ch, std::string("abc"));
  GTEST_ASSERT_TRUE(mocker.value == 1);

  ctrl.GetContext().pub().Publish(ch, std::string("edf"));
  GTEST_ASSERT_TRUE(mocker.value == 2);
}

TEST_F(MockTest, Subscriber)
{
  class MockSubscriber : public core::IMockSubscriber<std::string>
  {
   protected:
    void OnNullSubscriberError() override
    {
      GTEST_FAIL();
    }

    void AnalyzeAsync() override
    {
      GTEST_FAIL();
    }
  };

  MockSubscriber mocker;
  res::Channel<std::string> ch = ctrl.GetContext().sub().InitMock("/mock/subscriber", mocker);

  std::string str;

  ctrl.GetContext().sub().SubscribeInline(
    ch,
    [&](const std::string &msg) {
      str = msg;
    });

  mocker.Feed("abc");
  GTEST_ASSERT_EQ(str, "abc");
}

TEST_F(MockTest, NullSubscriber)
{
  class MockSubscriber : public core::IMockSubscriber<std::string>
  {
   public:
    bool flag = false;

   protected:
    void OnNullSubscriberError() override
    {
      flag = true;
    }

    void AnalyzeAsync() override
    {
      GTEST_FAIL();
    }
  };

  MockSubscriber mocker;
  res::Channel<std::string> ch = ctrl.GetContext().sub().InitMock("/mock/subscriber", mocker);

  mocker.Feed("abc");
  GTEST_ASSERT_TRUE(mocker.flag);
}

TEST_F(MockTest, SubscriberOnExecutor)
{
  class MockSubscriber : public core::IMockSubscriber<std::string>
  {
   public:
    std::atomic_int count = 0;

   protected:
    void OnNullSubscriberError() override
    {
      GTEST_FAIL();
    }

    void AnalyzeAsync() override
    {
      ++count;
    }
  };

  MockSubscriber mocker;
  res::Channel<std::string> ch = ctrl.GetContext().sub().InitMock("/mock/subscriber", mocker);

  res::Executor exe = ctrl.GetContext().InitExecutor("work_thread_pool");
  ctrl.GetContext().exe(exe).Subscribe(
    ch,
    [](const std::string &) {
    });

  ctrl.LetStart();
  for (int i = 0; i < 100; ++i)
    mocker.FeedAsync("");

  ctrl.LetEnd();
  GTEST_ASSERT_EQ(mocker.count, 100);
}

TEST_F(MockTest, Client)
{
  class MockClient : public core::IMockClient<std::string, int>
  {
   protected:
    void AnalyzeAndFeedback(const aimrt::rpc::ContextRef &, const std::string &q, int &p, aimrt::rpc::Status &ret) override
    {
      if (q == "abc")
        p = 1;
      else
        p = 2;

      ret = aimrt::rpc::Status{AIMRT_RPC_STATUS_UNKNOWN};
    }
  };

  MockClient mocker;
  res::Service<std::string, int> srv = ctrl.GetContext().cli().InitMock("/mock/client", mocker);

  int response           = 0;
  aimrt::rpc::Status ret = ctrl.GetContext().cli().Call(srv, std::string("abc"), response).Sync();
  GTEST_ASSERT_EQ(ret.Code(), AIMRT_RPC_STATUS_UNKNOWN);
  GTEST_ASSERT_EQ(response, 1);

  ctrl.GetContext().cli().Call(srv, std::string("edf"), response).Sync();
  GTEST_ASSERT_EQ(response, 2);
}

TEST_F(MockTest, Server)
{
  class MockServer : public core::IMockServer<std::string, int>
  {
   protected:
    void OnNullServerError() override
    {
      GTEST_FAIL();
    }

    void Analyze(const aimrt::rpc::ContextRef &rpc_ctx, const std::string &q, const int &p, const aimrt::rpc::Status &ret) override
    {
      if (q == "abc")
        GTEST_ASSERT_EQ(p, 1);
      else
        GTEST_ASSERT_EQ(p, 2);

      GTEST_ASSERT_EQ(ret.Code(), AIMRT_RPC_STATUS_UNKNOWN);
    }

    void AnalyzeAsync(const aimrt::rpc::ContextRef &, const std::string &, const int &, const aimrt::rpc::Status &) override
    {
      GTEST_FAIL();
    }
  };

  MockServer mocker;
  res::Service<std::string, int> srv = ctrl.GetContext().srv().InitMock("/mock/server", mocker);

  ctrl.GetContext().srv().ServeInline(
    srv,
    [](const std::string &q, int &p) {
      if (q == "abc")
        p = 1;
      else
        p = 2;
      return aimrt::rpc::Status{AIMRT_RPC_STATUS_UNKNOWN};
    });

  mocker.Feed("abc");
  mocker.Feed("edf");
}

TEST_F(MockTest, NullServer)
{
  class MockServer : public core::IMockServer<std::string, int>
  {
   public:
    bool flag = false;

   protected:
    void OnNullServerError() override
    {
      flag = true;
    }

    void Analyze(const aimrt::rpc::ContextRef &, const std::string &, const int &, const aimrt::rpc::Status &) override
    {
      GTEST_FAIL();
    }

    void AnalyzeAsync(const aimrt::rpc::ContextRef &, const std::string &, const int &, const aimrt::rpc::Status &) override
    {
      GTEST_FAIL();
    }
  };

  MockServer mocker;
  res::Service<std::string, int> srv = ctrl.GetContext().srv().InitMock("/mock/server", mocker);

  mocker.Feed("abc");
  GTEST_ASSERT_TRUE(mocker.flag);
}

TEST_F(MockTest, ServerOnExecutor)
{
  class MockServer : public core::IMockServer<std::string, int>
  {
   public:
    std::atomic_int sum = 0;

   protected:
    void OnNullServerError() override
    {
      GTEST_FAIL();
    }

    void Analyze(const aimrt::rpc::ContextRef &, const std::string &, const int &, const aimrt::rpc::Status &) override
    {
      GTEST_FAIL();
    }

    void AnalyzeAsync(const aimrt::rpc::ContextRef &, const std::string &, const int &p, const aimrt::rpc::Status &) override
    {
      sum += p;
    }
  };

  MockServer mocker;
  res::Service<std::string, int> srv = ctrl.GetContext().srv().InitMock("/mock/server", mocker);

  res::Executor exe = ctrl.GetContext().InitExecutor("work_thread_pool");
  ctrl.GetContext().exe(exe).Serve(
    srv,
    [](const std::string &request, int &response) -> aimrt::rpc::Status {
      response = std::stoi(request);
      return {};
    });

  ctrl.LetStart();
  int sum = 0;
  for (int i = 0; i < 100; ++i) {
    sum += i;
    mocker.FeedAsync(std::to_string(i));
  }

  ctrl.LetEnd();
  GTEST_ASSERT_EQ(mocker.sum, sum);
}
}  // namespace aimrte::test
