// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "aimdk/protocol/demo/demo_channel.pb.h"
#include "aimdk/protocol/demo/demo_service.h"
#include "src/all_in_one/include/aimrte.h"

namespace
{
class MyModule : public aimrte::Mod
{
 public:
  struct Option {
    aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/pub/topic"};
    aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/sub/topic"};

    aimrte::Exe exe{"my_executor"};
    aimrte::Exe mod_exe{"~/my_private_executor"};
    aimrte::Exe mode_exe2{"global_executor_maybe_multiple_defined", 3};

    std::chrono::steady_clock::duration t{std::chrono::seconds(1)};

    aimdk::protocol::res::DemoService srv;

    struct
    {
      aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/nested/pub/topic"};
      aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/nested/sub/topic"};
    } nested_ch;

    struct
    {
      aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/nested/unused/pub/topic"};
      aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/nested/unused/sub/topic"};

      aimdk::protocol::res::DemoServiceProxy cli;
    } nested_rpc;

    struct
    {
      aimrte::Exe exe1{"/my/global/exe"};
      aimrte::Exe exe2{"~/my/private/exe"};
    } nested_exe;
  };

  Option option;

 protected:
  void OnConfigure(aimrte::ModCfg& cfg) override
  {
    using namespace aimrte::cfg;

    cfg
      [Module::Basic]
        .Config(option)

          [Module::Logger]
        .Level(LogLevel::Error)

          [Ch::ros2]
        .Def(option.pub)
        .Def(option.sub)  // 注意，sub 要求其至少生存至初始化阶段

          [Ch::mqtt]
        .Def(option.nested_ch)  // 绑定嵌套类型

          [Rpc::ros2]
        .Def(option.srv)  // 注意，srv 需要一直生存至模块执行结束

          [Rpc::mqtt]
        .Def(option.nested_rpc, ignore_invalid)

          [Module::Executor]
        .Declare(option.exe)     // 声明执行器，但不定义配置，需要在主线程或外部配置去定义
        .Def(option.mod_exe, 2)  // 定义执行器，如果出现同名，将报错
        .Def(option.mode_exe2)
        .Def(option.nested_exe);  // 支持嵌套定义执行器
  }

  bool OnInitialize() override
  {
    return true;
  }

  bool OnStart() override
  {
    return true;
  }

  void OnShutdown() override
  {
  }
};
}  // namespace

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "example_cfg_demo3");

  cfg
    .WithDefaultTimeoutExecutor()
    .WithDefaultLogger()
    .WithDefaultRos()
    .WithDefaultMqtt();

  cfg[aimrte::cfg::Exe::asio_thread] += {
    .name = MyModule::Option().exe.GetName(),
  };

  return aimrte::Run(cfg, {{"my_module", std::make_shared<MyModule>()}});
}
