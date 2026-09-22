// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./module_test_controller.h"
#include <fmt/format.h>
#include <fstream>

template <>
struct fmt::formatter<std::source_location, char> : formatter<std::string_view> {
  template <class FmtContext>
  static typename FmtContext::iterator format(const std::source_location call_loc, FmtContext& ctx)
  {
    return ::fmt::format_to(
      ctx.out(),
      R"(
in: {}
at: line {}, column {}
of: {}
)",
      call_loc.function_name(), call_loc.line(), call_loc.column(), call_loc.file_name());
  }
};

namespace aimrte::test
{
ModuleTestController::ModuleTestController()
    : module_(this)
{
}

void ModuleTestController::SetConfigContent(std::string cfg_content)
{
  cfg_content_    = std::move(cfg_content);
  default_config_ = {};
}

void ModuleTestController::SetDefaultConfigContent(const std::string& module_cfg_content)
{
  std::string cfg_content = R"yaml(
aimrt:
  configurator:
    temp_cfg_path: ./cfg/tmp # 生成的临时模块配置文件存放路径
  log: # log配置
    core_lvl: Fatal # 内核日志等级，可选项：Trace/Debug/Info/Warn/Error/Fatal/Off，不区分大小写
    default_module_lvl: Fatal # 模块默认日志等级
    backends: # 日志backends
      - type: console # 控制台日志
        options:
          color: true # 是否彩色打印
  executor: # 执行器配置
    executors: # 当前先支持thread型，未来可根据加载的网络模块提供更多类型
      - name: work_thread_pool # 线程池
        type: asio_thread
        options:
          thread_num: 5 # 线程数，不指定则默认单线程
      - name: thread_safe_work_thread_pool # 线程池
        type: asio_thread
  channel: # 消息队列相关配置
    backends: # 消息队列后端配置
      - type: local # 本地消息队列配置
        options:
          subscriber_use_inline_executor: false # 订阅端是否使用inline执行器
          subscriber_executor: work_thread_pool # 订阅端回调的执行器，仅在subscriber_use_inline_executor=false时生效
  rpc:
    backends:
      - type: local
    clients_options:
      - func_name: "(.*)"
        enable_backends: [local]
    servers_options:
      - func_name: "(.*)"
        enable_backends: [local]
)yaml";

  if (not module_cfg_content.empty())
    cfg_content += "TestModule:\n" + module_cfg_content;

  SetConfigContent(std::move(cfg_content));

  default_config_ = DefaultConfig{
    .exe             = "work_thread_pool",
    .thread_safe_exe = "thread_safe_work_thread_pool",
  };
}

void ModuleTestController::RegisterModule(std::string name, aimrt::ModuleBase& module)
{
  class CustomModule : public aimrt::ModuleBase
  {
   public:
    std::string name;
    ModuleBase* module_ptr = nullptr;

    aimrt::ModuleInfo Info() const override
    {
      return {name};
    }

    bool Initialize(aimrt::CoreRef core) override
    {
      return module_ptr->Initialize(core);
    }

    bool Start() override
    {
      return module_ptr->Start();
    }

    void Shutdown() override
    {
      module_ptr->Shutdown();
    }
  };

  auto ptr        = std::make_shared<CustomModule>();
  ptr->name       = std::move(name);
  ptr->module_ptr = &module;

  core_.GetModuleManager().RegisterModule(custom_modules_.emplace_back(std::move(ptr))->NativeHandle());
}

void ModuleTestController::HookLetInit(std::function<void()> func)
{
  core_.RegisterHookFunc(
    aimrt::runtime::core::AimRTCore::State::kPostInitModules,
    [this, func{std::move(func)}]() {
      this->ctx_ptr_->LetMe();
      func();
    });
}

void ModuleTestController::LetInit(const std::source_location call_loc)
{
  switch (stage_) {
    case Stage::Created:
      break;
    case Stage::Init:
      return;
    default:
      ThrowWrongOrderException(Stage::Init, call_loc);
  }

  stage_ = Stage::Init;

  // 准备临时配置文件，供 AimRT 加载
  temp_cfg_path_ = "./temp_test_module_cfg.yaml";

  std::ofstream temp_cfg_file(temp_cfg_path_);
  temp_cfg_file << cfg_content_;
  temp_cfg_file.close();

  // 注册我们的虚拟模块
  core_.GetModuleManager().RegisterModule(module_.NativeHandle());

  // 启动 AimRT 线程
  aimrt_start_and_init_thread_ = std::thread(
    [this] {
      core_.Initialize({.cfg_file_path = temp_cfg_path_});
      core_.Start();
    });

  // 确保我们的模块进入初始化阶段
  init_begin_.Wait();

  // 准备 AimRTe 模块内全局上下文
  core::details::g_thread_ctx = {ctx_ptr_->weak_from_this()};
}

void ModuleTestController::LetStart(const std::source_location call_loc)
{
  switch (stage_) {
    case Stage::Created: {
      LetInit(call_loc);
      [[fallthrough]];
    }
    case Stage::Init:
      break;
    case Stage::Start:
      return;
    default:
      ThrowWrongOrderException(Stage::Start, call_loc);
  }

  stage_ = Stage::Start;

  // 让初始化流程结束
  init_done_.Satisfy();

  // 确保我们的模块进入启动阶段
  start_begin_.Wait();
}

void ModuleTestController::LetRun(const std::source_location call_loc)
{
  switch (stage_) {
    case Stage::Created: {
      LetInit(call_loc);
      [[fallthrough]];
    }
    case Stage::Init: {
      LetStart(call_loc);
      [[fallthrough]];
    }
    case Stage::Start:
      break;
    case Stage::Run:
      return;
    default:
      ThrowWrongOrderException(Stage::Run, call_loc);
  }

  stage_ = Stage::Run;

  // 让启动流程结束
  start_done_.Satisfy();

  // 确保 AimRT 完全进入运行状态
  while (core_.GetState() != aimrt::runtime::core::AimRTCore::State::kPostStart or
         core_.GetMainThreadExecutor().GetState() != aimrt::runtime::core::executor::MainThreadExecutor::State::kStart)
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
}

void ModuleTestController::LetShutdown(const std::source_location call_loc)
{
  switch (stage_) {
    case Stage::Created: {
      LetInit(call_loc);
      [[fallthrough]];
    }
    case Stage::Init: {
      LetStart(call_loc);
      [[fallthrough]];
    }
    case Stage::Start: {
      LetRun(call_loc);
      [[fallthrough]];
    }
    case Stage::Run:
      break;
    case Stage::Shutdown:
      return;
    default:
      ThrowWrongOrderException(Stage::Shutdown, call_loc);
  }

  stage_ = Stage::Shutdown;

  // 启动 AimRT 关闭流程，让模块进入 shutdown 过程
  aimrt_shutdown_thread_ = std::thread(
    [this] {
      core_.Shutdown();
    });

  // 确保我们的模块进入关闭阶段
  shutdown_begin_.Wait();
}

void ModuleTestController::LetEnd(const std::source_location call_loc)
{
  switch (stage_) {
    case Stage::Created: {
      LetInit(call_loc);
      [[fallthrough]];
    }
    case Stage::Init: {
      LetStart(call_loc);
      [[fallthrough]];
    }
    case Stage::Start: {
      LetRun(call_loc);
      [[fallthrough]];
    }
    case Stage::Run: {
      LetShutdown(call_loc);
      [[fallthrough]];
    }
    case Stage::Shutdown:
      break;
    case Stage::End:
      return;
    default:
      std::terminate();
  }

  stage_ = Stage::End;

  // 让关闭流程结束
  shutdown_done_.Satisfy();

  // 确保 AimRT 的线程都退出
  if (aimrt_start_and_init_thread_.joinable())
    aimrt_start_and_init_thread_.join();

  if (aimrt_shutdown_thread_.joinable())
    aimrt_shutdown_thread_.join();

  // 回收上下文资源
  core_ref_                   = {};
  ctx_ptr_                    = {};
  core::details::g_thread_ctx = {};

  // 删除临时的配置文件
  std::filesystem::remove(temp_cfg_path_);
}

ModuleTestController::~ModuleTestController()
{
  if (stage_ != Stage::Created)
    LetEnd();
}

const aimrt::runtime::core::AimRTCore& ModuleTestController::GetCore() const
{
  return core_;
}

aimrt::CoreRef ModuleTestController::GetCoreRef() const
{
  return core_ref_;
}

core::Context& ModuleTestController::GetContext() const
{
  return *ctx_ptr_;
}

std::shared_ptr<core::Context> ModuleTestController::GetContextPtr() const
{
  return ctx_ptr_;
}

const ModuleTestController::DefaultConfig& ModuleTestController::GetDefaultConfig(const std::source_location call_loc) const
{
  if (not default_config_.has_value()) {
    throw std::logic_error(::fmt::format("TEST ERROR: CANNOT get default config without setting it ! {}", call_loc));
  }

  return default_config_.value();
}

YAML::Node ModuleTestController::GetModuleConfigYaml(const std::source_location call_loc) const
{
  auto throw_get_error = [&](const std::string_view& stage_name) {
    throw std::logic_error(
      ::fmt::format("TEST ERROR: CANNOT get module config at {} stage ! {}", stage_name, call_loc));
  };

  if (stage_ == Stage::Created)
    throw_get_error("Created");

  if (stage_ == Stage::End)
    throw_get_error("End");

  const aimrt::configurator::ConfiguratorRef configurator_ref = core_ref_.GetConfigurator();
  if (not configurator_ref)
    throw std::runtime_error("TEST ERROR: FAIL to get configurator from CoreRef !");

  try {
    return YAML::LoadFile(std::string(configurator_ref.GetConfigFilePath()));
  } catch (const std::exception& ec) {
    ctx_ptr_->log(call_loc).Warn("Fail to get module yaml config, error = {}", ec.what());
    return {};
  }
}

void ModuleTestController::ThrowWrongOrderException(
  const Stage required_stage, const std::source_location call_loc) const
{
  static auto NameOf = [](Stage value) -> std::string_view {
    switch (value) {
      case Stage::Created:
        return "Created";
      case Stage::Init:
        return "Init";
      case Stage::Start:
        return "Start";
      case Stage::Run:
        return "Run";
      case Stage::Shutdown:
        return "Shutdown";
      case Stage::End:
        return "End";
      default:
        return "UNKNOWN";
    }
  };

  throw std::logic_error(
    ::fmt::format("wrong order of stages, now is {}, but you require {} ! {}", NameOf(stage_), NameOf(required_stage), call_loc));
}
}  // namespace aimrte::test

namespace aimrte::test
{
bool ModuleTestController::Module::Initialize(aimrt::CoreRef core) noexcept
{
  ctrl_->core_ref_ = core;
  ctrl_->ctx_ptr_  = std::make_shared<core::Context>(core);

  ctrl_->init_begin_.Satisfy();
  ctrl_->init_done_.Wait();
  return true;
}

bool ModuleTestController::Module::Start() noexcept
{
  ctrl_->start_begin_.Satisfy();
  ctrl_->start_done_.Wait();
  return true;
}

void ModuleTestController::Module::Shutdown() noexcept
{
  ctrl_->shutdown_begin_.Satisfy();
  ctrl_->shutdown_done_.Wait();
}

ModuleTestController::Module::Module(ModuleTestController* ctrl)
    : ctrl_(ctrl)
{
}
}  // namespace aimrte::test
