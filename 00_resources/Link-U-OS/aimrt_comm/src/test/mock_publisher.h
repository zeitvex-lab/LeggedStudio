// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
#include "src/ctx/ctx.h"
#include <gmock/gmock.h>

#include "src/core/mock/i_mock_publisher.h"

namespace aimrte::test
{
template <class T>
class MockPublisher : public core::IMockPublisher<T>
{
 public:
  ctx::Publisher<T> Init()
  {
    return ctx::init::GetCorePtr()->pub().InitMock("/mock/publisher", *this);
  }

  MOCK_METHOD(void, Analyze, (const T& msg), (override));
};
}  // namespace aimrte::test
