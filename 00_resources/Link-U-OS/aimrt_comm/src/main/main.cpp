// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/program/app_mode/app_mode.h"

int main(int argc, char** argv)
{
  aimrte::Cfg cfg(argc, argv, "aimrte");
  cfg.WithDefaultLogger();
  return aimrte::Run(cfg, {});
}
