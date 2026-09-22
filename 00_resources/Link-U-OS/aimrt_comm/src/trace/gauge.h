// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include <source_location>
#include <string>
#include "./internal/reporter.h"

namespace aimrte::trace
{

template <typename TEventCode, typename TValue>
class Gauge
{
 public:
  explicit Gauge(std::source_location call_loc = std::source_location::current()) : call_loc_(call_loc)
  {
    const auto info                     = TEventCode::GetInfo();
    gauge_info_                         = internal::GetNewEventInfo();
    gauge_info_.name                    = info.description;
    gauge_info_.code                    = TEventCode::value;
    gauge_info_.module_id               = info.module_id;
    gauge_info_.attributes["enum_name"] = info.name;
    gauge_info_.attributes["type"]      = "Gauge";
    gauge_info_.event_content           = "";
  }

  explicit Gauge(TEventCode::Attribute attribute, std::string_view event_content = "", std::source_location call_loc = std::source_location::current()) : call_loc_(call_loc)
  {
    const auto info                     = TEventCode::GetInfo();
    gauge_info_                         = internal::GetNewEventInfo();
    gauge_info_.name                    = info.description;
    gauge_info_.code                    = TEventCode::value;
    gauge_info_.module_id               = info.module_id;
    gauge_info_.attributes["enum_name"] = info.name;
    gauge_info_.attributes["type"]      = "Gauge";
    for (auto& [key, value] : attribute.GetAttribute()) {
      gauge_info_.attributes[key] = value;
    }
    gauge_info_.event_content = event_content;
  }

  virtual ~Gauge()
  {
    is_reported_ = true;
  }

  /**
   * @brief 小于阈值时上报
   *
   * @param value 当前值
   * @param threshold 阈值
   * @return Gauge&
   */
  Gauge& LessThan(TValue value, TValue threshold, std::string_view event_content = "")
  {
    if (value < threshold) {
      gauge_info_.attributes["value"]      = std::to_string(value);
      gauge_info_.attributes["threshold"]  = std::to_string(threshold);
      gauge_info_.attributes["comparison"] = "less_than";
      gauge_info_.event_content            = event_content;
      internal::Report(gauge_info_, call_loc_);
    }
    return *this;
  }

  /**
   * @brief 大于阈值时上报
   *
   * @param value 当前值
   * @param threshold 阈值
   * @return Gauge&
   */
  Gauge& GreaterThan(TValue value, TValue threshold, std::string_view event_content = "")
  {
    if (value > threshold) {
      gauge_info_.attributes["value"]      = std::to_string(value);
      gauge_info_.attributes["threshold"]  = std::to_string(threshold);
      gauge_info_.attributes["comparison"] = "greater_than";
      gauge_info_.event_content            = event_content;
      internal::Report(gauge_info_, call_loc_);
    }
    return *this;
  }

  /**
   * @brief 等于阈值时上报
   *
   * @param value 当前值
   * @param threshold 阈值
   * @return Gauge&
   */
  Gauge& EqualTo(TValue value, TValue threshold, std::string_view event_content = "")
  {
    if (value == threshold) {
      gauge_info_.attributes["value"]      = std::to_string(value);
      gauge_info_.attributes["threshold"]  = std::to_string(threshold);
      gauge_info_.attributes["comparison"] = "equal_to";
      gauge_info_.event_content            = event_content;
      internal::Report(gauge_info_, call_loc_);
    }
    return *this;
  }

  /**
   * @brief 直接上报value
   *
   * @param value 当前值
   */
  void Value(TValue value)
  {
    gauge_info_.attributes["value"]      = std::to_string(value);
    gauge_info_.attributes["comparison"] = "value_for";
    internal::Report(gauge_info_, call_loc_);
  }

 private:
  internal::Event gauge_info_;
  std::source_location call_loc_;
  bool is_reported_ = false;
};

}  // namespace aimrte::trace
