// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/module_base.h"
#include "src/macro/macro.h"

/**
 * @brief 定义一个模块注册列表
 */
#define AIMRTE_DETAILS_DEFINE_MODULE_REGISTER_ARRAY(...)                                             \
  namespace aimrte::program_details                                                                  \
  {                                                                                                  \
  static constexpr std::tuple<std::string_view, ::aimrt::ModuleBase *(*)()> module_register_array[]{ \
    AIMRTE_INVOKE(AIMRTE_DETAILS_DEFINE_ONE_MODULE, __VA_ARGS__)};                                   \
  }

#define AIMRTE_DETAILS_DEFINE_ONE_MODULE(_pack_params_)                              \
  {                                                                                  \
    AIMRTE_DETAILS_DEFINE_ONE_MODULE_UNPACK_NAME _pack_params_,                      \
    []() -> ::aimrt::ModuleBase * {                                                  \
      return new AIMRTE_DETAILS_DEFINE_ONE_MODULE_UNPACK_CONSTRUCTING _pack_params_; \
    }},

#define AIMRTE_DETAILS_DEFINE_ONE_MODULE_UNPACK_NAME(_name_, ...) _name_
#define AIMRTE_DETAILS_DEFINE_ONE_MODULE_UNPACK_CONSTRUCTING(_name_, ...) __VA_ARGS__
