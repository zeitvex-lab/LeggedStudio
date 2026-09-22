// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/hds/hds.h"
#include "src/test/test.h"

namespace aima::TestModule
{
class ContextTest : public aimrte::test::TestBase
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

TEST_F(ContextTest, PubExc)
{
  ctrl.LetInit();
  auto& hds_ctx = ctrl.GetContext().InitSubContext<aimrte::hds::Context>(aimrte::core::Context::SubContext::Hds);

  aimrte::test::MockPublisher<aimrte::hds::ModuleExceptionChannel> pub_mocker;
  hds_ctx.ch_ec = pub_mocker.Init();

  ctrl.LetStart();

  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([](const aimrte::hds::ModuleExceptionChannel& msg) {
    GTEST_EXPECT_FALSE(msg.exception_list.empty());
    GTEST_ASSERT_EQ(msg.exception_list[0].module_exception, static_cast<std::uint32_t>(DiagCode::InitFailed));
    GTEST_ASSERT_EQ(msg.exception_list[0].module_id, aimrte::module::details::ModuleTypeTrait<EC>::ModuleType::GetId());
  });
  aimrte::hds::Throw(DiagCode::InitFailed);

  aimrte::hds::Throw(DiagCode::InitFailed, "init failed!");

  aimrte::hds::ThrowCode(aima::TestModule::ModuleManifest::GetId(), static_cast<uint32_t>(DiagCode::InitFailed));

  aimrte::hds::TriggerOn(DiagCode::InitFailed);

  aimrte::hds::TriggerOn(DiagCode::InitFailed, "init failed!");

  aimrte::hds::TriggerOff(DiagCode::InitFailed);

  std::vector<TestModule::DiagCode> ec_list = {DiagCode::InitFailed, DiagCode::InitFailed2};

  aimrte::hds::Throw(ec_list);

  aimrte::hds::Throw(ec_list, "init failed!");

  aimrte::hds::TriggerOn(ec_list);

  aimrte::hds::TriggerOn(ec_list, "init failed!");

  aimrte::hds::TriggerOff(ec_list);
}

TEST_F(ContextTest, PubToast)
{
  ctrl.LetInit();
  auto& hds_ctx = ctrl.GetContext().InitSubContext<aimrte::hds::Context>(aimrte::core::Context::SubContext::Hds);

  aimrte::test::MockPublisher<aimrte::hds::ModuleExceptionChannel> pub_mocker;
  hds_ctx.ch_ec = pub_mocker.Init();

  ctrl.LetStart();

  EXPECT_CALL(pub_mocker, Analyze).WillRepeatedly([](const aimrte::hds::ModuleExceptionChannel& msg) {
    GTEST_EXPECT_FALSE(msg.exception_list.empty());
    GTEST_ASSERT_EQ(msg.exception_list[0].module_exception, 0);
    GTEST_ASSERT_EQ(msg.exception_list[0].module_id, aimrte::module::details::ModuleTypeTrait<EC>::ModuleType::GetId());
    GTEST_ASSERT_EQ(msg.exception_list[0].info, "test toast");
  });

  aimrte::debug::Toast<aima::TestModule::EC>("test toast");
}

}  // namespace aima::TestModule
