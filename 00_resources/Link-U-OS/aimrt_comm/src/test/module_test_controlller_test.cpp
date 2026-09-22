// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include <gtest/gtest.h>
#include "src/runtime/base/i_core.h"
#include "./module_test_controller.h"

namespace aimrte::test
{
class ModuleTestControllerTest : public ::testing::Test
{
 protected:
  ModuleTestController ctrl;
};

static inline const std::string cfg = R"(
aimrt:
  configurator:
    temp_cfg_path: ./cfg/tmp # 生成的临时模块配置文件存放路径
  log: # log配置
    core_lvl: INFO # 内核日志等级，可选项：Trace/Debug/Info/Warn/Error/Fatal/Off，不区分大小写
    default_module_lvl: Trace # 模块默认日志等级
    backends: # 日志backends
      - type: console # 控制台日志
        options:
          color: true # 是否彩色打印
      - type: rotate_file # 文件日志
        options:
          path: ./log # 日志文件路径
          filename: example_helloworld_pkg_mode.log # 日志文件名称
          max_file_size_m: 4 # 日志文件最大尺寸，单位m
          max_file_num: 10 # 最大日志文件数量，0代表无限
  executor: # 执行器配置
    executors: # 当前先支持thread型，未来可根据加载的网络模块提供更多类型
      - name: work_thread_pool # 线程池
        type: asio_thread
        options:
          thread_num: 5 # 线程数，不指定则默认单线程
)";

TEST_F(ModuleTestControllerTest, Created)
{
  ctrl.LetStart();
}

TEST_F(ModuleTestControllerTest, Init)
{
  ctrl.SetConfigContent(cfg);
  ctrl.LetInit();
  GTEST_ASSERT_EQ(uint32_t(ctrl.GetCore().GetState()), uint32_t(aimrte::runtime::State::kPreInitModules));
}

TEST_F(ModuleTestControllerTest, Start)
{
  ctrl.SetConfigContent(cfg);
  ctrl.LetStart();
  GTEST_ASSERT_EQ(uint32_t(ctrl.GetCore().GetState()), uint32_t(aimrte::runtime::State::kPreStartModules));
}

TEST_F(ModuleTestControllerTest, Run)
{
  ctrl.SetConfigContent(cfg);
  ctrl.LetRun();
  GTEST_ASSERT_EQ(uint32_t(ctrl.GetCore().GetState()), uint32_t(aimrte::runtime::State::kPostStart));
}

TEST_F(ModuleTestControllerTest, Shutdown)
{
  ctrl.SetConfigContent(cfg);
  ctrl.LetShutdown();
  GTEST_ASSERT_EQ(uint32_t(ctrl.GetCore().GetState()), uint32_t(aimrte::runtime::State::kPreShutdownModules));
}

TEST_F(ModuleTestControllerTest, End)
{
  ctrl.SetConfigContent(cfg);
  ctrl.LetEnd();
  GTEST_ASSERT_EQ(uint32_t(ctrl.GetCore().GetState()), uint32_t(aimrte::runtime::State::kPostShutdown));
}

TEST_F(ModuleTestControllerTest, WrongOrderWillThrow)
try {
  ctrl.SetConfigContent(cfg);
  ctrl.LetRun();
  ctrl.LetInit();
  GTEST_FAIL();
} catch (const std::exception& ec) {
  std::cout << ec.what() << std::endl;
}
}  // namespace aimrte::test
