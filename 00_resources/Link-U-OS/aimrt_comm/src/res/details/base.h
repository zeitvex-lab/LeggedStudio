// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>

namespace aimrte::core
{
class Context;
}

namespace aimrte::res::details
{
/**
 * @brief 资源标识的基类，记录了所有资源都有的名称与索引。
 */
class Base
{
 public:
  Base() = default;

  explicit Base(std::string name)
      : name_(std::move(name))
  {
  }

 public:
  [[nodiscard]] bool IsValid() const
  {
    return idx_ != static_cast<std::size_t>(-1) and context_id_ != -1;
  }

  [[nodiscard]] const std::string& GetName() const
  {
    return name_;
  }

 private:
  friend class core::Context;

 private:
  // 资源名称
  std::string name_;

  // 由 core::Context 管理的资源索引，用于加速访问
  std::size_t idx_ = -1;

  // 所属 core::Context 的索引，用于资源误用检查
  int context_id_ = -1;

 public:
  static void SetName(Base& obj, std::string name)
  {
    obj.name_ = std::move(name);
  }
};
}  // namespace aimrte::res::details
