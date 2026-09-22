// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
#include "src/ctx/ctx.h"
#include <gmock/gmock.h>

#include "src/core/mock/i_mock_subscriber.h"

namespace aimrte::test
{
template <class T>
class MockSubscriber : public core::IMockSubscriber<T>
{
 public:
  ctx::Subscriber<T> Init()
  {
    return ctx::init::GetCorePtr()->sub().InitMock("/mock/subcriber", *this);
  }

  MOCK_METHOD(void, OnNullSubscriberError, (), (override));
  MOCK_METHOD(void, AnalyzeAsync, (), (override));
};
}  // namespace aimrte::test
