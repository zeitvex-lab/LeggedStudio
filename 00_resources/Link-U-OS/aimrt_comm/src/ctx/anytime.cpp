// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./anytime.h"
#include "src/panic/panic.h"
#include "src/sys/internal/fs.h"
#include <filesystem>
#include "./details/fs.h"

namespace aimrte::ctx
{
core::Context::OpLog log(const std::source_location call_loc)
{
  return core::details::ExpectContext(call_loc)->log(call_loc);
}

core::Context::OpCheck check(const bool con, const std::source_location call_loc)
{
  return core::details::ExpectContext(call_loc)->check(con, call_loc);
}

core::Context::OpRaise raise(const std::source_location call_loc)
{
  return core::details::ExpectContext(call_loc)->raise(call_loc);
}

static details::Fs& GetFs(const std::source_location call_loc)
{
  return core::details::ExpectContext(call_loc)->GetSubContext<details::Fs>(core::Context::SubContext::Fs);
}

const std::filesystem::path& GetDataPath(const std::source_location call_loc)
{
  return GetFs(call_loc).GetData();
}

const std::filesystem::path& GetParamPath(const std::source_location call_loc)
{
  return GetFs(call_loc).GetParam();
}

const std::filesystem::path& GetTempPath(const std::source_location call_loc)
{
  return GetFs(call_loc).GetTemp();
}

bool Ok(const std::source_location call_loc)
{
  return core::details::ExpectContext(call_loc)->Ok();
}
}  // namespace aimrte::ctx
