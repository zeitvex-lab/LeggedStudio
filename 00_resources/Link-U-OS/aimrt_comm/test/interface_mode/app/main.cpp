// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/all_in_one/include/aimrte.h"

namespace
{
class Module : public aimrte::ctx::ModuleBase
{
 protected:
  bool OnInitialize() override
  {
    return true;
  }

  bool OnStart() override
  {
    return false;
  }

  void OnShutdown() override
  {
  }
};
}  // namespace

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "test_app");

  cfg
    .WithDefaultLogger()
    .WithDefaultTimeoutExecutor()
    .WithDefaultMqtt()
    .WithDefaultRos();

  return aimrte::Run(cfg, {{"TestModule", std::make_shared<Module>()}});
}
