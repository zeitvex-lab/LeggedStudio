// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./impl.h"
#include <dlfcn.h>
#include <filesystem>
#include <stdexcept>

namespace aimrte
{
DynamicLib::~DynamicLib()
{
  Unload();
}

bool DynamicLib::Load(std::string name)
{
  Unload();

  name_   = std::move(name);
  handle_ = dlopen(name_.data(), RTLD_NOW | RTLD_LOCAL);

  if (nullptr == handle_)
    return false;

  char buf[2024];
  dlinfo(handle_, RTLD_DI_ORIGIN, &buf);
  full_path_ = canonical(std::filesystem::path(buf) / name_).string();

  return true;
}

void DynamicLib::Unload()
{
  if (nullptr == handle_)
    return;

  if (dlclose(handle_) != 0)
    return;

  handle_ = nullptr;
}

bool DynamicLib::IsLoaded()
{
  return handle_ != nullptr;
}

const std::string& DynamicLib::GetName() const
{
  return name_;
}

const std::string& DynamicLib::GetFullPath() const
{
  return full_path_;
}

void* DynamicLib::GetSymbol(const std::string& symbol_name)
{
  if (nullptr == handle_)
    throw std::runtime_error("DynamicLib does not load any lib.");

  return dlsym(handle_, symbol_name.data());
}
}  // namespace aimrte
