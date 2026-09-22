// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/all_in_one/include/aimrte.h"
#include "src/camera/mod/tzmod.hpp"

using namespace aima::sensors::camera;

int main(int argc, char **argv) {
  aimrte::Cfg cfg(argc, argv, "tzcamera_gmsl");
  cfg.WithDefaultLogger()
      .WithDefaultTimeoutExecutor()
      .WithDefaultMqtt()
      .WithDefaultRos();

  cfg[aimrte::cfg::Exe::asio_thread] += {
      .name = "tzcamera",
      .options = {{.thread_num = 8, .thread_sched_policy = "SCHED_FIFO:20", .thread_bind_cpu = {{9, 8}}}},
  };

  return aimrte::Run(cfg, {{"tzcamera", std::make_shared<TzCameraMod>()}});
}