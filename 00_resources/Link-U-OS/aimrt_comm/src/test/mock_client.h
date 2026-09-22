// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
#include "src/ctx/ctx.h"
#include <gmock/gmock.h>

#include "src/core/mock/i_mock_client.h"

namespace aimrte::test
{
template <class Q, class P>
class MockClient : public core::IMockClient<Q, P>
{
 public:
  ctx::Client<Q, P> Init()
  {
    return ctx::init::GetCorePtr()->cli().InitMock("/mock/client", *this);
  }

  MOCK_METHOD(void, AnalyzeAndFeedback, (const aimrt::rpc::ContextRef& rpc_ctx, const Q& q, P& p, aimrt::rpc::Status& ret), (override));
};
}  // namespace aimrte::test
