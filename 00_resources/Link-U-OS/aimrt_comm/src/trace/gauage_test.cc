// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/test/test.h"
#include "src/trace/trace.h"

namespace aima::TestModule
{
class TraceContextTest : public aimrte::test::TestBase
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

TEST_F(TraceContextTest, GaugeWithAttribute)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  bool is_called = false;
  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([&is_called](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    // GTEST_ASSERT_EQ(msg.event_name, "test_event");
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::Status::SUCCESS);
    GTEST_ASSERT_EQ(event.attributes.at("TestGaugeV1"), "test_value1");
    GTEST_ASSERT_EQ(event.attributes.at("TestGaugeV2"), "test_value2");
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestGauge");
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Gauge");
    GTEST_ASSERT_EQ(event.code, EventCode::TestGauge::value);
    GTEST_ASSERT_EQ(event.module_id, EventCode::TestGauge::GetInfo().module_id);
    auto gauge = std::stod(event.attributes.at("value"));
    GTEST_ASSERT_EQ(gauge, 1);
    is_called = true;
  });

  // 填属性的事件（属性在Excel表格中定义）
  auto gauge = aimrte::trace::Gauge<EventCode::TestGauge, double>(EventCode::TestGauge::Attribute{
    .TestGaugeV1 = "test_value1",
    .TestGaugeV2 = "test_value2",
  });
  gauge.Value(1);
  EXPECT_TRUE(is_called);
}

TEST_F(TraceContextTest, GaugeValue)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Gauge");
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestGauge");
    GTEST_ASSERT_EQ(event.code, EventCode::TestGauge::value);
    GTEST_ASSERT_EQ(event.module_id, EventCode::TestGauge::GetInfo().module_id);
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::SUCCESS);
    std::cout << "gauge:" << event.attributes.at("value") << std::endl;
    auto gauge = std::stod(event.attributes.at("value"));
    GTEST_ASSERT_EQ(gauge, 1);
  });

  auto gauge = aimrte::trace::Gauge<EventCode::TestGauge, int>();

  // 直接上报value
  gauge.Value(1);
}

TEST_F(TraceContextTest, GaugeGreaterThan)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Gauge");
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestGauge");
    GTEST_ASSERT_EQ(event.attributes.at("comparison"), "greater_than");
    auto threshold = std::stod(event.attributes.at("threshold"));
    GTEST_ASSERT_EQ(threshold, 0.1);
    GTEST_ASSERT_EQ(event.code, EventCode::TestGauge::value);
    GTEST_ASSERT_EQ(event.module_id, EventCode::TestGauge::GetInfo().module_id);
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::SUCCESS);
    std::cout << "gauge:" << event.attributes.at("value") << std::endl;
    auto gauge = std::stod(event.attributes.at("value"));
    GTEST_ASSERT_EQ(gauge, 2.1);
  });

  auto gauge = aimrte::trace::Gauge<EventCode::TestGauge, double>();

  // 比较value和threshold
  // 大于
  gauge.GreaterThan(2.1, 0.1);
}

TEST_F(TraceContextTest, GaugeEqualTo)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Gauge");
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestGauge");
    GTEST_ASSERT_EQ(event.attributes.at("comparison"), "equal_to");
    GTEST_ASSERT_EQ(event.attributes.at("threshold"), "2");
    GTEST_ASSERT_EQ(event.code, EventCode::TestGauge::value);
    GTEST_ASSERT_EQ(event.module_id, EventCode::TestGauge::GetInfo().module_id);
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::SUCCESS);
    std::cout << "gauge:" << event.attributes.at("value") << std::endl;
    auto gauge = std::stod(event.attributes.at("value"));
    GTEST_ASSERT_EQ(gauge, 2);
  });

  auto gauge = aimrte::trace::Gauge<EventCode::TestGauge, int>();

  // 比较value和threshold
  // 等于
  gauge.EqualTo(2, 2);
}

TEST_F(TraceContextTest, GaugeLessThan)
{
  ctrl.LetInit();
  auto& trace_ctx = ctrl.GetContext().InitSubContext<aimrte::trace::internal::Context>(aimrte::core::Context::SubContext::Trace);

  aimrte::test::MockPublisher<aimrte::trace::internal::EventChannel> pub_mocker;
  trace_ctx.ch_event = pub_mocker.Init();

  ctrl.LetStart();

  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([](const aimrte::trace::internal::EventChannel& msg) {
    auto event = msg.events.front();
    GTEST_ASSERT_EQ(event.attributes.at("type"), "Gauge");
    GTEST_ASSERT_EQ(event.attributes.at("enum_name"), "TestGauge");
    GTEST_ASSERT_EQ(event.attributes.at("comparison"), "less_than");
    auto threshold = std::stoi(event.attributes.at("threshold"));
    GTEST_ASSERT_EQ(threshold, 2);
    GTEST_ASSERT_EQ(event.code, EventCode::TestGauge::value);
    GTEST_ASSERT_EQ(event.module_id, EventCode::TestGauge::GetInfo().module_id);
    GTEST_ASSERT_EQ(event.status, aimrte::trace::internal::Event::SUCCESS);
    std::cout << "gauge:" << event.attributes.at("value") << std::endl;
    auto gauge = std::stod(event.attributes.at("value"));
    GTEST_ASSERT_EQ(gauge, 1);
  });

  auto gauge = aimrte::trace::Gauge<EventCode::TestGauge, int>();

  // 比较value和threshold
  // 小于
  gauge.LessThan(1, 2);
}

}  // namespace aima::TestModule
