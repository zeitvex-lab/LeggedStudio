// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/module/cfg.h"
#include "src/register_backward/register_backward.h"  // 用于注册 backward trace print
#include <cstdint>

#include "src/program/details/define_module_register_array.h"
#include "src/program/details/module_base_span.h"

/**
 * @brief 定义需要注册的模块列表，以 app 模式声明一个 main 函数，要求本 target 是可执行的。
 * @code
 *   #include <aimrte/use/app_mode.h>
 *
 *   AIMRTE_APP_MAIN(
 *     ("MyModule1", MyModule(1, 2, 3)),
 *     ("MyModule2", MyModule(4, 5, 6))
 *   )
 * @endcode
 */
#define AIMRTE_APP_MAIN(...)                                                                              \
  AIMRTE_DETAILS_DEFINE_MODULE_REGISTER_ARRAY(__VA_ARGS__)                                                \
  std::int32_t main(std::int32_t argc, char **argv)                                                       \
  {                                                                                                       \
    return ::aimrte::program_details::Main(argc, argv, ::aimrte::program_details::module_register_array); \
  }

namespace aimrte::program_details
{
std::int32_t Main(std::int32_t argc, char **argv, const ModuleCreatorSpan &module_creators);
}

namespace aimrte
{
/**
 * @brief 名字与 aimrt 模块指针的数组容器
 */
using NamedModulePtrList = std::vector<std::pair<std::string, std::shared_ptr<aimrt::ModuleBase>>>;

/**
 * @brief 提供给开发者使用的，AimRTe 程序启动的入口，在 main() 中调用，将阻塞至整个框架运行结束。
 * @param cfg 启动参数
 * @param modules 需要被注册启动的模块列表，将按顺序注册，注意名称不能相同
 * @return 执行返回值，0 为成功无错误。
 */
std::int32_t Run(Cfg &cfg, NamedModulePtrList modules);
}  // namespace aimrte
