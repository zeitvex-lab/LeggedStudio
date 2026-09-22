// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/module_base.h"
#include "src/core/core.h"
#include "src/runtime/core/aimrt_core.h"
#include "src/sync/sync.h"
#include <set>

namespace aimrte::test
{
/**
 * @brief 基于 AimRT 的模块测试控制器，可以控制执行阶段停在 AimRT 生命周期的各个地方，
 * 以执行对应流程的测试过程。
 * 其中，生命周期只能往后走，且没法复位重来。
 */
class ModuleTestController
{
  enum class Stage {
    Created,
    Init,
    Start,
    Run,
    Shutdown,
    End
  };

 public:
  struct DefaultConfig {
    // 默认执行器的名称
    std::string exe;

    // 默认的单线程执行器的名称
    std::string thread_safe_exe;
  };

  using ModulePtrSet = std::set<std::shared_ptr<aimrt::ModuleBase>>;

 public:
  ModuleTestController();

  AIMRTE_DECLARE_FORBIDDEN_COPY_MOVE(ModuleTestController);

  /**
   * @brief 设置 AimRT 启动用的配置
   */
  void SetConfigContent(std::string cfg_content);

  /**
   * @brief 设置默认的配置，可从 GetDefaultConfig() 获取具体细节
   * @param module_cfg_content 模块所需参数（可选），每个参数两个缩进，但不需要给定模块名称。
   * @code
   *  ModuleTestController ctrl;
   *  ctrl.SetDefaultConfigContent(R"(
   *    my_param1: 3
   *    my_param2:
   *      my_param3: 4
   *      my_param4: [1, 2]
   *  )");
   * @endcode
   */
  void SetDefaultConfigContent(const std::string& module_cfg_content = "");

  /**
   * @brief 注册一个被测模块
   */
  void RegisterModule(std::string name, aimrt::ModuleBase& module);

  /**
   * @brief 注入初始化时执行的过程
   */
  void HookLetInit(std::function<void()> func);

  /**
   * @brief 执行至 Init 阶段，要求配置已经设置
   */
  void LetInit(std::source_location call_loc = std::source_location::current());

  /**
   * @brief 执行至 Start 阶段
   */
  void LetStart(std::source_location call_loc = std::source_location::current());

  /**
   * @brief 执行至 Run 阶段
   */
  void LetRun(std::source_location call_loc = std::source_location::current());

  /**
   * @brief 执行至 Shutdown 阶段
   */
  void LetShutdown(std::source_location call_loc = std::source_location::current());

  /**
   * @brief 执行至所有上下文全部析构。
   */
  void LetEnd(std::source_location call_loc = std::source_location::current());

  /**
   * @brief 如果被初始化过，将自动执行到结束。
   */
  ~ModuleTestController();

 public:
  const aimrt::runtime::core::AimRTCore& GetCore() const;

  aimrt::CoreRef GetCoreRef() const;

  core::Context& GetContext() const;

  std::shared_ptr<core::Context> GetContextPtr() const;

  /**
   * @return 初始化本模块控制器时，预设的一些默认参数
   */
  const DefaultConfig& GetDefaultConfig(std::source_location call_loc = std::source_location::current()) const;

  /**
   * @return 虚拟模块的参数，只能在 Init() 阶段后拿出。
   */
  YAML::Node GetModuleConfigYaml(std::source_location call_loc = std::source_location::current()) const;

 private:
  class Module : public aimrt::ModuleBase
  {
   public:
    /**
     * @return 本虚拟模块的信息
     */
    aimrt::ModuleInfo Info() const noexcept override
    {
      return {.name = "TestModule"};
    }

    /**
     * @brief 执行模块的初始化过程
     */
    bool Initialize(aimrt::CoreRef core) noexcept override;

    /**
     * @brief 执行模块的启动过程
     */
    bool Start() noexcept override;

    /**
     * @brief 执行模块的关闭过程
     */
    void Shutdown() noexcept override;

   public:
    explicit Module(ModuleTestController* ctrl);

   private:
    ModuleTestController* ctrl_ = nullptr;
  };

  /**
   * @brief 抛出一个生命周期调用顺序出错的异常信息
   * @param required_stage 用户要求的阶段
   * @param call_loc 用户调用处信息
   */
  [[noreturn]] void ThrowWrongOrderException(Stage required_stage, std::source_location call_loc) const;

 private:
  // 记录当前执行到 AimRT 生命周期的哪一个阶段
  Stage stage_ = Stage::Created;

  // 用户设置的 AimRT 启动配置
  std::string cfg_content_;

  // 默认的配置，仅调用了 SetDefaultConfigContent() 函数后有效
  std::optional<DefaultConfig> default_config_;

  // 用于存放 AimRT 启动配置的临时文件，测试结束后删除
  std::string temp_cfg_path_;

  // 虚拟的 AimRT 模块
  Module module_;

  // 注册的自定义模块
  std::vector<std::shared_ptr<aimrt::ModuleBase>> custom_modules_;

  // AimRT 核心，用于启动本控制器中唯一的虚拟模块，以模拟 AimRT 运行时环境
  aimrt::runtime::core::AimRTCore core_;

  // 从模块中取到的 AimRT 资源接口，仅 Init 之后有效
  aimrt::CoreRef core_ref_;

  // AimRTe 上下文，仅 Init 之后有效
  std::shared_ptr<core::Context> ctx_ptr_;

  // 执行 AimRT 以及我们的虚拟模块的初始化、启动流程的独立线程
  std::thread aimrt_start_and_init_thread_;

  // 执行 AimRT 以及我们的虚拟模块的关闭流程的独立线程
  std::thread aimrt_shutdown_thread_;

  // 获知我们的虚拟模块生命周期进程的同步条件
  sync::Condition init_begin_, start_begin_, shutdown_begin_;

  // 阻塞 AimRT 生命周期进行的同步条件
  sync::Condition init_done_, start_done_, shutdown_done_;
};
}  // namespace aimrte::test
