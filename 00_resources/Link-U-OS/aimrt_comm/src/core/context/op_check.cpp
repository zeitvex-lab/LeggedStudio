// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "../context.h"

namespace aimrte::core
{
Context::OpCheck::OpCheck(Context& ctx, const bool con, const std::source_location loc)
    : OpBase(ctx, loc), con_(con)
{
}
}  // namespace aimrte::core
