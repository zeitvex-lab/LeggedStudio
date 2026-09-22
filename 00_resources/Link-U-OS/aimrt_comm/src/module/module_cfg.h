// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <functional>
#include <list>
#include <optional>
#include <set>

#include "./cfg.h"
#include "./context_resource_manager.h"

namespace aimrte::ctx
{
class ModuleCfg;
}

namespace aimrte::cfg
{
struct Module {
  enum { Basic };
  enum { Logger };
  enum { Executor };
};

struct {
} constexpr ignore_invalid;
}  // namespace aimrte::cfg

namespace aimrte::ctx::cfg_details
{
class BasicPart;
class LoggerPart;
class ExecutorPart;
class ChPart;
class RpcPart;

/**
 * @brief 模块配置的标签操作接口汇总，通过 [运算符] 与级联调用，来给模块进行配置。
 */
class Session
{
 public:
  BasicPart operator[](decltype(cfg::Module::Basic));

  LoggerPart operator[](decltype(cfg::Module::Logger));

  ExecutorPart operator[](decltype(cfg::Module::Executor));

  ChPart operator[](cfg::Ch methods);

  RpcPart operator[](cfg::Rpc methods);

 protected:
  explicit Session(ModuleCfg* cfg);

 protected:
  ModuleCfg* cfg_ = nullptr;
};

/**
 * @brief 模块基础信息的配置接口
 */
class BasicPart : public Session
{
 public:
  explicit BasicPart(ModuleCfg* cfg);

 public:
  /**
   * @brief 启用本模块
   */
  BasicPart& Enable(bool value = true);

  /**
   * @brief 不启用本模块
   */
  BasicPart& Disable(bool value = true);

  /**
   * @brief 使用反射，读取本模块配置到给定结构体对象
   */
  template <class T>
  BasicPart& Config(T& obj);

  /**
   * @brief 使用给定 yaml 节点进行反射，读取到指定结构体对象中。
   *        用户可以使用 Cfg 对象的 GetConfigYaml() 获取配置对象、访问其子节点，再进行子结构反射。
   */
  template <class T>
  BasicPart& Config(YAML::Node node, T& obj);
};

/**
 * @brief 模块的日志配置接口
 */
class LoggerPart : public Session
{
 public:
  explicit LoggerPart(ModuleCfg* cfg);

 public:
  /**
   * @brief 设置本模块的日志等级
   */
  LoggerPart& Level(cfg::LogLevel value);

  /**
   * @brief 设置本模块的日志等级为全局默认等级
   */
  LoggerPart& UseDefaultLevel();
};

/**
 * @brief 模块的执行器声明接口，具体的定义在进程级别的配置 Cfg 中实现。
 */
class ExecutorPart : public Session
{
 public:
  explicit ExecutorPart(ModuleCfg* cfg);

 public:
  /**
   * @brief 声明本模块需要使用指定名称的执行器，将要求进程层面的配置需要拥有该执行器的配置过程。
   * @param res 绑定的执行器描述符，将在初始化阶段自动初始化它。
   * @param name 指定的名称。
   */
  ExecutorPart& Declare(Executor& res, std::string name);

  /**
   * @brief 与 Declare() 函数类似，但进一步要求执行器是线程安全的。
   */
  ExecutorPart& DeclareThreadSafe(Executor& res, std::string name);

  /**
   * @brief 定义一个执行器，并为其绑定初始化过程。若进程内有别的模块定义同名执行器时，将报错。
   *        使用 "~/" 前缀命名执行器，可以将执行器定义为模块内部私有的执行器，此时将不会有同名问题。
   */
  ExecutorPart& Def(Executor& res, std::string name, std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu = {}, std::string thread_sched_policy = {});

  /**
   * @brief 与 Def() 函数类似，但进一步要求执行器是线程安全的。
   */
  ExecutorPart& DefThreadSafe(Executor& res, std::string name, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy = {});

  /**
   * @brief 与 Def() 函数类似，但使用执行器的默认构造配置进行初始化
   */
  ExecutorPart& Def(Executor& res, std::string name);

  /**
   * @brief 与 DefThreadSafe() 函数类似，但使用执行器的默认构造配置进行初始化
   */
  ExecutorPart& DefThreadSafe(Executor& res, std::string name);

 public:
  ExecutorPart& Declare(Executor& res)
  {
    return Declare(res, res.GetName());
  }

  ExecutorPart& DeclareThreadSafe(Executor& res)
  {
    return DeclareThreadSafe(res, res.GetName());
  }

  ExecutorPart& Def(Executor& res, const std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu = {}, std::string thread_sched_policy = {})
  {
    return Def(res, res.GetName(), thread_num, std::move(thread_bind_cpu), std::move(thread_sched_policy));
  }

  ExecutorPart& DefThreadSafe(Executor& res, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy = {})
  {
    return DefThreadSafe(res, res.GetName(), std::move(thread_bind_cpu), std::move(thread_sched_policy));
  }

  ExecutorPart& Def(Executor& res)
  {
    return Def(res, res.GetName());
  }

  ExecutorPart& DefThreadSafe(Executor& res)
  {
    return DefThreadSafe(res, res.GetName());
  }

  /**
   * @brief 使用反射，Def 给定对象中的所有 exe 对象
   */
  template <class TRes>
  ExecutorPart& Def(TRes& res)
  {
    DefRfl<false>(res);
    return *this;
  }

  /**
   * @brief 使用反射，Def 给定对象中的所有 exe 对象。支持忽略并跳过非 exe 对象的处理。
   */
  template <class TRes>
  ExecutorPart& Def(TRes& res, decltype(cfg::ignore_invalid))
  {
    DefRfl<true>(res);
    return *this;
  }

 private:
  /**
   * @brief 使用反射，Def 给定对象中的所有 exe 对象。
   * @tparam IGNORE_INVALID 是否忽略非 exe 对象字段，如果不忽略，遇到非 exe 对象时将报错。
   */
  template <bool IGNORE_INVALID, class T>
  void DefRfl(T& obj);

  /**
   * @brief 处理执行器的声明与初始化绑定
   */
  void DoDeclare(Executor& res, std::string name, bool check_thread_safe);

  /**
   * @brief 处理执行器的定义与初始化绑定
   */
  void DoDef(Executor& res, std::string name, bool check_thread_safe, std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy);

  /**
   * @return 将可能的模块私有执行器名称，替换为进程唯一的全名。
   *         该处理会将形如 "~/my_exe" 替换为 "MyModule/my_exe".
   */
  std::string ReplaceWithFullName(std::string name) const;

  /**
   * @brief 添加指定执行器的初始化器
   */
  void AddInitializer(Executor& res, std::string name, bool check_thread_safe);
};

/**
 * @brief 模块 channel 通信部分的配置接口，将定义本模块使用的 channel 通信资源与通信后端，
 * 若多次定义同名的通信链路，其通信后端将取并集，作为最终的配置结果。
 */
class ChPart : public Session
{
 public:
  ChPart(ModuleCfg* cfg, cfg::Ch methods);

 public:
  /**
   * @brief 配置指定名称的发布端，但不定义初始化过程。
   */
  ChPart& DefPub(std::string name);

  /**
   * @brief 配置指定名称的订阅端，但不定义初始化过程。
   */
  ChPart& DefSub(std::string name);

  /**
   * @brief 定义一个 topic 发布端。
   * @tparam T 用于通信的数据类型，可自动推导。
   */
  template <class T>
  ChPart& Def(ctx::Publisher<T>& res, std::string name);

  /**
   * @brief 定义一个 topic 订阅端。
   * @tparam T 用于通信的数据类型，可自动推导。
   */
  template <class T>
  ChPart& Def(ctx::Subscriber<T>& res, std::string name);

  /**
   * @brief 定义一个自定义类型的 topic 发布端。
   * @tparam TRaw 用于通信的数据类型。
   * @tparam T 自定义的数据类型，可自动推导。
   */
  template <class TRaw, class T>
  ChPart& DefBy(ctx::Publisher<T>& res, std::string name);

  /**
   * @brief 定义一个自定义类型的 topic 订阅端。
   * @tparam TRaw 用于通信的数据类型。
   * @tparam T 自定义的数据类型，可自动推导。
   */
  template <class TRaw, class T>
  ChPart& DefBy(ctx::Subscriber<T>& res, std::string name);

 public:
  /**
   * @brief 根据通信对象的自带的 topic 名称，配置该通信对象。
   * @tparam TRes 支持多种形式的通信对象，包括：
   *   - ctx::Publisher<>, ctx::Subscriber<>，通过 GetName() 函数获取 topic 名；
   *   - 结构体，将自动递归遍历其中的所有受支持的通信对象进一步处理；
   *     若遍历到不受支持的对象时，将报错。
   */
  template <class TRes>
  ChPart& Def(TRes& res)
  {
    DefRfl<false>(res);
    return *this;
  }

  /**
   * @brief 根据通信对象的自带的 topic 名称，配置该通信对象，支持忽略并跳过非通信对象的处理。
   * @tparam TRes 支持多种形式的通信对象，包括：
   *   - ctx::Publisher<>, ctx::Subscriber<>，通过 GetName() 函数获取 topic 名；
   *   - 结构体，将自动递归遍历其中的所有受支持的通信对象进一步处理。
   */
  template <class TRes>
  ChPart& Def(TRes& res, decltype(cfg::ignore_invalid))
  {
    DefRfl<true>(res);
    return *this;
  }

  /**
   * @brief 根据通信对象的自带的 topic 名称，配置该类型自定义的通信对象。
   * @tparam TRaw 用于通信的数据类型。
   * @tparam TRes 支持两种形式的通信对象，ctx::Publisher<>, ctx::Subscriber<>，
   *              将通过 GetName() 函数获取 topic 名。
   */
  template <class TRaw, class TRes>
  ChPart& DefBy(TRes& res)
  {
    return DefBy<TRaw>(res, res.GetName());
  }

 private:
  /**
   * @brief 使用反射，Def 给定对象中的所有 ch 对象。
   * @tparam IGNORE_INVALID 是否忽略非 ch 对象字段，如果不忽略，遇到非 ch 对象时将报错。
   */
  template <bool IGNORE_INVALID, class T>
  void DefRfl(T& obj);

 private:
  cfg::Ch methods_{cfg::Ch::Default};
};

/**
 * @brief 模块 rpc 通信部分的配置接口，将定义本模块使用的 rpc 通信资源与通信后端，
 * 若多次定义同名的通信链路，其通信后端将取并集，作为最终的配置结果。
 */
class RpcPart : public Session
{
 public:
  RpcPart(ModuleCfg* cfg, cfg::Rpc methods);

 public:
  /**
   * @brief 配置指定名称的客户端，但不定义初始化过程。
   */
  RpcPart& DefCli(std::string name);

  /**
   * @brief 配置指定名称的服务端，但不定义初始化过程。
   */
  RpcPart& DefSrv(std::string name);

  /**
   * @brief 定义一个 rpc method 客户端。
   * @tparam Q 用于通信的请求数据类型，可自动推导。
   * @tparam P 用于通信的响应数据类型，可自动推导。
   */
  template <class Q, class P>
  RpcPart& Def(ctx::Client<Q, P>& res, std::string name);

  /**
   * @brief 定义一个 rpc method 服务端。
   * @tparam Q 用于通信的请求数据类型，可自动推导。
   * @tparam P 用于通信的响应数据类型，可自动推导。
   */
  template <class Q, class P>
  RpcPart& Def(ctx::Server<Q, P>& res, std::string name);

  /**
   * @brief 定义一个自定义类型的 rpc method 客户端。
   * @tparam QRaw 用于通信的请求数据类型。
   * @tparam PRaw 用于通信的响应数据类型。
   * @tparam Q 自定义的请求数据类型，可自动推导。
   * @tparam P 自定义的响应数据类型，可自动推导。
   */
  template <class QRaw, class PRaw, class Q, class P>
  RpcPart& DefBy(ctx::Client<Q, P>& res, std::string name);

  /**
   * @brief 定义一个自定义类型的 rpc method 客户端。
   * @tparam QRaw 用于通信的请求数据类型。
   * @tparam PRaw 用于通信的响应数据类型。
   * @tparam Q 自定义的请求数据类型，可自动推导。
   * @tparam P 自定义的响应数据类型，可自动推导。
   */
  template <class QRaw, class PRaw, class Q, class P>
  RpcPart& DefBy(ctx::Server<Q, P>& res, std::string name);

  /**
   * @brief 定义原生 ros srv 客户端，通过 ros srv 类型告知 rclcpp 该 srv 的序列化方式。
   * @tparam RosSrv 由 ros 生成的原生 srv 类型。
   */
  template <class RosSrv>
  RpcPart& DefRosSrv(ctx::Client<typename RosSrv::Request, typename RosSrv::Response>& res, std::string name);

  /**
   * @brief 定义原生 ros srv 服务端，通过 ros srv 类型告知 rclcpp 该 srv 的序列化方式。
   * @tparam RosSrv 由 ros 生成的原生 srv 类型。
   */
  template <class RosSrv>
  RpcPart& DefRosSrv(ctx::Server<typename RosSrv::Request, typename RosSrv::Response>& res, std::string name);

 public:
  /**
   * @brief 根据通信对象的自带的 method 名称，配置该通信对象。
   * @tparam TRes 支持多种形式的通信对象，包括：
   *   - ctx::Client<>, ctx::Server<>，通过 GetName() 函数获取 method 名；
   *   - 结构体，将自动递归遍历其中的所有受支持的通信对象进一步处理；
   *     若遍历到不受支持的对象时，将报错；
   *   - 由 AimRTe 生成的 res::ServiceClass 与 res::ServiceProxyClass.
   */
  template <class TRes>
  RpcPart& Def(TRes& res)
  {
    DefRfl<false>(res);
    return *this;
  }

  /**
   * @brief 根据通信对象的自带的 method 名称，配置该通信对象，支持忽略并跳过非通信对象的处理。
   * @tparam TRes 支持多种形式的通信对象，包括：
   *   - ctx::Client<>, ctx::Server<>，通过 GetName() 函数获取 method 名；
   *   - 结构体，将自动递归遍历其中的所有受支持的通信对象进一步处理；
   *   - 由 AimRTe 生成的 res::ServiceClass 与 res::ServiceProxyClass.
   */
  template <class TRes>
  RpcPart& Def(TRes& res, decltype(cfg::ignore_invalid))
  {
    DefRfl<true>(res);
    return *this;
  }

  /**
   * @brief 根据通信对象的自带的 method 名称，配置该类型自定义的通信对象。
   * @tparam QRaw 用于通信的请求数据类型。
   * @tparam PRaw 用于通信的响应数据类型。
   * @tparam TRes 支持两种形式的通信对象，ctx::Client<>, ctx::Server<>，
   *              将通过 GetName() 函数获取 method 名。
   */
  template <class QRaw, class PRaw, class TRes>
  RpcPart& DefBy(TRes& res)
  {
    return DefBy<QRaw, PRaw>(res, res.GetName());
  }

  /**
   * @brief 根据通信对象的自带的 method 名称，配置该通信对象。
   * @tparam RosSrv 由 ros 生成的原生 srv 类型。
   * @tparam TRes 支持两种形式的通信对象，ctx::Client<>, ctx::Server<>，
   *              将通过 GetName() 函数获取 method 名。
   */
  template <class RosSrv, template <class, class> class TRes>
  RpcPart& DefRosSrv(TRes<typename RosSrv::Request, typename RosSrv::Response>& res)
  {
    return DefRosSrv(res, res.GetName());
  }

  /**
   * @brief 配置由 AimRTe 生成的 res::ServiceClass 与 res::ServiceProxyClass，
   *        但指定 service_name.
   */
  template <class TRes>
  RpcPart& Def(TRes& res, std::string service_name);

 private:
  /**
   * @brief 使用反射，Def 给定对象中的所有 rpc 对象。
   * @tparam IGNORE_INVALID 是否忽略非 rpc 对象字段，如果不忽略，遇到非 rpc 对象时将报错。
   */
  template <bool IGNORE_INVALID, class T>
  void DefRfl(T& obj);

  /**
   * @brief 配置由 AimRT 生成的 rpc service 与 proxy 类型的通信对象
   */
  template <class TRes>
  void DefServiceResource(TRes& obj, std::string service_name = "");

  template <class Q, class P>
  static constexpr bool CheckIfAreDirectlySupportedTypes();

 private:
  cfg::Rpc methods_{cfg::Rpc::Default};
};
}  // namespace aimrte::ctx::cfg_details

namespace aimrte::ctx
{
/**
 * @brief 模块启动配置的设置器。
 * @code
 *  void OnConfig(ModuleCfg& setting) {
 *    using namespace aimrte::cfg;
 *
 *    // 自定义结构体类型的、记录了模块配置项的对象
 *    MyConfigClass config;
 *
 *    setting
 *    [Module::Basic]
 *    .Enable()
 *    .Config(config) // 读取模块配置
 *
 *    [Module::Logger]
 *    .Level(LogLevel::Warn)
 *
 *    [Module::Executor]
 *    .Delcare(my_executor, config.my_executor_name)
 *
 *    [Ch::ros2]
 *    .Def(my_pub, config.my_topic_name)
 *    .Def(my_sub, "/my/topic/name")
 *
 *    [Rpc::Ros | Rpc::Mqtt]
 *    .Def(my_srv, "/my/service/name")
 *    .Def(my_servce_class_obj)
 *    ;
 *  }
 * @endcode
 */
class ModuleCfg : public cfg_details::Session
{
 public:
  ModuleCfg(Cfg* process_cfg, ContextResourceManager* resource_manager, std::string module_name);

  // 由 Cfg::Processor 处理模块配置信息，将这些信息与进程配置信息融合
  friend class Cfg::Processor;

  // 给予配置接口直接修改本类内容的权限
  friend cfg_details::BasicPart;
  friend cfg_details::LoggerPart;
  friend cfg_details::ExecutorPart;
  friend cfg_details::ChPart;
  friend cfg_details::RpcPart;

  /**
   * @return 获取模块 yaml 配置，该配置可以被索引修改
   */
  YAML::Node Yaml();

  /**
   * @brief 使用反射，读取本模块配置，并设置到给定结构体对象中，
   *        同时使用默认操作初始化该对象中的所有资源。
   */
  template <class T>
  void ConfigAndDefineByDefault(T& obj);

  /**
   * @brief 基于给定的 yaml 配置节点进行反射。
   *        用户可以调用 GetConfigYaml() 并获取其中的子节点，再传递给本函数的 node 参数，进行子结构反射。
   */
  template <class T>
  void ConfigAndDefineByDefault(YAML::Node node, T& obj);

 private:
  // 本进程的配置对象，用于获取进程层面，为本模块的预先设置的参数
  Cfg* process_cfg_ = nullptr;

  // 用于注册模块资源的管理器
  ContextResourceManager* resource_manager_ = nullptr;

 private:
  // 模块的配置
  cfg::details::ModuleConfig config_;

  // 通过本配置对象设置的通信链路信息，将被用于构造通信白名单及其使用的后端（取并集）
  std::list<cfg::details::ChConfig> pubs_, subs_;
  std::list<cfg::details::RpcConfig> clis_, srvs_;

  // 通过本配置对象设置的所需执行器名称集合，将在进程层面的配置阶段进行检查，要求所有执行器得到定义
  std::list<cfg::details::ExeConfig> exes_;
};

template <class T>
void ModuleCfg::ConfigAndDefineByDefault(T& obj)
{
  ConfigAndDefineByDefault(Yaml(), obj);
}

template <class T>
void ModuleCfg::ConfigAndDefineByDefault(YAML::Node node, T& obj)
{
  (*this)
    [cfg::Module::Basic]
      .Config(node, obj)
        [cfg::Ch::Default]
      .Def(obj, cfg::ignore_invalid)
        [cfg::Rpc::Default]
      .Def(obj, cfg::ignore_invalid)
        [cfg::Module::Executor]
      .Def(obj, cfg::ignore_invalid);
}
}  // namespace aimrte::ctx

namespace aimrte::ctx::cfg_details
{
template <class T>
BasicPart& BasicPart::Config(T& obj)
{
  Config(cfg_->Yaml(), obj);
  return *this;
}

template <class T>
BasicPart& BasicPart::Config(YAML::Node node, T& obj)
{
  // 从预设的配置中读取用户参数，若有字段缺失的，将使用该对象的字段值
  Cfg::GetModuleConfig(node, obj);

  // 将读取后的对象反写回总配置中
  Cfg::SetModuleConfig(node, obj);
  return *this;
}

template <bool IGNORE_INVALID, class T>
void ExecutorPart::DefRfl(T& obj)
{
  if constexpr (std::is_class_v<T> and std::is_aggregate_v<T>) {
    // 递归对嵌套类型进行处理
    std::apply(
      [this](auto&&... fields_ptr) {
        (DefRfl<IGNORE_INVALID>(*fields_ptr), ...);
      },
      rfl::to_view(obj).values());
  } else if constexpr (std::is_same_v<std::remove_cvref_t<T>, Executor>) {
    Def(obj);
  } else {
    static_assert(IGNORE_INVALID, "The object to def has field that is no exe ! may be use Def(obj, aimrte::cfg::ignore_invalid) ?");
  }
}

template <class T>
ChPart& ChPart::Def(ctx::Publisher<T>& res, std::string name)
{
  if constexpr (core::concepts::DirectlySupportedType<T>) {
    res::details::Base::SetName(res, std::move(name));
    DefPub(res.GetName());

    cfg_->resource_manager_->AddInitializer(
      [&res, name{res.GetName()}]() {
        res = init::Publisher<T>(name);
      });
  } else {
    DefBy<typename convert::For<T>::AnotherType>(res, std::move(name));
  }

  return *this;
}

template <class T>
ChPart& ChPart::Def(ctx::Subscriber<T>& res, std::string name)
{
  if constexpr (core::concepts::DirectlySupportedType<T>) {
    res::details::Base::SetName(res, std::move(name));
    DefSub(res.GetName());

    cfg_->resource_manager_->AddInitializer(
      [&res, name{res.GetName()}]() {
        res = init::Subscriber<T>(name);
      });
  } else {
    DefBy<typename convert::For<T>::AnotherType>(res, std::move(name));
  }

  return *this;
}

template <class TRaw, class T>
ChPart& ChPart::DefBy(ctx::Publisher<T>& res, std::string name)
{
  res::details::Base::SetName(res, std::move(name));
  DefPub(res.GetName());

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}]() {
      res = init::Publisher<T, convert::By<TRaw>>(name);
    });

  return *this;
}

template <class TRaw, class T>
ChPart& ChPart::DefBy(ctx::Subscriber<T>& res, std::string name)
{
  res::details::Base::SetName(res, std::move(name));
  DefSub(res.GetName());

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}]() {
      res = init::Subscriber<T, convert::By<TRaw>>(name);
    });

  return *this;
}

namespace details
{
template <class T>
struct IsCh
    : std::bool_constant<false> {
};

template <class T>
struct IsCh<T&>
    : IsCh<std::remove_cvref_t<T>> {
};

template <class T>
struct IsCh<ctx::Publisher<T>>
    : std::bool_constant<true> {
};

template <class T>
struct IsCh<ctx::Subscriber<T>>
    : std::bool_constant<true> {
};
}  // namespace details

template <bool IGNORE_INVALID, class T>
void ChPart::DefRfl(T& obj)
{
  if constexpr (std::is_class_v<T> and std::is_aggregate_v<T>) {
    // 递归对嵌套类型进行处理
    std::apply(
      [this](auto&&... fields_ptr) {
        (DefRfl<IGNORE_INVALID>(*fields_ptr), ...);
      },
      rfl::to_view(obj).values());
  } else if constexpr (details::IsCh<T>::value) {
    Def(obj, obj.GetName());
  } else {
    static_assert(IGNORE_INVALID, "The object to def has field that is no pub or sub ! may be use Def(obj, aimrte::cfg::ignore_invalid) ?");
  }
}

template <class Q, class P>
RpcPart& RpcPart::Def(ctx::Client<Q, P>& res, std::string name)
{
  if constexpr (CheckIfAreDirectlySupportedTypes<Q, P>) {
    res::details::Base::SetName(res, std::move(name));
    DefCli(core::details::WrapRpcFuncName<Q>(res.GetName()));

    cfg_->resource_manager_->AddInitializer(
      [&res, name{res.GetName()}]() {
        res = init::ClientFunc<Q, P>(name);
      });
  } else {
    DefBy<typename convert::For<Q>::AnotherType, typename convert::For<P>::AnotherType>(res, std::move(name));
  }

  return *this;
}

template <class Q, class P>
RpcPart& RpcPart::Def(ctx::Server<Q, P>& res, std::string name)
{
  if constexpr (CheckIfAreDirectlySupportedTypes<Q, P>) {
    res::details::Base::SetName(res, std::move(name));
    DefSrv(core::details::WrapRpcFuncName<Q>(res.GetName()));

    cfg_->resource_manager_->AddInitializer(
      [&res, name{res.GetName()}]() {
        res = init::ServerFunc<Q, P>(name);
      });
  } else {
    DefBy<typename convert::For<Q>::AnotherType, typename convert::For<P>::AnotherType>(res, std::move(name));
  }

  return *this;
}

template <class QRaw, class PRaw, class Q, class P>
RpcPart& RpcPart::DefBy(ctx::Client<Q, P>& res, std::string name)
{
  res::details::Base::SetName(res, std::move(name));
  DefCli(core::details::WrapRpcFuncName<QRaw>(res.GetName()));

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}]() {
      res = init::ClientFunc<Q, P, convert::By<QRaw>, convert::By<PRaw>>(name);
    });

  return *this;
}

template <class QRaw, class PRaw, class Q, class P>
RpcPart& RpcPart::DefBy(ctx::Server<Q, P>& res, std::string name)
{
  res::details::Base::SetName(res, std::move(name));
  DefSrv(core::details::WrapRpcFuncName<QRaw>(res.GetName()));

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}]() {
      res = init::ServerFunc<Q, P, convert::By<QRaw>, convert::By<PRaw>>(name);
    });

  return *this;
}

template <class RosSrv>
RpcPart& RpcPart::DefRosSrv(ctx::Client<typename RosSrv::Request, typename RosSrv::Response>& res, std::string name)
{
  res::details::Base::SetName(res, std::move(name));
  DefCli(core::details::WrapRpcFuncName<typename RosSrv::Request>(res.GetName()));

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}]() {
      res = init::ClientFunc<typename RosSrv::Request, typename RosSrv::Response, RosSrv>(name);
    });

  return *this;
}

template <class RosSrv>
RpcPart& RpcPart::DefRosSrv(ctx::Server<typename RosSrv::Request, typename RosSrv::Response>& res, std::string name)
{
  res::details::Base::SetName(res, std::move(name));
  DefSrv(core::details::WrapRpcFuncName<typename RosSrv::Request>(res.GetName()));

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}]() {
      res = init::ServerFunc<typename RosSrv::Request, typename RosSrv::Response, RosSrv>(name);
    });

  return *this;
}

template <class TRes>
RpcPart& RpcPart::Def(TRes& res, std::string service_name)
{
  DefServiceResource(res, std::move(service_name));
  return *this;
}

namespace details
{
template <class T>
struct IsRpc
    : std::bool_constant<false> {
};

template <class T>
struct IsRpc<T&>
    : IsCh<std::remove_cvref_t<T>> {
};

template <class Q, class P>
struct IsRpc<ctx::Server<Q, P>>
    : std::bool_constant<true> {
};

template <class Q, class P>
struct IsRpc<ctx::Client<Q, P>>
    : std::bool_constant<true> {
};
}  // namespace details

template <bool IGNORE_INVALID, class T>
void RpcPart::DefRfl(T& obj)
{
  if constexpr (std::is_class_v<T> and std::is_aggregate_v<T>) {
    // 递归对嵌套类型进行处理
    std::apply(
      [this](auto&&... fields_ptr) {
        (DefRfl<IGNORE_INVALID>(*fields_ptr), ...);
      },
      rfl::to_view(obj).values());
  } else if constexpr (details::IsRpc<T>::value) {
    Def(obj, obj.GetName());
  } else if constexpr (concepts::ContextServiceResource<T>) {
    DefServiceResource<T>(obj);
  } else {
    static_assert(IGNORE_INVALID, "The object to def has field that is no cli or srv ! may be use Def(obj, aimrte::cfg::ignore_invalid) ?");
  }
}

template <class TRes>
void RpcPart::DefServiceResource(TRes& obj, std::string service_name)
{
  // 注册一个 service class 里的所有 methods
  for (std::string func_name : TRes::GetMethodNames(service_name)) {
    (TRes::IS_PROXY ? cfg_->clis_ : cfg_->srvs_).push_back({methods_, std::move(func_name)});
  }

  // 添加该 service class 的初始化过程
  cfg_->resource_manager_->AddInitializer(
    [&obj, manager_ptr = cfg_->resource_manager_, service_name{std::move(service_name)}]() {
      obj = manager_ptr->Init<TRes>(service_name);
    });
}

template <class Q, class P>
constexpr bool RpcPart::CheckIfAreDirectlySupportedTypes()
{
  if constexpr (core::concepts::SameDirectlySupportedType<Q, P>)
    return true;
  else {
    static_assert(
      not(core::concepts::DirectlySupportedType<Q> or core::concepts::DirectlySupportedType<P>),
      "Request type and response type must be the same protocol type (both are protobuf or ros) !");
  }

  return false;
}
}  // namespace aimrte::ctx::cfg_details
