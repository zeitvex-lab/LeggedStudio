// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "aimdk/protocol/demo/demo_service.h"
#include "aimdk/protocol/demo/demo_channel.pb.h"
#include "src/all_in_one/include/aimrte.h"
#include "./time_wheel_executor.h"
#include "./worker.h"
/// 可以定义很多组类型转换函数
namespace aimrte::impl
{
template <>
void Convert(const int &src, aimdk::protocol::BallChannel &dst)
{
  dst.mutable_ball()->set_msg("int value " + std::to_string(src));
}

template <>
void Convert(const aimdk::protocol::BallChannel &src, int &dst)
{
}
}  // namespace aimrte::impl

/// 最终为自定义类型，选择全局唯一的转换类型（仅可以定义一次）
/// 这部分可以在 app 的定义处定义。
namespace aimrte::convert
{
template <>
struct For<int> : By<aimdk::protocol::BallChannel> {
};
}  // namespace aimrte::convert

namespace
{

class PublisherWorker : public aimrt::module::executor::BaseWorker
{
 private:
  aimrte::Pub<int> publisher_;
  std::shared_ptr<aimrte::core::Context> ctx_;

 public:
  void Run() override
  {
    ctx_->LetMe();
    publisher_.Publish(1);
  }

  PublisherWorker(aimrte::Pub<int> pub, std::shared_ptr<aimrte::core::Context> ctx)
      : aimrt::module::executor::BaseWorker((uint64_t)(1e6), "test_publisher"), publisher_(pub), ctx_(ctx) {}
};

class MyModule : public aimrte::Mod
{
 public:
  struct Option {
    aimrte::Pub<int> pub{"/my/pub/topic"};
    aimrte::Sub<int> sub{"/my/pub/topic"};
    aimrte::Exe exe{"my_executor"};
    aimdk::protocol::res::DemoService srv;
    aimdk::protocol::res::DemoServiceProxy cli;
  };

 protected:
  void OnConfigure(aimrte::ModCfg &cfg) override
  {
    using namespace aimrte::cfg;

    cfg
      [Module::Basic]
        .Config(option_)
          [Ch::local]
        .Def(option_.pub)
        .Def(option_.sub)
          [Rpc::mqtt]
        .Def(option_.cli, ignore_invalid)
          [Rpc::ros2]
        .Def(option_.srv)  // 注意，srv 需要一直生存至模块执行结束
          [Module::Executor]
        .Declare(option_.exe);
  }

  bool OnInitialize() override
  {
    option_.sub.WhenInit().SubscribeOn(option_.exe, [](const int &sub) {});
    time_wheel_executor_.Init(GetCoreRef().GetExecutorManager().GetExecutor(option_.exe.GetName()));
    time_wheel_executor_.AddWorker<PublisherWorker>(option_.pub, GetContextPtr());

    return true;
  }

  bool OnStart() override
  {
    run_flag_ = true;
    time_wheel_executor_.Start();
    return true;
  }

  void OnShutdown() override
  {
    run_flag_ = false;
    time_wheel_executor_.Shutdown();
  }

 private:
  Option option_;
  std::atomic_bool run_flag_ = false;
  aimrt::module::executor::TimeWheelExecutor time_wheel_executor_;
};

}  // namespace

int main(int argc, char **argv)
{
  aimrte::Cfg cfg(argc, argv, "aimrte_plugin_example_monitor");

  cfg
    .WithDefaultLogger()
    .WithDefaultTimeoutExecutor()
    .WithDefaultRos()
    .WithDefaultLocal()
    .WithDefaultMqtt();

  cfg[aimrte::cfg::Exe::asio_thread] += {
    .name    = MyModule::Option().exe.GetName(),
    .options = {{
      .thread_num = 4,
    }},
  };

  return aimrte::Run(cfg, {{"monitor_example", std::make_shared<MyModule>()}});
}
