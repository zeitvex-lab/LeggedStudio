// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <any>
#include <rfl/yaml.hpp>
#include <source_location>
#include <sstream>
#include <vector>

#include "src/interface/aimrt_module_c_interface/logger/logger_base.h"
#include "src/interface/aimrt_module_cpp_interface/co/schedule.h"
#include "src/interface/aimrt_module_cpp_interface/co/sync_wait.h"
#include "src/interface/aimrt_module_cpp_interface/core.h"
#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_tools.h"
#include "src/interface/aimrt_module_cpp_interface/co/aimrt_context.h"
#include "src/interface/aimrt_module_cpp_interface/co/async_scope.h"
#include "src/macro/macro.h"
#include "src/panic/panic.h"
#include "src/res/res.h"
#include "./coroutine.h"
#include "./details/concepts.h"
#include "./details/type_support.h"
#include "./mock/i_mock_client.h"
#include "./mock/i_mock_publisher.h"
#include "./mock/i_mock_server.h"
#include "./mock/i_mock_subscriber.h"


namespace aimrte::core
{
/**
 * @brief 封装 aimrt::CoreRef ，通过 res 资源标识符，创建、并维护用户可用的
 * 计算资源、通信资源。这些资源仅可以在初始化阶段使用。
 * 除此之外，还提供日志、配置等其他接口。
 *
 * @note 本类仅可以通过 make_shared 创建。
 */
class Context : public std::enable_shared_from_this<Context>
{
  class OpBase;

 public:
  class OpPub;
  class OpSub;
  class OpCli;
  class OpSrv;
  class OpExe;
  class OpLog;
  class OpCheck;
  class OpRaise;

  explicit Context(aimrt::CoreRef core);

  ~Context();

 public:
  OpPub pub(AIMRTE(src(loc))) &;
  OpSub sub(AIMRTE(src(loc))) &;
  OpCli cli(AIMRTE(src(loc))) &;
  OpSrv srv(AIMRTE(src(loc))) &;

  /**
   * @brief 取出指定执行器上下文，以完成在该执行器上的操作（监听、调度协程）。
   * @param res 执行器资源标识符
   */
  [[nodiscard]] OpExe exe(const res::Executor& res, AIMRTE(src(loc))) &;
  [[nodiscard]] OpExe exe(res::Executor&& res, AIMRTE(src(loc))) &;

  /**
   * @return 本模块的日志输出接口
   */
  [[nodiscard]] OpLog log(AIMRTE(src(loc))) &;

  /**
   * @brief 检查给定的条件是否成立，若不成立，则执行后续的操作。
   * @param con 被检查的条件
   * @return 后置动作接口
   */
  [[nodiscard]] OpCheck check(bool con, AIMRTE(src(loc))) &;

  /**
   * @brief 将给定的对象显式转换为 bool 后，判断其是否为 true，若不是，则执行后续操作。
   */
  template <class T>
  [[nodiscard]] OpCheck check(const T& obj, AIMRTE(src(loc))) &;

  /**
   * @return 异常日志记录与抛出接口
   */
  [[nodiscard]] OpRaise raise(AIMRTE(src(loc))) &;

 public:
  /**
   * @brief 根据指定名称，初始化执行器，并返回它的资源标识符。
   * 若指定名称的执行器不存在时，将报错。
   * @param name 执行器名称
   * @return 执行器资源标识符，将在使用执行器时使用。
   */
  [[nodiscard]] res::Executor InitExecutor(const std::string_view& name, AIMRTE(src(loc)));

  /**
   * @brief 使用指定信道资源，发布数据
   * @param ch  信道资源描述符，约定了类型以及对应的发布器，若资源没有正确初始化或使用，将报错
   * @param msg 需要被发送的数据
   * @deprecated 改用 pub().Publish
   */
  template <class T>
  void Publish(const res::Channel<T>& ch, const T& msg, AIMRTE(src(loc)));

  /**
   * @return 获取 Context 中的 AimRT 的 CoreRef
   */
  static aimrt::CoreRef GetRawRef(const Context& ctx);

  /**
   * @return 获取 Context 中的协程生命周期域
   */
  static aimrt::co::AsyncScope& GetAsyncScope(Context& ctx);

 private:
  template <class T>
  using PublishFunction = std::function<void(aimrt::channel::PublisherRef, aimrt::channel::ContextRef, const T&)>;

  template <class T>
  using ChannelCallback = std::function<co::Task<void>(std::shared_ptr<const T>)>;

  template <class T>
  using SubscribeFunction =
    std::function<bool(
      aimrt::channel::SubscriberRef,
      ChannelCallback<T>,
      std::weak_ptr<Context>,
      res::Executor)>;

  struct ChannelContext {
    // 原生的发布器（无论会不会发布，总是会初始化）
    aimrt::channel::PublisherRef pub;

    // 原生的订阅器（无论有没有订阅，总是会初始化）
    aimrt::channel::SubscriberRef sub;

    // 擦除了类型的发送函数（PublishFunction<T>）
    std::any pub_f;

    // 擦除了类型的订阅函数（SubscribeFunction<T>）
    std::any sub_f;
  };

  template <class Q, class P>
  using Client = std::function<
    aimrt::co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q&, P&)>;

  template <class Q, class P>
  using Server = std::function<
    co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q&, P&)>;

  template <class Q, class P>
  using ServerInvoker = std::function<
    aimrt::co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q&, P&, std::any&)>;

  template <class Q, class P>
  using RegisterServerFunction =
    std::function<void(Server<Q, P>, std::weak_ptr<Context>, res::Executor)>;

  struct ServiceContext {
    // 擦除了类型的客户端调用接口（Client<Q, P>）
    std::any call_f;

    // 擦除了类型的服务端处理接口（Server<Q, P>）
    std::any serve_f;

    // 擦除了类型的原生服务端处理接口，用于 Serving() 函数与 DoInitServer() 函数（ServerInvoker<Q, P>）
    std::any server_invoke_f;

    // 擦除了类型的服务器注册接口，目前仅用于配合 mock server
    std::any register_server_f;

    // AimRT 服务回调函数的容器，仅通过本类的 InitServerFunc() 会初始化它
    aimrt::util::Function<aimrt_function_service_func_ops_t> raw_server_holder;

    // 服务方法名称，作为 aimrt 内部 std::string_view 的内容 holder
    std::string func_name;
  };

 private:
  /**
   * @brief 统一的日志处理过程
   * @param level    指定的日志等级
   * @param call_loc 用户操作 Context 最外层接口的调用位置信息
   * @param fmt      消息风格化字符串定义
   * @param args     风格化数据
   */
  template <class... TArgs>
  void Log(
    std::uint32_t level, std::source_location call_loc,
    const fmt::format_string<TArgs...>& fmt,
    TArgs&&... args);

  /**
   * @brief 统一的日志处理与异常抛出的过程
   * @param level    指定的日志等级
   * @param call_loc 用户操作 Context 最外层接口的调用位置信息
   * @param fmt      消息风格化字符串定义
   * @param args     风格化数据
   */
  template <class... TArgs>
  void LogAndThrow(
    std::uint32_t level, std::source_location call_loc,
    const fmt::format_string<TArgs...>& fmt,
    TArgs&&... args);

  /**
   * @brief 检查给定的信道是否合法，并返回该信道的上下文。
   */
  template <class T>
  ChannelContext& GetChannelContext(const res::Channel<T>& ch, std::source_location call_loc);

  /**
   * @brief 检查给定的服务资源是否合法，并返回该服务的上下文。
   */
  template <class Q, class P>
  ServiceContext& GetServiceContext(const res::Service<Q, P>& srv, std::source_location call_loc);

 private:
  // 用于给 Context 分配唯一 id
  static std::atomic_int global_unique_id_;

  // 本 Context 的 id，用于资源匹配检查
  const int id_;

  // AimRT 中为模块提供组件支持的接口（弱引用）
  aimrt::CoreRef core_;

  // 用于创建并管理所有协程的生命周期
  aimrt::co::AsyncScope async_scope_;

  // 申请的执行器资源
  std::vector<aimrt::executor::ExecutorRef> executors_;

  // 发布订阅通信资源上下文
  std::vector<ChannelContext> channel_contexts_;

  // 请求响应通信资源上下文
  std::vector<ServiceContext> service_contexts_;

 public:
  /**
   * @brief 由 AimRTe 集成的各个子系统的上下文，具体内容由子系统注册与使用，
   * 本核心上下文起到全局维护的作用。
   */
  enum class SubContext {
    Undefined,

    // 模块的文件系统管理
    Fs,

    // 健康告警系统
    Hds,

    // 埋点
    Trace,

    // 子系统的数量
    MAX_COUNT_
  };

  template <class TSubContext, class... TArgs>
  TSubContext& InitSubContext(const SubContext id, TArgs&&... args)
  {
    auto raw_ptr = new TSubContext(std::forward<TArgs>(args)...);
    sub_contexts_[static_cast<std::size_t>(id)] =
      std::unique_ptr<TSubContext, SubContextDeleter>(
        raw_ptr,
        [](void* ptr) {
          delete static_cast<TSubContext*>(ptr);
        });
    return *raw_ptr;
  }

  template <class TSubContext>
  TSubContext& GetSubContext(const SubContext id)
  {
    return *static_cast<TSubContext*>(sub_contexts_[static_cast<std::size_t>(id)].get());
  }

  /**
   * @brief 让本线程的上下文对象成为当前的 context 对象。执行器上下文将被清空。
   * @note  本函数仅可在 main 函数 Shutdown 时使用。
   */
  void LetMe();

  /**
   * @return 是否运行
   */
  bool Ok() const;

  /**
   * @brief 要求模块退出，但只设置了标识，供模块子类实现者参考使用
   */
  void RequireToShutdown();

  /**
   * @return 是否启用 trace 功能
   */
  bool EnableTrace() const;

 private:
  using SubContextDeleter = std::function<void(void*)>;

  // 由本核心上下文托管的、所有 AimRTe 子系统的模块上下文信息。
  std::array<std::unique_ptr<void, SubContextDeleter>, static_cast<std::size_t>(SubContext::MAX_COUNT_)> sub_contexts_;

  // 是否被要求关闭。该状态量可以被 ctx 接口获取
  std::atomic_bool is_ok_ = true;

  // 是否被允许启用 trace 功能
  bool enable_trace_ = false;
};
}  // namespace aimrte::core

namespace aimrte::core
{
class Context::OpBase
{
 public:
  OpBase(Context& ctx, std::source_location loc);

 protected:
  Context& ctx_;
  const std::source_location loc_;
};
}  // namespace aimrte::core

#include "./context/op_check.h"
#include "./context/op_cli.h"
#include "./context/op_exe.h"
#include "./context/op_log.h"
#include "./context/op_pub.h"
#include "./context/op_raise.h"
#include "./context/op_srv.h"
#include "./context/op_sub.h"

#include "./context/op_cli.inl"
#include "./context/op_exe.inl"
#include "./context/op_pub.inl"
#include "./context/op_srv.inl"
#include "./context/op_sub.inl"

namespace aimrte::core
{
template <class T>
void Context::Publish(const res::Channel<T>& ch, const T& msg, const std::source_location loc)
{
  pub(loc).Publish(ch, msg);
}

template <class T>
Context::OpCheck Context::check(const T& obj, const std::source_location loc) &
{
  return check(static_cast<bool>(obj), loc);
}

template <class... TArgs>
void Context::Log(
  const std::uint32_t level, const std::source_location call_loc, const fmt::format_string<TArgs...>& fmt,
  TArgs&&... args)
{
  const aimrt::logger::LoggerRef& logger = core_.GetLogger();

  if (level < logger.GetLogLevel())
    return;

  aimrt::common::util::LogImpl(
    logger,
    level,
    call_loc.line(),
    call_loc.file_name(),
    call_loc.function_name(),
    fmt,
    std::forward<TArgs>(args)...);
}

template <class... TArgs>
void Context::LogAndThrow(
  const std::uint32_t level, const std::source_location call_loc, const fmt::format_string<TArgs...>& fmt,
  TArgs&&... args)
{
  // 组装错误信息
  std::string msg = fmt::format(fmt, std::forward<TArgs>(args)...);

  // 日志等级满足时，打印日志
  if (const aimrt::logger::LoggerRef& logger = core_.GetLogger(); level >= logger.GetLogLevel()) {
    logger.Log(
      level,
      call_loc.line(),
      call_loc.file_name(),
      call_loc.function_name(),
      msg.data(),
      msg.length());
  }

  // 将该错误信息抛出
  throw aimrt::common::util::AimRTException(std::move(msg));
}

template <class T>
Context::ChannelContext& Context::GetChannelContext(const res::Channel<T>& ch, const std::source_location call_loc)
{
  check(id_ == ch.context_id_, call_loc).ErrorThrow("Wrong use of res::Channel [{}], current context is [{}], but yours is [{}].", ch.name_, id_, ch.context_id_);

  return channel_contexts_[ch.idx_];
}

template <class Q, class P>
Context::ServiceContext& Context::GetServiceContext(const res::Service<Q, P>& srv, const std::source_location call_loc)
{
  check(id_ == srv.context_id_, call_loc).ErrorThrow("Wrong use of res::Service [{}], current context is [{}], but yours is [{}].", srv.name_, id_, srv.context_id_);

  return service_contexts_[srv.idx_];
}
}  // namespace aimrte::core
