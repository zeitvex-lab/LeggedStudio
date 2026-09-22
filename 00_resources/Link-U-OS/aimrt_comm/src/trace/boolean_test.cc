// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "boolean.h"
#include "src/test/test.h"
#include "src/trace/trace.h"

namespace aima::TestModule
{
class BooleanContextTest : public aimrte::test::TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetConfigContent(
      R"(
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
      - type: rotate_file # 文件日志
        options:
          path: ./log # 日志文件路径
          filename: example_helloworld_pkg_mode.log # 日志文件名称
          max_file_size_m: 4 # 日志文件最大尺寸，单位m
          max_file_num: 10 # 最大日志文件数量，0代表无限
  executor: # 执行器配置
    executors: # 当前先支持thread型，未来可根据加载的网络模块提供更多类型
      - name: work_thread_pool # 线程池
        type: asio_thread
        options:
          thread_num: 5 # 线程数，不指定则默认单线程
  channel: # 消息队列相关配置
    backends: # 消息队列后端配置
      - type: local # 本地消息队列配置
        options:
          subscriber_use_inline_executor: false # 订阅端是否使用inline执行器
          subscriber_executor: work_thread_pool # 订阅端回调的执行器，仅在subscriber_use_inline_executor=false时生效
)");
  }

 protected:
  aimrte::test::ModuleTestController ctrl;
};

TEST_F(BooleanContextTest, BooleanDefault)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  bool is_called = false;
  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([&is_called](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestCounter");
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Boolean");
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::Status::SUCCESS);
    GTEST_ASSERT_EQ(event.attributes.at("value"), "1");
    is_called = true;
  });

  aimrte::trace::Boolean<EventCode::TestCounter>();
  EXPECT_TRUE(is_called);
}

TEST_F(BooleanContextTest, Boolean)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  bool is_called = false;
  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([&is_called](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestCounter");
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Boolean");
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::Status::SUCCESS);
    GTEST_ASSERT_EQ(event.attributes.at("value"), "0");
    is_called = true;
  });

  aimrte::trace::Boolean<EventCode::TestCounter>(false);
  EXPECT_TRUE(is_called);
}

}  // namespace aima::TestModule
