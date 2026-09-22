// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/module_base.h"
#include "src/ctx/ctx.h"
#include <yaml-cpp/yaml.h>

#include "./context_resource_manager.h"
#include "./module_cfg.h"

namespace aimrte::ctx
{
class ModuleBase : public aimrt::ModuleBase
{
 public:
  /**
   * @brief 执行 AimRT 框架启动前的模块配置定义过程
   * @param cfg 进程的配置
   * @param module_name 模块名称
   * @return 由用户进一步定义的模块配置
   */
  ModuleCfg Configure(Cfg& cfg, std::string module_name);

 private:
  aimrt::ModuleInfo Info() const noexcept final;

  bool Initialize(aimrt::CoreRef core) noexcept final;

  bool Start() noexcept final;

  void Shutdown() noexcept final;

 protected:
  virtual void OnConfigure(ModuleCfg& cfg) {}

  virtual bool OnInitialize() = 0;

  virtual bool OnStart() = 0;

  virtual void OnShutdown() = 0;
 protected:
  /**
   * @return AimRTe 上下文数据指针
   */
  [[nodiscard]] std::shared_ptr<core::Context> GetContextPtr() const;

  /**
   * @return AimRT 原生的 CoreRef
   */
  [[nodiscard]] aimrt::CoreRef GetCoreRef() const;

  /**
   * @return 本模块的信息
   */
  [[nodiscard]] aimrt::ModuleInfo GetInfo() const;

  /**
   * @brief 从 AimRT 中读取本模块配置，解析为 yaml 并返回。如果解析或读取失败时，返回 null yaml node.
   */
  [[nodiscard]] YAML::Node GetConfigYaml() const;

  /**
   * @brief 创建、初始化、并维护可以被 core::Context 初始化的资源，
   *        如由 AimRTe 生成的 service 与 service proxy 等。
   * @return 资源的一份拷贝
   */
  template <concepts::ContextResouce T, class... TArgs>
  T Init(TArgs&&... args)
  {
    return ctx_res_manager_.Init<T>(std::forward<TArgs>(args)...);
  }

  /**
   * @brief 初始化指定的资源，并拷贝给指定对象
   */
  template <concepts::ContextResouce T, class... TArgs>
  T& InitFor(T& obj, TArgs&&... args)
  {
    return obj = Init<T>(std::forward<TArgs>(args)...);
  }

 private:
  std::shared_ptr<core::Context> ctx_ptr_;

  // 在模块的生命周期内，维护可被 core::Context 初始化的资源
  ContextResourceManager ctx_res_manager_;

  // 标记本模块是否经历过配置过程，若模块不是由 AimRTe 启动的，它的配置过程需要在初始化过程运行
  bool is_configured = false;
};
}  // namespace aimrte::ctx
