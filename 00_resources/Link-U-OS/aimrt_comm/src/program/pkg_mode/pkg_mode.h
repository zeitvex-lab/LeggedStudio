// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/program/details/define_module_register_array.h"
#include "src/program/details/module_base_span.h"

namespace aimrte::program_details
{
/**
 * @return 给定模块注册列表中的模块数量
 */
constexpr std::size_t GetModulesNumber(const ModuleCreatorSpan& module_creators)
{
  return module_creators.size();
}

/**
 * @return 需要注册的模块名称列表
 */
template <std::size_t MODULES_NUMBER>
const aimrt_string_view_t* GetModulesNames(const ModuleCreatorSpan& module_creators)
{
  constexpr std::size_t modules_number = MODULES_NUMBER;
  static aimrt_string_view_t modules_names[MODULES_NUMBER];

  for (std::size_t idx = 0; idx < modules_number; ++idx) {
    const std::string_view& str = std::get<0>(module_creators[idx]);

    modules_names[idx] = aimrt_string_view_t{
      .str = str.data(),
      .len = str.size()};
  }

  return modules_names;
}

/**
 * @brief 从注册列表中，创建指定名称的模块对象
 */
const aimrt_module_base_t* CreateModule(const ModuleCreatorSpan& module_creators, aimrt_string_view_t name);

/**
 * @brief 析构给定的模块对象
 */
void DestroyModule(const aimrt_module_base_t* module_ptr);
}  // namespace aimrte::program_details

/**
 * @brief 为当前的 pkg library target，注册一系列需要启动的模块，用于 pkg 模式。
 * @code
 *   #include <aimrte/use/pkg_mode.h>
 *
 *   static constexpr std::tuple<std::string_view, aimrt::ModuleBase *(*)()>
 *     aimrt_module_register_array[]{
 *       {
 *         "MyModule1",
 *         []() -> aimrt::ModuleBase * {
 *           return new MyModule(1, 2, 3);
 *         }
 *       },
 *       {
 *         "MyModule2",
 *         []() -> aimrt::ModuleBase * {
 *           return new MyModule(4, 5, 6);
 *         }
 *       },
 *  };
 *
 *  AIMRT_PKG_MAIN(aimrt_module_register_array)
 * @endcode
 */
#define AIMRT_PKG_MAIN(_module_register_array_)                                  \
  extern "C" {                                                                   \
  size_t AimRTDynlibGetModuleNum()                                               \
  {                                                                              \
    return aimrte::program_details::GetModulesNumber(_module_register_array_);   \
  }                                                                              \
                                                                                 \
  const aimrt_string_view_t* AimRTDynlibGetModuleNameList()                      \
  {                                                                              \
    return aimrte::program_details::GetModulesNames<                             \
      std::size(_module_register_array_)>(_module_register_array_);              \
  }                                                                              \
                                                                                 \
  const aimrt_module_base_t* AimRTDynlibCreateModule(aimrt_string_view_t name)   \
  {                                                                              \
    return aimrte::program_details::CreateModule(_module_register_array_, name); \
  }                                                                              \
                                                                                 \
  void AimRTDynlibDestroyModule(const aimrt_module_base_t* module_ptr)           \
  {                                                                              \
    aimrte::program_details::DestroyModule(module_ptr);                          \
  }                                                                              \
  }

/**
 * @brief 定义模块注册过程，用于 pkg 模式
 * @code
 *   #include <aimrte/use/pkg_mode.h>
 *
 *   AIMRTE_PKG_MAIN(
 *     ("MyModule1", MyModule(1, 2, 3)),
 *     ("MyModule2", MyModule(4, 5, 6))
 *   )
 * @endcode
 */
#define AIMRTE_PKG_MAIN(...)                               \
  AIMRTE_DETAILS_DEFINE_MODULE_REGISTER_ARRAY(__VA_ARGS__) \
  AIMRT_PKG_MAIN(aimrte::program_details::module_register_array)
