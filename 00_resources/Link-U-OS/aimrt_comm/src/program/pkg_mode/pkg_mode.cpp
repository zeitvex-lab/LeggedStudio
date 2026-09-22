// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./pkg_mode.h"
#include "src/program/details/named_module.h"

namespace aimrte::program_details
{
const aimrt_module_base_t* CreateModule(const ModuleCreatorSpan& module_creators, const aimrt_string_view_t name)
{
  const std::string_view module_name_str = aimrt::util::ToStdStringView(name);

  for (const auto& [cur_module_name_str, cur_module_creator] : module_creators) {
    if (module_name_str == cur_module_name_str) {
      const auto* named_module_ptr =
        new NamedModule(
          cur_module_name_str,
          std::unique_ptr<aimrt::ModuleBase>(cur_module_creator()));

      return named_module_ptr->NativeHandle();
    }
  }

  return nullptr;
}

void DestroyModule(const aimrt_module_base_t* module_ptr)
{
  delete static_cast<aimrt::ModuleBase*>(module_ptr->impl);
}
}  // namespace aimrte::program_details
