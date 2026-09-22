// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"

namespace aimrte::hds
{

struct ModuleException {
  enum class Type {
    kNormal           = 0,  // 正常类型
    kTriggerAppear    = 1,  // 触发型异常(该异常产生)
    kTriggerDisappear = 2,  // 触发型异常(该异常消失)
  };
  uint64_t timestamp        = 0;
  uint8_t module_id         = 0;
  uint32_t module_exception = 0;
  Type type                 = Type::kNormal;
  std::string info          = "";
};

struct ModuleExceptionChannel {
  uint64_t timestamp = 0;
  std::vector<ModuleException> exception_list;
};

struct Context {
  // 异常码的上传通道
  res::Channel<ModuleExceptionChannel> ch_ec;
};
}  // namespace aimrte::hds
