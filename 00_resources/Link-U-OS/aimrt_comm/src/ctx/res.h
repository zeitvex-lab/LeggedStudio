// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/res/res.h"
#include "./anytime.h"
#include "./init_op.h"
#include "./run.h"

#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_tools.h"

namespace aimrte::ctx
{
/**
 * @brief 对 res::Executor 的操作接口封装。
 */
class Executor : public res::Executor
{
  struct WhenInitOperator {
   public:
    /**
     * @brief 在当前执行器上，注册指定的信道资源的消息回调。
     * @param ch       信道资源标识符
     * @param callback 回调函数或协程，参数为 std::shared_ptr<T> 或 const T&
     */
    template <class T, core::concepts::SupportedSubscriber<T> TCallback>
    const WhenInitOperator& Subscribe(const res::Channel<T>& ch, TCallback callback, AIMRTE(src(loc))) const
    {
      ctx::init::exe(this_).Subscribe(ch, std::move(callback), loc);
      return *this;
    }

    /**
     * @brief 在当前执行器上，注册指定服务资源的服务处理回调。
     * @tparam Q 请求数据类型
     * @tparam P 响应数据类型
     * @param srv    服务资源标识符
     * @param server 服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
     *               (const Q &, P &)，返回 rpc::Status.
     */
    template <class Q, class P, core::concepts::SupportedServer<Q, P> TServer>
    const WhenInitOperator& Serve(const res::Service<Q, P>& srv, TServer server, AIMRTE(src(loc))) const
    {
      ctx::init::exe(this_).Serve(srv, std::move(server), loc);
      return *this;
    }

   private:
    friend class Executor;

    explicit WhenInitOperator(const Executor& impl)
        : this_(impl)
    {
    }

    const Executor& this_;
  };

 public:
  /**
   * @brief 准备使用只有 init 阶段可以使用的接口
   */
  auto WhenInit() const
  {
    return WhenInitOperator{*this};
  }

  /**
   * @brief 在本执行器中，执行给定函数或协程
   */
  template <core::concepts::SupportedInvoker F>
  const Executor& Post(F f, AIMRTE(src(loc))) const
  {
    ctx::exe(*this, loc).Post(std::move(f));
    return *this;
  }

  /**
   * @brief 在本执行器中，执行给定函数或协程
   * @param scope 协程的生命周期将由该 scope 管理
   */
  template <core::concepts::SupportedInvoker F>
  const Executor& Post(aimrt::co::AsyncScope& scope, F f, AIMRTE(src(loc))) const
  {
    ctx::exe(*this, loc).Post(scope, std::move(f));
    return *this;
  }

  /**
   * @brief 在本执行器中，原地执行完给定函数或协程
   */
  template <core::concepts::SupportedInvoker F>
  const Executor& Inline(F&& f, AIMRTE(src(loc))) const
  {
    ctx::exe(*this, loc).Inline(std::forward<F>(f));
    return *this;
  }

  /**
   * @brief 检查本执行器是否是线程安全的
   */
  bool ThreadSafe(AIMRTE(src(loc))) const;

 public:
  Executor() = default;

  explicit Executor(std::string name);

  Executor(std::string name, std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu = {}, std::string thread_sched_policy = {});

  Executor(res::Executor&& res);

  Executor(const res::Executor& res);

  Executor& operator=(const Executor& other);

 private:
  struct Option {
    std::uint32_t thread_num = 1;
    std::vector<std::uint32_t> thread_bind_cpu;
    std::string thread_sched_policy;
  };

  // 用于配合 cfg 接口，定义模块内部执行器的默认配置，不代表执行器的真实配置
  std::optional<Option> option_;

  // 是否仅覆盖名称，不要覆盖 option，用于和 cfg 反射配合。用户配置不会反射 option
  bool no_copy_option_{false};

 public:
  static std::optional<Option> GetOption(const Executor& exe);
  static Executor CreateDeclaration(std::string name);
};

/**
 * @brief 对 res::Channel<T> 的数据发送相关的操作接口封装
 */
template <class T>
class Publisher : public res::Channel<T>
{
 public:
  /**
   * @brief 基于当前的上下文信息，通过本发布器资源通道发布数据。
   */
  void Publish(const T& msg, AIMRTE(src(loc))) const
  {
    ctx::Publish(*this, msg, loc);
  }

  const Publisher& operator<<(const T& msg) const
  {
    Publish(msg);
    return *this;
  }

  friend void operator>>(const T& msg, const Publisher& res)
  {
    res.Publish(msg);
  }

  void operator()(const T& msg, AIMRTE(src(loc))) const
  {
    Publish(msg, loc);
  }

 public:
  Publisher() = default;
  using res::Channel<T>::Channel;

  Publisher(res::Channel<T>&& res)
      : res::Channel<T>(std::move(res))
  {
  }

  Publisher(const res::Channel<T>& res)
      : res::Channel<T>(res)
  {
  }
};

/**
 * @brief 对 res::Channel<T> 的数据监听相关的操作接口封装
 */
template <class T>
class Subscriber : public res::Channel<T>
{
  struct WhenInitOperator {
   public:
    /**
     * @brief 注册本信道资源的消息回调，该回调发生在原生通信系统的回调中。
     * @param callback 回调函数或协程，参数为 std::shared_ptr<T> 或 const T&，
     *                 将在原生通信的回调中执行，请勿编写过重的内容。
     */
    template <core::concepts::SupportedSubscriber<T> TCallback>
    void SubscribeInline(TCallback callback, AIMRTE(src(loc))) const
    {
      ctx::init::SubscribeInline(this_, std::move(callback), loc);
    }

    /**
     * @brief 在指定执行器上，注册本信道资源的消息回调。
     * @param callback 回调函数或协程，参数为 std::shared_ptr<T> 或 const T&
     */
    template <core::concepts::SupportedSubscriber<T> TCallback>
    void SubscribeOn(
      const res::Executor& exe, TCallback callback, AIMRTE(src(loc))) const
    {
      ctx::init::exe(exe, loc).Subscribe(this_, std::move(callback));
    }

   private:
    friend class Subscriber;

    explicit WhenInitOperator(const Subscriber& impl)
        : this_(impl)
    {
    }

    const Subscriber& this_;
  };

 public:
  /**
   * @brief 准备使用只有 init 阶段可以使用的接口
   */
  auto WhenInit() const
  {
    return WhenInitOperator{*this};
  }

 public:
  Subscriber() = default;
  using res::Channel<T>::Channel;

  Subscriber(res::Channel<T>&& res)
      : res::Channel<T>(std::move(res))
  {
  }

  Subscriber(const res::Channel<T>& res)
      : res::Channel<T>(res)
  {
  }
};

/**
 * @brief 对 res::Service<Q, P> 的调用操作接口封装
 */
template <class Q, class P>
class Client : public res::Service<Q, P>
{
 public:
  using ClientRequest  = Q;
  using ClientResponse = P;
  /**
   * @brief 使用本服务资源，发起远程调用。
   * @param q 请求数据
   * @param p 响应数据
   * @return 服务处理结果
   */
  [[nodiscard]] co::Task<aimrt::rpc::Status> Call(const Q& q, P& p, AIMRTE(src(loc))) const
  {
    return ctx::Call(*this, q, p, loc);
  }

  [[nodiscard]] co::Task<aimrt::rpc::Status> operator()(const Q& q, P& p, AIMRTE(src(loc))) const
  {
    return Call(q, p, loc);
  }

  [[nodiscard]] co::Task<std::optional<P>> Call(const Q& q, AIMRTE(src(loc))) const
  {
    P p;
    if (const aimrt::rpc::Status status = co_await Call(q, p, loc); status.OK())
      co_return p;

    co_return {};
  }

  [[nodiscard]] co::Task<std::optional<P>> operator()(const Q& q, AIMRTE(src(loc))) const
  {
    return Call(q, loc);
  }

  /**
   * @brief 与上一个接口类似，但可指定服务调用的相关配置（如超时等）。
   */
  [[nodiscard]] co::Task<aimrt::rpc::Status> Call(
    aimrt::rpc::ContextRef ctx, const Q& q, P& p, AIMRTE(src(loc))) const
  {
    return ctx::Call(*this, ctx, q, p, loc);
  }

  [[nodiscard]] co::Task<aimrt::rpc::Status> operator()(
    aimrt::rpc::ContextRef ctx, const Q& q, P& p, AIMRTE(src(loc))) const
  {
    return Call(std::move(ctx), q, p, loc);
  }

  [[nodiscard]] co::Task<std::optional<P>> Call(
    aimrt::rpc::ContextRef ctx, const Q& q, AIMRTE(src(loc))) const
  {
    P p;
    if (const aimrt::rpc::Status status = co_await Call(std::move(ctx), q, p, loc); status.OK())
      co_return p;

    co_return {};
  }

  [[nodiscard]] co::Task<std::optional<P>> operator()(
    aimrt::rpc::ContextRef ctx, const Q& q, AIMRTE(src(loc))) const
  {
    return Call(std::move(ctx), q, loc);
  }

 public:
  Client() = default;
  using res::Service<Q, P>::Service;

  Client(res::Service<Q, P>&& res)
      : res::Service<Q, P>(std::move(res))
  {
  }

  Client(const res::Service<Q, P>& res)
      : res::Service<Q, P>(res)
  {
  }
};

template <class Q, class P>
class Server : public res::Service<Q, P>
{
  struct WhenInitOperator {
   public:
    /**
     * @brief 注册本服务资源的服务处理回调，该回调发生在原生通信系统的回调中。
     * @param server  服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
     *                (const Q &, P &)，返回 rpc::Status.
     *                该处理器将在原生通信的回调中执行，请勿编写过重的内容。
     */
    template <core::concepts::SupportedServer<Q, P> TServer>
    void ServeInline(TServer server, AIMRTE(src(loc))) const
    {
      ctx::init::ServeInline(this_, std::move(server), loc);
    }

    /**
     * @brief 在指定执行器上，注册指定服务资源的服务处理回调。
     * @param exe    指定的执行器资源描述符
     * @param server 服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
     *               (const Q &, P &)，返回 rpc::Status.
     */
    template <core::concepts::SupportedServer<Q, P> TServer>
    void ServeOn(const res::Executor& exe, TServer server, AIMRTE(src(loc))) const
    {
      ctx::init::exe(exe, loc).Serve(this_, std::move(server));
    }

   private:
    friend class Server;

    explicit WhenInitOperator(const Server& impl)
        : this_(impl)
    {
    }

    const Server& this_;
  };

 public:
  /**
   * @brief 准备使用只有 init 阶段可以使用的接口
   */
  auto WhenInit() const
  {
    return WhenInitOperator{*this};
  }

 public:
  Server() = default;
  using res::Service<Q, P>::Service;

  Server(res::Service<Q, P>&& res)
      : res::Service<Q, P>(std::move(res))
  {
  }

  Server(const res::Service<Q, P>& res)
      : res::Service<Q, P>(res)
  {
  }
};

template <class Q, class P>
class Nginx
{
 public:
  using NginxRequest  = Q;
  using NginxResponse = P;

  struct WhenInitOperator {
   public:
    /**
     * @brief 注册本服务资源的服务处理回调，该回调发生在原生通信系统的回调中。
     * @param server  服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
     *                (const Q &, P &)，返回 rpc::Status.
     *                该处理器将在原生通信的回调中执行，请勿编写过重的内容。
     */
    template <core::concepts::SupportedServer<Q, P> TServer>
    void ServeInline(TServer server, AIMRTE(src(loc)))
    {
      ctx::init::ServeInline(this_.srv_, std::move(server), loc);
      this_.is_served_ = true;
    }

    /**
     * @brief 在指定执行器上，注册指定服务资源的服务处理回调。
     * @param exe    指定的执行器资源描述符
     * @param server 服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
     *               (const Q &, P &)，返回 rpc::Status.
     */
    template <core::concepts::SupportedServer<Q, P> TServer>
    void ServeOn(const res::Executor& exe, TServer server, AIMRTE(src(loc)))
    {
      ctx::init::exe(exe, loc).Serve(this_.srv_, std::move(server));
      this_.is_served_ = true;
    }

    void NoServe()
    {
      this_.is_served_ = true;
    }

    void ServeDefaultInline(uint64_t timeout = 20 * 1000, AIMRTE(src(loc)))
    {
      if (this_.is_served_)
        return;

      ServeInline(
        [cli{this_.cli_}, timeout, func_name{this_.GetName()}](const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
          aimrt::rpc::Context ctx;
          ctx.SetTimeout(std::chrono::milliseconds(timeout));

          auto id   = aimrte::utils::GenerateUniqueID();
          auto json = aimrt::Pb2CompactJson(q);
          AIMRTE_INFO("Request To RpcFunc: [{}][{}] req: {} [ServeDefaultInline]...", func_name, id, json.size() > 2048 ? json.substr(0, 2048) + " ..." : json);
          auto status = co_await cli.Call(ctx, q, p);
          json        = aimrt::Pb2CompactJson(p);
          AIMRTE_INFO("Response From RpcFunc: [{}][{}] =====> rsp: {}, status: {}", func_name, id, json.size() > 2048 ? json.substr(0, 2048) + " ..." : json, status.ToString());

          co_return status;
        },
        loc);
    }

    void ServeDefaultOn(const res::Executor& exe, uint64_t timeout = 20 * 1000, AIMRTE(src(loc)))
    {
      if (this_.is_served_)
        return;

      ServeOn(
        exe,
        [cli{this_.cli_}, timeout, func_name{this_.GetName()}](const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
          aimrt::rpc::Context ctx;
          ctx.SetTimeout(std::chrono::milliseconds(timeout));

          auto id   = aimrte::utils::GenerateUniqueID();
          auto json = aimrt::Pb2CompactJson(q);
          AIMRTE_INFO("Request To RpcFunc: [{}][{}] req: {} [ServeDefaultOn]...", func_name, id, json.size() > 2048 ? json.substr(0, 2048) + " ..." : json);
          auto status = co_await cli.Call(ctx, q, p);
          json        = aimrt::Pb2CompactJson(p);
          AIMRTE_INFO("Response From RpcFunc: [{}][{}] =====> rsp: {}, status: {}", func_name, id, json.size() > 2048 ? json.substr(0, 2048) + " ..." : json, status.ToString());

          co_return status;
        },
        loc);
    }

   private:
    friend class Nginx;

    explicit WhenInitOperator(Nginx& impl)
        : this_(impl)
    {
    }

    Nginx& this_;
  };

 public:
  /**
   * @brief 准备使用只有 init 阶段可以使用的接口
   */
  auto WhenInit()
  {
    return WhenInitOperator(*this);
  }

  /**
   * @return 是否设置了服务处理函数
   */
  bool IsServed()
  {
    return is_served_;
  }

  /**
   * @return 简化版本的InternalCall函数, 去掉过程日志的打印, 由业务方自己维护
   */
  [[nodiscard]] co::Task<aimrt::rpc::Status> InternalCall(const Q& q, P& p, const std::uint64_t timeout = 20 * 1000)
  {
    aimrt::rpc::Context ctx;
    ctx.SetTimeout(std::chrono::milliseconds(timeout));
    auto status = co_await cli_.Call(ctx, q, p);
    co_return status;
  }

  [[nodiscard]] co::Task<aimrt::rpc::Status> InternalCall(aimrt::rpc::Context& ctx, const Q& q, P& p, const std::uint64_t timeout = 20 * 1000)
  {
    ctx.SetTimeout(std::chrono::milliseconds(timeout));
    auto status = co_await cli_.Call(ctx, q, p);
    co_return status;
  }

  /**
   * @brief 获取代理srv
   */
  Server<Q, P>& Srv()
  {
    return srv_;
  }

  /**
   * @brief 获取代理请求的客户端
   */
  Client<Q, P>& Cli()
  {
    return cli_;
  }

  /**
   *@brief 设置服务ID
   */
  void SetServerId(std::string_view server_id)
  {
    server_mqtt_id_ = std::string(server_id);
  }

  /**
   *@brief 获取服务ID
   */
  [[nodiscard]] const std::string& GetServerId() const
  {
    return server_mqtt_id_;
  }

  /**
   * @brief 设置当前Nginx的字符串名称
   * @param name
   */
  void SetName(const std::string_view name)
  {
    name_ = name;
  }

  /**
   * @brief 获取当前Nginx的字符串名称
   * @return
   */
  std::string_view GetName() const
  {
    return name_;
  }

 private:
  Server<Q, P> srv_;
  Client<Q, P> cli_;

  std::string server_mqtt_id_;
  std::string_view name_;

  bool is_served_ = false;
};
}  // namespace aimrte::ctx
