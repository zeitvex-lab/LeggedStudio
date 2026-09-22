// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "aimdk/protocol/demo/demo_channel.pb.h"
#include "aimdk/protocol/demo/demo_service.h"
#include "src/all_in_one/include/aimrte.h"

/// 可以定义很多组类型转换函数
namespace aimrte::impl
{
template <>
void Convert(const int& src, aimdk::protocol::BallChannel& dst)
{
  dst.mutable_ball()->set_msg("int value " + std::to_string(src));
}

template <>
void Convert(const aimdk::protocol::BallChannel& src, int& dst)
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
class MyModule : public aimrte::Mod
{
 public:
  struct Option {
    aimrte::Pub<int> pub{"/my/pub/topic"};
    aimrte::Sub<int> sub{"/my/sub/topic"};
  };

 protected:
  void OnConfigure(aimrte::ModCfg& cfg) override
  {
    using namespace aimrte::cfg;

    cfg
      [Module::Basic]
        .Config(option_)

          [Ch::ros2 | Ch::mqtt]
        .Def(option_);
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

 private:
  Option option_;
};
}  // namespace

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "example_cfg_demo4");

  cfg
    .WithDefaultLogger()
    .WithDefaultTimeoutExecutor()
    .WithDefaultRos()
    .WithDefaultMqtt();

  return aimrte::Run(cfg, {{"my_module", std::make_shared<MyModule>()}});
}
