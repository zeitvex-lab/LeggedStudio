// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.


#include "./context_resource_manager.h"

namespace aimrte::ctx
{
void ContextResourceManager::Prepare(std::shared_ptr<core::Context> ctx_ptr, aimrt::ModuleInfo module_info)
{
  ctx_ptr_     = std::move(ctx_ptr);
  module_info_ = std::move(module_info);
}

void ContextResourceManager::AddInitializer(std::function<void()> func)
{
  initializers_.push_back(std::move(func));
}

void ContextResourceManager::Initialize()
{
  for (std::function<void()>& i : initializers_)
    i();
}
}  // namespace aimrte::ctx
