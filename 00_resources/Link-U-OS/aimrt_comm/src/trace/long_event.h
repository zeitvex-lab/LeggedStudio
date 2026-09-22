// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include <source_location>
#include <string>
#include "./internal/reporter.h"
namespace aimrte::trace
{

template <typename TEventCode>
class Event;

template <typename TEventCode>
class LongEvent
{
  friend class Event<TEventCode>;

 public:
  LongEvent() = default;

  explicit LongEvent(std::source_location call_loc) : call_loc_(call_loc)
  {
    const auto info                     = TEventCode::GetInfo();
    event_info_                         = internal::GetNewEventInfo();
    event_info_.name                    = info.description;
    event_info_.code                    = TEventCode::value;
    event_info_.module_id               = info.module_id;
    event_info_.attributes["enum_name"] = info.name;
    event_info_.attributes["type"]      = "LongEvent";
    event_info_.status                  = aimrte::trace::internal::Event::Status::STARTING;
    event_info_.event_content           = "";
    // 上报开始事件
    internal::Report(event_info_, call_loc_);
  }

  explicit LongEvent(TEventCode::Attribute attribute, std::string_view event_content = "", std::source_location call_loc = std::source_location::current())
  {
    const auto info                     = TEventCode::GetInfo();
    event_info_                         = internal::GetNewEventInfo();
    event_info_.name                    = info.description;
    event_info_.code                    = TEventCode::value;
    event_info_.module_id               = info.module_id;
    event_info_.attributes["enum_name"] = info.name;
    event_info_.attributes["type"]      = "LongEvent";
    for (auto& [key, value] : attribute.GetAttribute()) {
      event_info_.attributes[key] = value;
    }
    event_info_.status        = aimrte::trace::internal::Event::Status::STARTING;
    event_info_.event_content = event_content;
    // 上报开始事件
    internal::Report(event_info_, call_loc_);
  }

  virtual ~LongEvent() = default;

 private:
  void UpdateEventContent(std::string_view event_content)
  {
    event_info_.event_content = event_content;
  }

  void Report()
  {
    if (is_reported_) {
      std::cerr << "LongEvent is already reported" << std::endl;
      return;
    }

    // 上报结束事件
    event_info_.timestamp = aimrte::utils::GetCurrentTimestamp();
    event_info_.status    = aimrte::trace::internal::Event::Status::SUCCESS;
    internal::Report(event_info_, call_loc_);
    is_reported_ = true;
  }

 private:
  internal::Event event_info_;
  std::source_location call_loc_;
  bool is_reported_ = false;
};

}  // namespace aimrte::trace
