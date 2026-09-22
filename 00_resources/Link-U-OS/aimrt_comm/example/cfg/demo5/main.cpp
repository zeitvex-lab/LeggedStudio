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

    aimrte::Exe exe1{"~/my_private_executor", 2};
    aimrte::Exe exe2{"global_executor_maybe_multiple_defined", 3};

    aimdk::protocol::res::DemoService srv;
    aimdk::protocol::res::DemoServiceProxy cli;

    std::chrono::steady_clock::duration t{std::chrono::seconds(1)};
    std::string param{"hello world"};
  };

  struct OtherOption {
    aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/another/pub/topic"};
    aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/another/sub/topic"};

    aimrte::Exe exe1{"~/my_another_private_executor", 2};
    aimrte::Exe exe2{"another_global_executor_maybe_multiple_defined", 3};

    std::chrono::steady_clock::duration t{std::chrono::seconds(1)};
    std::string param{"hello world"};
  };

 protected:
  void OnConfigure(aimrte::ModCfg& cfg) override
  {
    cfg.ConfigAndDefineByDefault(option_);
    cfg.ConfigAndDefineByDefault(cfg.Yaml()["sub_option"], other_option_);
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
  OtherOption other_option_;
};
}  // namespace

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "example_cfg_demo5");
  return aimrte::Run(cfg, {{"my_module", std::make_shared<MyModule>()}});
}
