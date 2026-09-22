// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
#include "src/ctx/ctx.h"
#include <gmock/gmock.h>

#include "src/core/mock/i_mock_server.h"

namespace aimrte::test
{
template <class Q, class P>
class MockServer : public core::IMockServer<Q, P>
{
 public:
  ctx::Server<Q, P> Init()
  {
    return ctx::init::GetCorePtr()->srv().InitMock("/mock/server", *this);
  }

  MOCK_METHOD(void, OnNullServerError, (), (override));
  MOCK_METHOD(void, Analyze, (const aimrt::rpc::ContextRef& rpc_ctx, const Q& q, const P& p, const aimrt::rpc::Status& ret), (override));
  MOCK_METHOD(void, AnalyzeAsync, (const aimrt::rpc::ContextRef& rpc_ctx, const Q& q, const P& p, const aimrt::rpc::Status& ret), (override));
};
}  // namespace aimrte::test
