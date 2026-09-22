// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include <source_location>
#include <string>
#include "./internal/reporter.h"

namespace aimrte::trace
{

template <typename TEventCode>
class Boolean
{
 public:
  explicit Boolean(bool value = true, std::string_view event_content = "", std::source_location call_loc = std::source_location::current())
  {
    const auto info         = TEventCode::GetInfo();
    boolean_info_           = internal::GetNewEventInfo();
    boolean_info_.name      = info.description;
    boolean_info_.code      = TEventCode::value;
    boolean_info_.module_id = info.module_id;

    boolean_info_.attributes["enum_name"] = info.name;
    boolean_info_.attributes["type"]      = "Boolean";
    boolean_info_.attributes["value"]     = std::to_string(value);
    boolean_info_.event_content           = event_content;
    internal::Report(boolean_info_, call_loc_);
  }

  explicit Boolean(TEventCode::Attribute attribute, bool value = true, std::string_view event_content = "", std::source_location call_loc = std::source_location::current())
  {
    const auto info                       = TEventCode::GetInfo();
    boolean_info_                         = internal::GetNewEventInfo();
    boolean_info_.name                    = info.description;
    boolean_info_.code                    = TEventCode::value;
    boolean_info_.module_id               = info.module_id;
    boolean_info_.attributes["enum_name"] = info.name;
    boolean_info_.attributes["type"]      = "Boolean";
    boolean_info_.attributes["value"]     = std::to_string(value);
    for (auto& [key, value] : attribute.GetAttribute()) {
      boolean_info_.attributes[key] = value;
    }
    boolean_info_.event_content = event_content;
    internal::Report(boolean_info_, call_loc_);
  }

  virtual ~Boolean()
  {
    is_reported_ = true;
  }

 private:
  internal::Event boolean_info_;
  std::source_location call_loc_;
  bool is_reported_ = false;
};

}  // namespace aimrte::trace
