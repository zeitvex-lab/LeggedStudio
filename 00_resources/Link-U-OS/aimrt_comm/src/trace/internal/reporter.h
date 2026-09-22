// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include "src/trace/internal/context.h"
#include "src/utils/utils.h"
#include <source_location>

namespace aimrte::trace::internal
{
/**
 * @brief 上报事件
 * @param event_info 事件信息
 * @param call_loc 调用位置
 */
inline void Report(const Event& event_info, std::source_location call_loc)
{
  // 获取 AimRTe 上下文
  std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  EventChannel event_channel;
  event_channel.timestamp = event_info.timestamp;
  event_channel.events.push_back(event_info);

  // 获取本系统的上下文
  Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Trace);
  // 发布异常码
  core_ctx->pub().Publish(ctx.ch_event, event_channel);
}

/**
 * @brief 获取新的事件信息
 * @param name 事件名称
 * @return 事件信息
 */
inline Event GetNewEventInfo()
{
  Event event_info;
  event_info.timestamp = aimrte::utils::GetCurrentTimestamp();
  event_info.local_id  = aimrte::utils::GenerateUniqueID();
  event_info.status    = aimrte::trace::internal::Event::Status::SUCCESS;
  return event_info;
}

}  // namespace aimrte::trace::internal
