// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include "src/core/core.h"
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace aimrte::trace::internal
{

struct Event {
  // 事件状态枚举
  enum Status {
    UNDEFINED = 0,  // 未定义状态
    STARTING  = 1,  // 开始状态
    SUCCESS   = 2,  // 成功状态
    FAILED    = 3,  // 失败状态
    CANCELED  = 4,  // 取消状态
  };

  uint64_t timestamp;                                       // 事件时间戳
  uint32_t module_id;                                       // 模块ID
  uint32_t code;                                            // 事件代码
  std::string name;                                         // 事件名称
  Status status;                                            // 事件状态
  uint64_t local_id;                                        // 本地ID
  std::unordered_map<std::string, std::string> attributes;  // 事件属性键值对
  std::string event_content;                                // 事件内容
};

struct EventChannel {
  uint64_t timestamp;         // 通道时间戳
  std::vector<Event> events;  // 事件列表
};

struct Context {
  res::Channel<EventChannel> ch_event;  // 事件通道
};

}  // namespace aimrte::trace::internal
