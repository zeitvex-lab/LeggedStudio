// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "aimdk/protocol/demo/demo_channel.pb.h"
#include "aimdk/protocol/demo/demo_service.h"
#include "src/module/module_base.h"
#include "src/program/app_mode/app_mode.h"

namespace
{
class MyModule : public aimrte::ctx::ModuleBase
{
 public:
  struct MyOption {
    std::string topic_name;
    std::string executor_name;
  };

 protected:
  void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override
  {
    using namespace aimrte::cfg;

    MyOption option;

    cfg
      [Module::Basic]
        .Config(option)

          [Module::Logger]
        .Level(LogLevel::Info)

          [Ch::ros2 | Ch::mqtt]
        .Def(publisher_, option.topic_name)

          [Module::Executor]
        .Declare(exe_, option.executor_name);
  }

  bool OnInitialize() override
  {
    return true;
  }

  bool OnStart() override
  {
    exe_.Post(
      [&]() {
        while (aimrte::ctx::Ok()) {
          publisher_.Publish({});
          std::this_thread::sleep_for(std::chrono::seconds(1));
        }
      });
    return true;
  }

  void OnShutdown() override
  {
  }

 private:
  aimrte::ctx::Publisher<aimdk::protocol::BallChannel> publisher_;

  aimrte::ctx::Executor exe_;
};
}  // namespace

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "example_cfg_demo1");

  cfg
    .WithDefaultLogger()
    .WithDefaultTimeoutExecutor()
    .WithDefaultMqtt()
    .WithDefaultRos()
    .SetModuleConfig("my_module", MyModule::MyOption{.topic_name = "/a/b/c", .executor_name = "my_executor"});

  cfg[aimrte::cfg::Exe::asio_thread] += {
    .name = "my_executor"};

  return aimrte::Run(cfg, {{"my_module", std::make_shared<MyModule>()}});
}
