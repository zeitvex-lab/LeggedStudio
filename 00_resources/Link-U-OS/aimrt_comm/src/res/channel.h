// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "./details/base.h"

namespace aimrte::res
{
template <class T>
class Channel : public details::Base
{
 public:
  using MessageType = T;
  using Base::Base;
};
}  // namespace aimrte::res
