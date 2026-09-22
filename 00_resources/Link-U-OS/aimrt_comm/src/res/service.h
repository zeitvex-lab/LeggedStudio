// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "./details/base.h"

namespace aimrte::res
{
template <class TRequest, class TResponse>
class Service : public details::Base
{
 public:
  using RequestType  = TRequest;
  using ResponseType = TResponse;
  using Base::Base;
};
}  // namespace aimrte::res
