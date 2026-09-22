// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "../context.h"

namespace aimrte::core
{
Context::OpExe::OpExe(Context& ctx, const res::Executor& res, const std::source_location loc)
    : OpBase(ctx, loc), res_(res)
{
  CheckAndInit();
}

Context::OpExe::OpExe(Context& ctx, res::Executor&& res, const std::source_location loc)
    : OpBase(ctx, loc), temp_res_(std::move(res)), res_(temp_res_)
{
  CheckAndInit();
}

void Context::OpExe::CheckAndInit()
{
  ctx_.check(ctx_.id_ == res_.context_id_, loc_)
    .ErrorThrow(
      "Wrong use of res::Executor [{}], current context is [{}], but yours is [{}].",
      res_.name_, ctx_.id_, res_.context_id_);
  executor_ = ctx_.executors_[res_.idx_];
}

aimrt::executor::ExecutorRef Context::OpExe::GetRawRef(const OpExe& ref)
{
  return ref.executor_;
}
}  // namespace aimrte::core
