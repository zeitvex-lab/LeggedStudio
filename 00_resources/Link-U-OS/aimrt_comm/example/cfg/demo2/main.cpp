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
    std::string pub_topic_name;
    std::string sub_topic_name;

    std::vector<int> values{1, 2, 3};
    std::string message;
  };

  Option option;

 protected:
  void OnConfigure(aimrte::ModCfg& cfg) override
  {
    using namespace aimrte::cfg;

    cfg
      [Module::Basic]
        .Config(option)

          [Ch::ros2]
        .Def(pub_, option.pub_topic_name)
        .Def(sub_, option.sub_topic_name)

          [Rpc::ros2]
        .Def(srv_)
        .Def(cli_);

    for (const int value : option.values) {
      std::cout << "value: " << value << std::endl;
    }

    std::cout << "message: " << option.message << std::endl;
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
  aimrte::Pub<aimdk::protocol::BallChannel> pub_;
  aimrte::Sub<aimdk::protocol::BallChannel> sub_;

  aimdk::protocol::res::DemoService srv_;
  aimdk::protocol::res::DemoServiceProxy cli_;
};
}  // namespace

int main(int argc, char** argv)
{
  // 可实例化 AimRTe 模块，自己管理
  MyModule my_module;
  my_module.option = {
    .pub_topic_name = "my_pub_topic",
    .sub_topic_name = "my_sub_topic",
  };

  const std::string default_pub_topic_name = my_module.option.pub_topic_name;

  // 为 AimRTe 框架构建启动配置
  aimrte::Cfg cfg(argc, argv, "example_cfg_demo2");

  // 使用默认的日志配置
  cfg.WithDefaultLogger();

  // 若没有给定外部的配置、或者外部配置字段缺失的，将采用给定对象对应字段的默认值
  cfg.GetModuleConfig("my_module", my_module.option);

  // 手动配置 ros2 后端，注意，需要定义插件。若使用了 channel 或 rpc 功能，对应的后端也要定义
  cfg[aimrte::cfg::backend::Plugin::ros2] = {};

  cfg[aimrte::cfg::backend::Ch::ros2] = {
    .options = {{
      .pub_topics_options = {{
        {
          .topic_name = default_pub_topic_name,
          .qos        = {{.reliability{"best_effort"}}},
        },
        {
          .topic_name = default_pub_topic_name + "_renamed",
          .qos        = {{.reliability{"best_effort"}}},
        },
      }},
    }},
  };

  cfg[aimrte::cfg::backend::Rpc::ros2] = {};

  // 启动 AimRTe 框架，将自己的局部对象创建为 std::shared_ptr 传入，但生命周期仍然归自己管
  return aimrte::Run(cfg, {{"my_module", aimrte::trait::AddressOf(my_module)}});
}
