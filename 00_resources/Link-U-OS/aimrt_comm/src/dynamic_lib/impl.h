// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <functional>
#include <string>

namespace aimrte
{
class DynamicLib
{
  template <class TSignature>
  struct FunctionTrait;

  template <class TRes, class... TArgs>
  struct FunctionTrait<TRes(TArgs...)> {
    static std::function<TRes(TArgs...)> Create(void* func)
    {
      typedef TRes (*Functor)(TArgs...);

      return (Functor)func;
    }
  };

 public:
  ~DynamicLib();

  /**
   * @brief 加载指定路径（可以是相对路径）的动态库
   */
  bool Load(std::string name);

  /**
   * @brief 卸载已经加载的动态库
   */
  void Unload();

  /**
   * @brief 是否加载了动态库
   */
  bool IsLoaded();

  /**
   * @return 打开本动态库给定的名称
   */
  [[nodiscard]] const std::string& GetName() const;

  /**
   * @return 本动态库的绝对路径
   */
  [[nodiscard]] const std::string& GetFullPath() const;

  /**
   * @brief 创建指定名、指定签名的函数
   * @return 加载的函数（对签名不进行检查）；若找不到指定名字的函数，则返回空
   */
  template <class TSignature>
  std::function<TSignature> f(const std::string& func_name)
  {
    return FunctionTrait<TSignature>::Create(GetSymbol(func_name));
  }

 private:
  /**
   * @brief 加载指定名称的符号
   */
  void* GetSymbol(const std::string& symbol_name);

 private:
  void* handle_{nullptr};
  std::string name_;
  std::string full_path_;
};
}  // namespace aimrte
