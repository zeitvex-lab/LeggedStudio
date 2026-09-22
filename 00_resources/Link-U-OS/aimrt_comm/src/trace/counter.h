// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include <source_location>
#include <string>
#include "./internal/reporter.h"

namespace aimrte::trace
{

template <typename TEventCode>
class Counter
{
 public:
  explicit Counter(int64_t value = 1, std::string_view event_content = "", std::source_location call_loc = std::source_location::current())
  {
    const auto info         = TEventCode::GetInfo();
    counter_info_           = internal::GetNewEventInfo();
    counter_info_.name      = info.description;
    counter_info_.code      = TEventCode::value;
    counter_info_.module_id = info.module_id;

    counter_info_.attributes["enum_name"] = info.name;
    counter_info_.attributes["type"]      = "Counter";
    counter_info_.attributes["value"]     = std::to_string(value);
    counter_info_.event_content           = event_content;
    internal::Report(counter_info_, call_loc_);
  }

  explicit Counter(TEventCode::Attribute attribute, std::string_view event_content = "", int64_t value = 1, std::source_location call_loc = std::source_location::current())
  {
    const auto info                       = TEventCode::GetInfo();
    counter_info_                         = internal::GetNewEventInfo();
    counter_info_.name                    = info.description;
    counter_info_.code                    = TEventCode::value;
    counter_info_.module_id               = info.module_id;
    counter_info_.attributes["enum_name"] = info.name;
    counter_info_.attributes["type"]      = "Counter";
    counter_info_.attributes["value"]     = std::to_string(value);
    for (auto& [key, value] : attribute.GetAttribute()) {
      counter_info_.attributes[key] = value;
    }
    counter_info_.event_content = event_content;
    internal::Report(counter_info_, call_loc_);
  }

  virtual ~Counter()
  {
    is_reported_ = true;
  }

 private:
  internal::Event counter_info_;
  std::source_location call_loc_;
  bool is_reported_ = false;
};

}  // namespace aimrte::trace
