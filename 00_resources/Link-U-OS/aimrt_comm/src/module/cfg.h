// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <fmt/format.h>
#include <yaml-cpp/yaml.h>
#include <rfl/yaml.hpp>
#include <string>
#include "src/ctx/ctx.h"
#include "src/macro/macro.h"
#include "src/sys/internal/config.h"

#include "./cfg/ch.h"
#include "./cfg/exe.h"
#include "./cfg/log.h"
#include "./cfg/plugin.h"
#include "./cfg/reflect.h"
#include "./cfg/rpc.h"
#include "./cfg/utils.h"

// 日志、插件、channel、rpc、执行器等不同配置的扩展宏
#define AIMRTE_DETAILS_CFG_LOGGER_INVOKE(_func_) AIMRTE_INVOKE_INDEX(_func_, console, rotate_file, topic_logger)
#define AIMRTE_DETAILS_CFG_PLUGIN_INVOKE(_func_) AIMRTE_INVOKE_INDEX(_func_, ros2, mqtt, net, parameter, log_control, opentelemetry, monitor, zenoh, iceoryx, record_playback, omp, echo, proxy, topic_logger, viz)
#define AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(_func_) AIMRTE_INVOKE_INDEX(_func_, ros2, mqtt, http, tcp, udp, local, monitor, zenoh, iceoryx)
#define AIMRTE_DETAILS_CFG_RPC_INVOKE(_func_) AIMRTE_INVOKE_INDEX(_func_, ros2, mqtt, http, local, monitor, omp, zenoh)
#define AIMRTE_DETAILS_CFG_EXE_INVOKE(_func_) AIMRTE_INVOKE_INDEX(_func_, simple_thread, asio_thread, asio_strand, tbb_thread, time_wheel)

/// 定义 cfg 的各种枚举量
namespace aimrte::cfg
{
#define AIMRTE_DETAILS_IMPL(_idx_, _type_) _type_ = (1 << (_idx_)),

/**
 * @brief channel 通信类型定义
 */
enum class Ch : std::uint64_t {
  Default,
  AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(AIMRTE_DETAILS_IMPL)
};

/**
 * @brief rpc 通信类型定义
 */
enum class Rpc : std::uint64_t {
  Default,
  AIMRTE_DETAILS_CFG_RPC_INVOKE(AIMRTE_DETAILS_IMPL)
};

#undef AIMRTE_DETAILS_IMPL

/**
 * @brief 日志等级
 */
enum class LogLevel {
  Trace,
  Debug,
  Info,
  Warn,
  Error,
  Fatal,
  Off,

  TRACE,
  DEBUG,
  INFO,
  WARN,
  ERROR,
  FATAL,
  OFF,
};

/**
 * @brief 执行器类型定义，每一种的配置均不同
 */
struct Exe {
#define AIMRTE_DETAILS_IMPL(_, _type_) enum { _type_ };
  enum { main_thread };
  enum { guard_thread };
  AIMRTE_DETAILS_CFG_EXE_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL
};

/**
 * @brief 数据过滤器类型
 */
enum class Filter {
  otp_trace,
  otp_simple_trace,
  monitor,
  viz,
};

// 用于导出对应的配置接口
enum { pkg };
enum { module };

Ch operator|(Ch lhs, Ch rhs);
Rpc operator|(Rpc lhs, Rpc rhs);
}  // namespace aimrte::cfg

/**
 * @brief 后端配置项类型，用于设置后端配置
 */
namespace aimrte::cfg::backend
{
#define AIMRTE_DETAILS_IMPL(_, _type_) enum { _type_ };

struct Log {
  AIMRTE_DETAILS_CFG_LOGGER_INVOKE(AIMRTE_DETAILS_IMPL)
};

struct Plugin {
  AIMRTE_DETAILS_CFG_PLUGIN_INVOKE(AIMRTE_DETAILS_IMPL)
};

struct Ch {
  AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(AIMRTE_DETAILS_IMPL)
};

struct Rpc {
  AIMRTE_DETAILS_CFG_RPC_INVOKE(AIMRTE_DETAILS_IMPL)
};

#undef AIMRTE_DETAILS_IMPL
}  // namespace aimrte::cfg::backend

/// 定义日志、通信、执行器、插件等变体类型，以支持在 vector 中存放多种后端配置
namespace aimrte::cfg::details
{
#define AIMRTE_DETAILS_IMPL(_, _type_) , backend::log::_type_
using LogBackend = std::variant<backend::log::meta AIMRTE_DETAILS_CFG_LOGGER_INVOKE(AIMRTE_DETAILS_IMPL)>;
#undef AIMRTE_DETAILS_IMPL

#define AIMRTE_DETAILS_IMPL(_, _type_) , backend::plugin::_type_
using PluginBackend = std::variant<backend::plugin::meta AIMRTE_DETAILS_CFG_PLUGIN_INVOKE(AIMRTE_DETAILS_IMPL)>;
#undef AIMRTE_DETAILS_IMPL

#define AIMRTE_DETAILS_IMPL(_, _type_) , backend::ch::_type_
using ChBackend = std::variant<backend::ch::meta AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(AIMRTE_DETAILS_IMPL)>;
#undef AIMRTE_DETAILS_IMPL

#define AIMRTE_DETAILS_IMPL(_, _type_) , backend::rpc::_type_
using RpcBackend = std::variant<backend::rpc::meta AIMRTE_DETAILS_CFG_RPC_INVOKE(AIMRTE_DETAILS_IMPL)>;
#undef AIMRTE_DETAILS_IMPL

#define AIMRTE_DETAILS_IMPL(_, _type_) , exe::_type_
using ExeBackend = std::variant<exe::meta AIMRTE_DETAILS_CFG_EXE_INVOKE(AIMRTE_DETAILS_IMPL)>;
#undef AIMRTE_DETAILS_IMPL

struct ChConfig {
  Ch methods{Ch::Default};
  std::string name;
};

struct RpcConfig {
  Rpc methods{Rpc::Default};
  std::string name;
};

struct ExeConfig {
  struct Option {
    std::uint32_t thread_num = 1;
    std::vector<std::uint32_t> thread_bind_cpu;
    std::string thread_sched_policy;
  };

  std::string name;
  std::optional<Option> option;
};

/**
 * @brief AimRT pkg 的动态库配置
 */
struct PkgConfig {
  std::string path;
  std::optional<std::vector<std::string>> disable_module;
};

/**
 * @brief AimRT 模块配置
 */
struct ModuleConfig {
  std::string name;
  std::optional<bool> enable;
  std::optional<LogLevel> log_lvl;
  std::optional<std::string> cfg_file_path;
};

/**
 * @brief AimRTe 启动参数配置，部分将传给 AimRTCore
 */
struct CoreConfig {
  std::string cfg_file_path;
  bool dump_cfg_file = false;
  std::string dump_cfg_file_path;
  std::string deployment_file_path;
};

/**
 * @brief 往容器中添加新的 filter
 */
void AddFilter(std::optional<std::vector<Filter>>& filters, Filter filter);
}  // namespace aimrte::cfg::details

namespace aimrte
{
/**
 * @brief AimRTe 进程的配置对象
 *
 * 本配置对象提供多种预设值，包括：
 * 1. 进程名称：
 *   - 用户构造 Cfg 对象时，给定的第三个参数为进程名称；
 *   - 若未给定进程名称参数，将使用 /proc/self/comm + _UNNAMED 作为进程名称。
 *
 * 2. ros2 与 mqtt 插件的 id 参数，默认使用进程名称来表示。
 *
 * 3. 使用 Cfg 的 WithDefaultMqtt() 函数构造默认的 mqtt 配置时，
 *   - 该函数的唯一参数是 broker_ip 地址；
 *   - 该参数具有默认值 127.0.0.1；
 *   - 该默认值可以通过指定 MQTT_BROKER_IP 环境变量覆盖；
 *   - 默认将配置所有 servers allow share，可以通过定义 DISABLE_MQTT_NGINX 环境变量为 false 覆盖。
 *
 * 4. 使用 Cfg 对象时，将自动导入 AimRTe 的 HDS 功能，将：
 *   - 自动配置通过 http 发送 HDS 的异常码；
 *   - 若用户配置了 net 插件、或配置了 http 后端时，Cfg 不会覆盖用户的配置；
 *   - Cfg 默认配置 HDS monitor ip 为 127.0.0.1，可以通过定义 HDS_MONITOR_IP 环境变量覆盖。
 */
class Cfg
{
  template <class Backend, class T>
  class Assign
  {
   public:
    explicit Assign(std::vector<Backend>& backends)
        : backends_(backends)
    {
    }

    void operator=(T value)
    {
      backends_.push_back(std::move(value));
    }

    void operator&=(T value)
    {
      const bool existed =
        cfg::details::Visit<T>(
          backends_,
          [&](T& backend) {
            backend = std::move(value);
          });

      if (not existed)
        backends_.push_back(std::move(value));
    }

    void operator|=(T value)
    {
      const bool existed =
        cfg::details::Visit<T>(backends_, [&](T&) {});

      if (not existed)
        backends_.push_back(std::move(value));
    }

   private:
    std::vector<Backend>& backends_;
  };

  template <class T>
  class SingleAssign
  {
   public:
    explicit SingleAssign(T& value)
        : value_(value)
    {
    }

    void operator=(T value)
    {
      value_ = std::move(value);
    }

   private:
    T& value_;
  };

  template <class Backend, class T>
  class Append
  {
   public:
    explicit Append(std::vector<Backend>& backends)
        : backends_(backends)
    {
    }

    Append& operator+=(T value)
    {
      backends_.push_back(std::move(value));
      return *this;
    }

   private:
    std::vector<Backend>& backends_;
  };

 public:
  /**
   * @brief 使用一组命令行参数来构造本 Cfg 对象
   */
  Cfg(const std::vector<std::string>& vargs, std::string process_name);

  /**
   * @brief 使用 main 函数的启动参数来构造本 Cfg 对象
   */
  Cfg(int argc, char** argv, std::string process_name);

  /**
   * @brief 处理 Cfg 的合并、并产生最终 yaml cfg
   */
  class Processor;

 public:
  /**
   * @brief 导出各种内容（包括日志、插件、通信后端、执行器、模块、包等）的配置接口
   * @tparam Option
   * @return 配置接口
   * @note 往下看各种 WithXXX 接口内的实现，可作为使用例子进行参考
   */
  template <class Option>
  auto operator[](Option)
  {
    if constexpr (false)
      ;
    // log backend config
#define AIMRTE_DETAILS_IMPL(_, _type_) \
  else if constexpr (std::same_as<Option, decltype(cfg::backend::Log::_type_)>) return Assign<cfg::details::LogBackend, cfg::backend::log::_type_>(aimrt_config_.log.backends);

    AIMRTE_DETAILS_CFG_LOGGER_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL

    // ch backend config
#define AIMRTE_DETAILS_IMPL(_, _type_) \
  else if constexpr (std::same_as<Option, decltype(cfg::backend::Ch::_type_)>) return Assign<cfg::details::ChBackend, cfg::backend::ch::_type_>(aimrt_config_.channel.backends);

    AIMRTE_DETAILS_CFG_CHANNEL_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL

    // rpc backend config
#define AIMRTE_DETAILS_IMPL(_, _type_) \
  else if constexpr (std::same_as<Option, decltype(cfg::backend::Rpc::_type_)>) return Assign<cfg::details::RpcBackend, cfg::backend::rpc::_type_>(aimrt_config_.rpc.backends);

    AIMRTE_DETAILS_CFG_RPC_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL

    // plugin config
#define AIMRTE_DETAILS_IMPL(_, _type_) \
  else if constexpr (std::same_as<Option, decltype(cfg::backend::Plugin::_type_)>) return Assign<cfg::details::PluginBackend, cfg::backend::plugin::_type_>(aimrt_config_.plugin.plugins);

    AIMRTE_DETAILS_CFG_PLUGIN_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL

    // main thread config
    else if constexpr (std::same_as<Option, decltype(cfg::Exe::main_thread)>) return SingleAssign(aimrt_config_.main_thread);

    // guard thread config
    else if constexpr (std::same_as<Option, decltype(cfg::Exe::guard_thread)>) return SingleAssign(aimrt_config_.guard_thread);

    // executor config
#define AIMRTE_DETAILS_IMPL(_, _type_) \
  else if constexpr (std::same_as<Option, decltype(cfg::Exe::_type_)>) return Append<cfg::details::ExeBackend, cfg::exe::_type_>(aimrt_config_.executor.executors);

    AIMRTE_DETAILS_CFG_EXE_INVOKE(AIMRTE_DETAILS_IMPL)
#undef AIMRTE_DETAILS_IMPL

    // pkg config
    else if constexpr (std::same_as<Option, decltype(cfg::pkg)>) return Append<cfg::details::PkgConfig, cfg::details::PkgConfig>(aimrt_config_.module.pkgs);

    // module config
    else if constexpr (std::same_as<Option, decltype(cfg::module)>) return Append<cfg::details::ModuleConfig, cfg::details::ModuleConfig>(aimrt_config_.module.modules);

    // SHOULD NEVER REACH HERE !!!
    else static_assert(trait::always_false_v<Option>);
  }

  /**
   * @brief 预设指定模块的参数内容
   */
  template <class T>
  Cfg& SetModuleConfig(const std::string& module_name, const T& obj)
  {
    SetModuleConfig(modules_config_[module_name], obj);
    return *this;
  }

  /**
   * @brief 读取指定模块的参数内容
   */
  template <class T>
  Cfg& GetModuleConfig(const std::string& module_name, T& obj)
  {
    GetModuleConfig(GetModuleConfigYaml(module_name), obj);
    return *this;
  }

  template <class T>
  static void SetModuleConfig(YAML::Node res, const T& obj)
  {
    if constexpr (std::same_as<T, YAML::Node>)
      res = obj;
    else
      res = YAML::Load(rfl::yaml::write(obj));
  }

  template <class T>
  static void GetModuleConfig(const YAML::Node& ext, T& obj)
  {
    YAML::Node res = YAML::Load(rfl::yaml::write(obj));
    cfg::details::MergeMapNode(res, ext);
    obj = rfl::yaml::read<T>(Dump(res)).value();
  }

  /**
   * @brief 从用户给定的程序启动参数中，获取指定模块的 yaml 配置
   */
  YAML::Node GetModuleConfigYaml(const std::string& module_name) const;

  /**
   * @brief 获取本模块配置的索引，对该配置节点的修改，都将反馈到模块配置上
   */
  YAML::Node GetMutableModuleConfigYaml(const std::string& module_name);

  /**
   * @brief 设置默认的模块日志等级
   */
  Cfg& SetDefaultLogLevel(cfg::LogLevel level);

  /**
   * @brief 设置框架的日志等级
   */
  Cfg& SetCoreLogLevel(cfg::LogLevel level);

  /**
   * @brief 获取当前进程在deployment.yaml中的配置信息
   * @return 当前进程在deployment.yaml中的配置节点
   */
  YAML::Node GetModuleDeploymentInfo() const;

  /**
   * @brief 获取网络插件的配置选项
   * @return 网络插件的配置选项对象
   */
  cfg::backend::plugin::net::Options GetNetworkPluginOptions() const;

 public:
  static constexpr auto DEFAULT_TIMEOUT_EXECUTOR   = "default_timeout_executor";
  static constexpr auto DEFAULT_TIMEOUT_TIME_WHEEL = "default_timeout_time_wheel";
  static constexpr auto DEFAULT_SM_EXECUTOR        = "default_sm_executor";

  /**
   * @brief 使用默认的日志器配置
   * @note 只能调用一次
   */
  Cfg& WithDefaultLogger()
  {
    (*this)[cfg::backend::Log::console] |= {};

    if (sys::config::EnableFileLogger())
      (*this)[cfg::backend::Log::rotate_file] |= {};

    if (sys::config::EnableTopicLogger()) {
      TryAddTopicLogger();
    }
    return *this;
  }

  void TryAddTopicLogger()
  {
    for (cfg::details::PluginBackend& i : aimrt_config_.plugin.plugins) {
      if (trait::get_index<cfg::backend::plugin::topic_logger, decltype(i)>::value == i.index()) {
        return;
      }
    }

    const auto LOG_TOPIC = "/aima/log/module_log";
    (*this)[cfg::backend::Plugin::topic_logger] |= {};
    (*this)[cfg::backend::Log::topic_logger] |= {
      .options = {
        .topic_name          = LOG_TOPIC,
        .timer_executor_name = DEFAULT_TIMEOUT_TIME_WHEEL,
        .interval_ms         = 100,
        .max_msg_size        = SIZE_MAX,
      },
    };
    TryAddDefaultTimeoutExecutor();

    WithDefaultRos();
    aimrt_config_.channel.pub_topics_options.insert(aimrt_config_.channel.pub_topics_options.begin(), {LOG_TOPIC, {cfg::Ch::ros2}});
  }

  /**
   * @brief 使用默认的 local 通信配置
   * @note 只能调用一次
   */
  Cfg& WithDefaultLocal()
  {
    (*this)[cfg::backend::Ch::local] |= {};
    (*this)[cfg::backend::Rpc::local] |= {};
    return *this;
  }

  /**
   * @brief 添加默认的、用于处理 timeout 事件的执行器与时间轮
   * @note 调用其他 WithDefault 函数、且会用到 timeout executor 的，将会尝试调用本函数。
   *       用户可以不再需要显式调用本函数。
   */
  Cfg& WithDefaultTimeoutExecutor();

  /**
   * @brief 添加默认的 ros 后端
   * @note 可以调用多次
   */
  Cfg& WithDefaultRos()
  {
    for (cfg::details::PluginBackend& i : aimrt_config_.plugin.plugins) {
      if (trait::get_index<cfg::backend::plugin::ros2, decltype(i)>::value == i.index()) {
        return *this;
      }
    }

    (*this)[cfg::backend::Plugin::ros2] |= {};
    (*this)[cfg::backend::Ch::ros2] |= {};
    (*this)[cfg::backend::Rpc::ros2] |= {
      .options = {{
        .timeout_executor = DEFAULT_TIMEOUT_TIME_WHEEL,
      }},
    };

    TryAddDefaultTimeoutExecutor();
    return *this;
  }

  /**
   * @brief 添加默认的 mqtt 后端，需要配置 WithDefaultTimeoutExecutor()
   * @note 只能调用一次
   */
  Cfg& WithDefaultMqtt(const std::string& broker_ip = utils::Env("MQTT_BROKER_IP", "127.0.0.1"))
  {
    (*this)[cfg::backend::Plugin::mqtt] |= {
      .options = {
        .broker_addr    = ::fmt::format("tcp://{}:1883", broker_ip),
        .max_pkg_size_k = 10240,
      },
    };
    (*this)[cfg::backend::Ch::mqtt] |= {};
    (*this)[cfg::backend::Rpc::mqtt] |= {
      .options = {{
        .timeout_executor = DEFAULT_TIMEOUT_TIME_WHEEL,
      }},
    };

    TryAddDefaultTimeoutExecutor();
    return *this;
  }

  /**
   * @brief 添加默认的 zenoh 支持
   * @note 只能调用一次
   */
  Cfg& WithDefaultZenoh()
  {
    (*this)[cfg::backend::Plugin::zenoh] |= {};
    (*this)[cfg::backend::Ch::zenoh] |= {};
    (*this)[cfg::backend::Rpc::zenoh] |= {
      .options = {{
        .timeout_executor = DEFAULT_TIMEOUT_TIME_WHEEL,
      }},
    };

    TryAddDefaultTimeoutExecutor();
    return *this;
  }

  /**
   * @brief 添加默认的 iceoryx 支持
   * @note 只能调用一次
   */
  Cfg& WithDefaultIceoryx()
  {
    (*this)[cfg::backend::Plugin::iceoryx] |= {};
    (*this)[cfg::backend::Ch::iceoryx] |= {};
    return *this;
  }

 public:
  /**
   * @brief 添加默认的 recode playback 订阅主题
   */
  Cfg& SetBackendTopic(const std::string& method, const std::string& topic_name, const std::vector<cfg::Ch>& enable_backends);

 private:
  /**
   * @brief 尝试向本 cfg 对象添加默认的 timeout executor，会在多个默认 WithDefault 函数中使用
   */
  void TryAddDefaultTimeoutExecutor();

 private:
  /**
   * @brief 执行本类的构造过程
   */
  void Construct(int argc, char** argv, std::string process_name);

 private:
  // 进程名称
  std::string process_name_;

  // 提供给 AimRTCore 的配置参数
  cfg::details::CoreConfig core_;

  // AimRT 进程配置
  struct {
    struct {
      std::string temp_cfg_path;  // 默认初值为本进程的临时目录
    } configurator;

    struct {
      cfg::LogLevel core_lvl{cfg::LogLevel::Info};
      cfg::LogLevel default_module_lvl{cfg::LogLevel::Info};
      std::vector<cfg::details::LogBackend> backends;
    } log;

    struct {
      std::vector<cfg::details::PluginBackend> plugins;
    } plugin;

    struct {
      struct PubOption {
        std::string topic_name;
        std::vector<cfg::Ch> enable_backends;
        std::optional<std::vector<cfg::Filter>> enable_filters;
      };
      using SubOption = PubOption;

      std::vector<cfg::details::ChBackend> backends;
      std::vector<PubOption> pub_topics_options;
      std::vector<SubOption> sub_topics_options;

      void AddPubFilter(const cfg::Filter filter)
      {
        for (PubOption& i : pub_topics_options)
          cfg::details::AddFilter(i.enable_filters, filter);
      }

      void AddSubFilter(const cfg::Filter filter)
      {
        for (PubOption& i : sub_topics_options)
          cfg::details::AddFilter(i.enable_filters, filter);
      }

      void AddFilter(const cfg::Filter filter)
      {
        AddPubFilter(filter);
        AddSubFilter(filter);
      }
    } channel;

    struct {
      struct CliOption {
        std::string func_name;
        std::vector<cfg::Rpc> enable_backends;
        std::optional<std::vector<cfg::Filter>> enable_filters;
      };
      using SrvOption = CliOption;

      std::vector<cfg::details::RpcBackend> backends;
      std::vector<CliOption> clients_options;
      std::vector<SrvOption> servers_options;

      void AddClientFilter(const cfg::Filter filter)
      {
        for (CliOption& i : clients_options)
          cfg::details::AddFilter(i.enable_filters, filter);
      }

      void AddServerFilter(const cfg::Filter filter)
      {
        for (CliOption& i : servers_options)
          cfg::details::AddFilter(i.enable_filters, filter);
      }

      void AddFilter(const cfg::Filter filter)
      {
        AddClientFilter(filter);
        AddServerFilter(filter);
      }
    } rpc;

    void AddFilter(const cfg::Filter filter)
    {
      channel.AddFilter(filter);
      rpc.AddFilter(filter);
    }

    cfg::exe::main_thread main_thread;
    cfg::exe::guard_thread guard_thread;

    struct {
      std::vector<cfg::details::ExeBackend> executors;
    } executor;

    struct {
      std::vector<cfg::details::PkgConfig> pkgs;
      std::vector<cfg::details::ModuleConfig> modules;
    } module;
  } aimrt_config_;

  // 模块的配置，需要通过 SetConfig() 进行设置
  YAML::Node modules_config_;
};
}  // namespace aimrte
