// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/program/app_mode/app_mode.h"
#include "./module.h"

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "ping_demo");

  // 设置本进程会用到的 AimRT 默认参数。这些配置可以被外部参数所覆盖（详见 example/cfg）
  cfg
    .WithDefaultLogger()
    .WithDefaultZenoh()
    // .WithDefaultIceoryx()
    .WithDefaultRos()
    .WithDefaultMqtt();

  // 执行器需要手动指定
  cfg[aimrte::cfg::Exe::asio_thread] += {
    .name    = example::ping::Module::Option().exe.GetName(),  // 用模块配置的默认值来指定执行器名称，也可以裸写字符串。保持一致就行
    .options = {{.thread_num = 3}},
  };

  // 给定要加载的模块（可以给定多个），并启动框架
  return aimrte::Run(cfg, {{"PingModule", std::make_shared<example::ping::Module>()}});
}
