// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./my_module.h"

namespace example::program
{
MyModule::MyModule(const int x, const int y)
    : option_{x, y}
{
}

void MyModule::OnConfigure(aimrte::ModCfg& cfg)
{
  // 读取外部给定的模块参数。若外部参数有字段缺省，将采用对应字段的默认值。
  cfg[aimrte::cfg::Module::Basic].Config(option_);
}

bool MyModule::OnInitialize()
{
  return true;
}

bool MyModule::OnStart()
{
  AIMRTE_INFO("{} x: {}, y: {}, z: {}.", GetInfo().name, option_.x, option_.y, option_.z);
  return true;
}

void MyModule::OnShutdown()
{
}
}  // namespace example::program
