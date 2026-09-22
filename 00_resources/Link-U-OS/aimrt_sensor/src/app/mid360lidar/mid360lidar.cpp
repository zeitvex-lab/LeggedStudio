// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/all_in_one/include/aimrte.h"
#include "src/mid360_lidar/module/mid360_module.hpp"


int main(int argc, char **argv) {
  aimrte::Cfg cfg(argc, argv, "mid360_lidar");
  cfg.WithDefaultLogger()
      .WithDefaultTimeoutExecutor()
      .WithDefaultRos();

  // cfg[aimrte::cfg::Exe::asio_thread] += {
  //     .name = "airylidar",
  //     .options = {{.thread_num = 8}},
  // };

  return aimrte::Run(cfg, {{"mid360lidar", std::make_shared<::aima::sensor::lidar::mid360::Mid360Mod>()}});
}