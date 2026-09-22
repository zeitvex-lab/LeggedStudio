// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/all_in_one/include/aimrte.h"

namespace example::program
{
class MyModule : public aimrte::Mod
{
  struct Option {
    int x = 0;
    int y = 0;
    int z = 0;
  };

 public:
  MyModule() = default;

  MyModule(int x, int y);

 protected:
  void OnConfigure(aimrte::ModCfg& cfg) override;

  bool OnInitialize() override;

  bool OnStart() override;

  void OnShutdown() override;

 private:
  Option option_;
};
}  // namespace example::program
