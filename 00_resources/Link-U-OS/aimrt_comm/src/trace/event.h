// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string_view>
#include "./long_event.h"

namespace aimrte::trace
{

template <typename TEventCode>
class Event
{
 public:
  explicit Event(TEventCode::Attribute attribute, std::string_view event_content = "", uint64_t timestamp = aimrte::utils::GetCurrentTimestamp(), std::source_location call_loc = std::source_location::current()) : call_loc_(call_loc)
  {
    const auto info                     = TEventCode::GetInfo();
    event_info_                         = internal::GetNewEventInfo();
    event_info_.name                    = info.description;
    event_info_.code                    = TEventCode::value;
    event_info_.timestamp               = timestamp;
    event_info_.module_id               = info.module_id;
    event_info_.attributes["enum_name"] = info.name;
    event_info_.attributes["type"]      = "Event";
    for (auto& [key, value] : attribute.GetAttribute()) {
      event_info_.attributes[key] = value;
    }
    event_info_.event_content = event_content;
    internal::Report(event_info_, call_loc_);
  }

  explicit Event(uint64_t timestamp = aimrte::utils::GetCurrentTimestamp(), std::source_location call_loc = std::source_location::current()) : call_loc_(call_loc)
  {
    const auto info                     = TEventCode::GetInfo();
    event_info_                         = internal::GetNewEventInfo();
    event_info_.name                    = info.description;
    event_info_.code                    = TEventCode::value;
    event_info_.timestamp               = timestamp;
    event_info_.module_id               = info.module_id;
    event_info_.attributes["enum_name"] = info.name;
    event_info_.attributes["type"]      = "Event";
    event_info_.event_content           = "";
    internal::Report(event_info_, call_loc_);
  }

  virtual ~Event() = default;

  /**
   * @brief 开始一个长事件
   * @param name 事件名称
   * @return
   */
  static LongEvent<TEventCode> Start(std::source_location call_loc = std::source_location::current())
  {
    return LongEvent<TEventCode>(call_loc);
  }

  /**
   * @brief 开始一个长事件
   * @param name 事件名称
   * @return
   */
  static LongEvent<TEventCode> Start(TEventCode::Attribute attribute, std::string_view event_content = "")
  {
    return LongEvent<TEventCode>(attribute, event_content);
  }

  static void UpdateExtra(LongEvent<TEventCode>&& event, std::string_view event_content)
  {
    event.UpdateEventContent(event_content);
  }

  /**
   * @brief 结束一个长事件
   * @param event 长事件
   */
  static void End(LongEvent<TEventCode>&& event)
  {
    event.Report();
  }

 private:
  internal::Event event_info_;
  std::source_location call_loc_;
  bool is_reported_ = false;
};

}  // namespace aimrte::trace
