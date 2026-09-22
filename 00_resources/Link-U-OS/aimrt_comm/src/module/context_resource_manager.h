// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/ctx/ctx.h"
#include <unordered_map>

namespace aimrte::ctx::concepts
{
/**
 * @brief 可以用 aimrte::core::Context 初始化的资源对象
 */
template <class T>
concept ContextResouce =
  requires(T& obj, const std::shared_ptr<core::Context>& ctx_ptr) {
    {
      obj.Init(ctx_ptr)
      } -> std::same_as<void>;
  };

/**
 * @brief aimrte 生成的 rpc 协议类型对象
 */
template <class T>
concept ContextServiceResource =
  requires {
    requires ContextResouce<T>;
    {
      T::GetMethodNames()
      } -> std::same_as<std::vector<std::string>>;
  };
}  // namespace aimrte::ctx::concepts

namespace aimrte::ctx
{
/**
 * @brief 模块的 aimrte::core::Context 关联资源的维护器，负责初始化它们、并持有它们。
 */
class ContextResourceManager
{
 public:
  /**
   * @brief 使用模块的信息来初始化本管理器
   */
  void Prepare(std::shared_ptr<core::Context> ctx_ptr, aimrt::ModuleInfo module_info);

  /**
   * @brief 新建、初始化并维护指定的模块上下文相关的资源
   */
  template <concepts::ContextResouce T>
  T Init(std::string_view extra_name = {})
  {
    const std::string id = fmt::format("{}({})", typeid(T).name(), extra_name);

    // 同一种类型的资源不允许初始化两次
    ctx::check(not ctx_res_.contains(id))
      .ErrorThrow("Module [{}] has already initialize resource [{}] !", module_info_.name, id);

    // 创建新的该类型资源
    auto ptr = std::make_unique<T>();

    // 执行初始化
    ptr->Init(ctx_ptr_, std::string(extra_name));

    // 暂记该引用，随后返回
    T& res = *ptr;

    // 在模块生命周期内维护该对象
    ctx_res_[id] = std::move(ptr);

    // 拷贝该资源描述并返回
    return res;
  }

  /**
   * @brief 添加一个在初始化阶段执行的任务
   */
  void AddInitializer(std::function<void()> func);

  /**
   * @brief 逐一执行所有的初始化任务
   */
  void Initialize();

 private:
  struct ResourceDeleter {
    std::function<void(void* ptr)> func;

    template <class T>
    ResourceDeleter& operator=(std::default_delete<T>&& deleter)
    {
      func = [deleter{std::move(deleter)}](void* ptr) {
        deleter(static_cast<T*>(ptr));
      };

      return *this;
    }

    void operator()(void* ptr) const
    {
      func(ptr);
    }
  };

 private:
  // 模块的上下文信息
  std::shared_ptr<core::Context> ctx_ptr_;

  // 模块信息，仅用于打印
  aimrt::ModuleInfo module_info_;

  // 按类型 hash code 维护的资源
  std::unordered_map<std::string, std::unique_ptr<void, ResourceDeleter>> ctx_res_;

  // 资源初始化过程列表，在配置阶段定义的资源，将在初始化阶段初始化。
  // 我们将捕获用户传入的资源描述对象，并为其初始化，因此要求这些资源对象的生命周期至少和模块的等同。
  // 在阅读相关代码时，会看到在 lambda 里重新构造一个 name，而不是用 res.GetName() 来获得资源名称，
  // 这是为了避免 res 在函数外被重新初始化，在初始化阶段执行该 lamda 时，res.GetName() 无效。
  std::list<std::function<void()>> initializers_;
};
}  // namespace aimrte::ctx
