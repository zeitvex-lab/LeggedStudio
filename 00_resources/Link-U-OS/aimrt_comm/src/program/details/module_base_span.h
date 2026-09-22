// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/module_base.h"
#include <span>

namespace aimrte::program_details
{
using ModuleCreatorSpan = std::span<const std::tuple<std::string_view, aimrt::ModuleBase* (*)()>>;
}
