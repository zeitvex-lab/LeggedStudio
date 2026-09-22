// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include <benchmark/benchmark.h>
#include "src/test/test.h"


namespace aimrte::bench
{
class LogBench : public benchmark::Fixture
{
 public:
  void SetUp(const benchmark::State&) override
  {
    aimrte::trait::renew(ctrl_);
    ctrl_.SetConfigContent(
      R"(
aimrt:
  configurator:
    temp_cfg_path: ./cfg/tmp # 生成的临时模块配置文件存放路径
  log: # log配置
    core_lvl: Info
    default_module_lvl: Info
    backends: # 日志backends
#      - type: console # 控制台日志
#        options:
#          color: true # 是否彩色打印
      - type: rotate_file
        options:
          path: ./log_bench
          filename: bench.log
          max_file_size_m: 4
          max_file_num: 10
          log_executor_name: log_executor

  executor:
    executors:
      - name: log_executor
        type: asio_thread
        options:
          thread_num: 1
)"
    );

    ctrl_.LetStart();
  }

  void TearDown(const benchmark::State&) override
  {
    ctrl_.LetEnd();
    std::filesystem::remove_all("./log_bench");
  }

private:
  test::ModuleTestController ctrl_;
};

BENCHMARK_DEFINE_F(LogBench, BasicUsage)(benchmark::State& st)
{
  for (auto _ : st) {
    ctx::log().Info("Hello world !!!");
  }
}

BENCHMARK_REGISTER_F(LogBench, BasicUsage)->MinTime(5);
}

BENCHMARK_MAIN();
