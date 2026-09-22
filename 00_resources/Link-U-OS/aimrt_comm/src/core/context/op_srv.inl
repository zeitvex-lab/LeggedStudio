// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once


namespace aimrte::core
{
template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P>
res::Service<Q, P> Context::OpSrv::Init(const std::string_view& service_name)
{
  // 创建新的服务资源
  ServiceContext& srv_ctx = ctx_.service_contexts_.emplace_back();

  // 绑定当前通信类型的服务处理过程
  srv_ctx.server_invoke_f = CreateServerInvokerFunction<Q, P>();

  ctx_.log(loc_).Info("Init server for service [{}] succeeded.", service_name);

  // 返回新资源标识符
  res::Service<Q, P> srv;
  srv.name_       = service_name;
  srv.idx_        = ctx_.service_contexts_.size() - 1;
  srv.context_id_ = ctx_.id_;
  return srv;
}

template <class Q, class P>
res::Service<Q, P> Context::OpSrv::InitMock(const std::string_view& service_name, IMockServer<Q, P>& mocker)
{
  // 新建服务端的服务资源
  ServiceContext& srv_ctx = ctx_.service_contexts_.emplace_back();

  // 使用 mock 为被测服务端提供预定的请求数据，分析被测服务返回的响应数据与 rpc 状态。
  srv_ctx.register_server_f = RegisterServerFunction<Q, P>(
    [&mocker](Server<Q, P> server, std::weak_ptr<Context> ctx_ptr, res::Executor exe) {
      mocker.func_ = [ctx_ptr{ctx_ptr}, server](
                       const aimrt::rpc::ContextRef& rpc_ctx, const Q& q, P& p) -> aimrt::rpc::Status {
        details::g_thread_ctx = {ctx_ptr, {}, rpc_ctx};
        return server(rpc_ctx, q, p).Sync();
      };

      if (not exe.IsValid())
        return;

      mocker.async_func_ = [ctx_ptr{ctx_ptr.lock()}, server, exe{std::move(exe)}](aimrt::rpc::ContextRef rpc_ctx, Q q, typename IMockServer<Q, P>::AnalyzeCaller analyzer) {
        ctx_ptr->exe(exe).Post(
          [&server, rpc_ctx{std::move(rpc_ctx)}, q{std::move(q)}, analyzer{std::move(analyzer)}]() -> co::Task<void> {
            // 设置 rpc context（其余内容已经在 exe 中设置）
            details::g_thread_ctx.active_rpc_context = rpc_ctx;

            // 调用用户设置的回调
            P p;
            aimrt::rpc::Status ret = co_await server(rpc_ctx, q, p);
            analyzer(rpc_ctx, q, p, ret);
          });
      };
    });

  ctx_.log(loc_).Debug("Server [{}] is mocked.", service_name);

  // 为 mocker 设置资源标识符，并返回给调用者，以便后续使用
  mocker.res_.name_       = service_name;
  mocker.res_.idx_        = ctx_.service_contexts_.size() - 1;
  mocker.res_.context_id_ = ctx_.id_;
  return mocker.res_;
}

template <class Q, class P, concepts::DirectlySupportedType QRaw, concepts::DirectlySupportedType PRaw>
res::Service<Q, P> Context::OpSrv::InitService(res::Service<QRaw, PRaw>&& srv)
{
  using QCvt = convert::By<QRaw>;
  using PCvt = convert::By<PRaw>;

  // 取出已有的服务资源
  ServiceContext& srv_ctx = ctx_.GetServiceContext(srv, loc_);

  // 若当前服务资源已经被绑定了服务处理函数，则报错
  if (srv_ctx.serve_f.has_value())
    ctx_.raise(loc_).Error("Init service [{}] failed, because a user server is set.", srv.name_);

  // 重新绑定服务的处理过程，以植入类型转换过程。
  srv_ctx.server_invoke_f = CreateServerInvokerFunction<Q, P, QCvt, PCvt>();

  // 准备新的资源标识符
  res::Service<Q, P> new_srv;
  new_srv.name_       = std::move(srv.name_);
  new_srv.idx_        = srv.idx_;
  new_srv.context_id_ = ctx_.id_;

  // 废弃旧标识符
  srv = res::Service<QRaw, PRaw>();

  // 返回新的资源标识符
  return new_srv;
}

template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P, class TSrv>
res::Service<Q, P> Context::OpSrv::InitFunc(const std::string_view& func_name)
{
  // 以当前的类型，以及方法名称，创建新的服务上下文
  auto [srv, srv_ctx] = DoInitFunc<Q, P, TSrv>(func_name);

  // 基于该类型，设置服务处理函数
  srv_ctx.server_invoke_f = CreateServerInvokerFunction<Q, P>();

  // 返回该服务端的资源描述符
  return srv;
}

template <class Q, class P, concepts::ByConverter QCvt, concepts::ByConverter PCvt, class TSrv>
res::Service<Q, P> Context::OpSrv::InitFunc(const std::string_view& func_name)
{
  using QRaw = typename QCvt::AnotherType;
  using PRaw = typename PCvt::AnotherType;

  // 基于这些类型，以及方法名称，创建新的服务上下文
  auto [srv, srv_ctx] = DoInitFunc<Q, P, TSrv, QRaw, PRaw>(func_name);

  // 基于该类型，设置服务处理函数
  srv_ctx.server_invoke_f = CreateServerInvokerFunction<Q, P, QCvt, PCvt>();

  // 返回该服务端的资源描述符
  return srv;
}

template <class Q, class P, concepts::SupportedServer<Q, P> TServer>
void Context::OpSrv::ServeInline(const res::Service<Q, P>& srv, TServer server)
{
  DoServe(srv, std::move(server), {});
}

template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P>
aimrt::co::Task<aimrt::rpc::Status> Context::OpSrv::Serving(
  const res::Service<Q, P>& srv, aimrt::rpc::ContextRef ctx, const Q& q, P& p)
{
  return [](
    Context & _ctx, const std::source_location _loc,
    const res::Service<Q, P>& _srv, aimrt::rpc::ContextRef _rpc_ctx, const Q& _q, P& _p) -> aimrt::co::Task<aimrt::rpc::Status> {
    // 获取资源指定的服务上下文
    ServiceContext& srv_ctx = _ctx.GetServiceContext(_srv, _loc);

    // 进行服务回调； serve_f 绑定的处理类型可能与当前通信类型不同，类型转换细节被封装在了 server_invoke_f 中。
    co_return co_await std::any_cast<ServerInvoker<Q, P>&>(srv_ctx.server_invoke_f)(_rpc_ctx, _q, _p, srv_ctx.serve_f);
  }(ctx_, loc_, srv, std::move(ctx), q, p);
}

template <class Q, class P, class TSrv, concepts::DirectlySupportedType QRaw, concepts::DirectlySupportedType PRaw>
std::pair<res::Service<Q, P>, Context::ServiceContext&> Context::OpSrv::DoInitFunc(const std::string_view& func_name)
{
  // 要求服务资源原始请求类型与响应类型是匹配的一套类型
  static_assert(concepts::SameDirectlySupportedType<QRaw, PRaw>);

  // 新建资源描述符，服务处理函数使用该描述符来获取用户注册的服务函数
  res::Service<Q, P> res;
  res.name_       = details::WrapRpcFuncName<QRaw>(func_name);
  res.idx_        = ctx_.service_contexts_.size();
  res.context_id_ = ctx_.id_;

  // 向 AimRT 注册的服务回调处理函数
  auto cb =
    [res, ctx_weak_ptr = ctx_.weak_from_this()](const aimrt_rpc_context_base_t* ctx, const void* req, void* rsp, aimrt_function_base_t* status_cb_raw) {
      using StatusCB = aimrt::util::Function<aimrt_function_service_callback_ops_t>;

      // 服务状态处理过程
      StatusCB status_cb(status_cb_raw);

      // 取出上下文信息
      const std::shared_ptr ctx_ptr = ctx_weak_ptr.lock();

      // 上下文已失效，直接返回服务失效
      if (ctx_ptr == nullptr) {
        status_cb(AIMRT_RPC_STATUS_SVR_NOT_FOUND);
        return;
      }

      // 服务处理过程
      const static auto h =
        [](
          aimrt::rpc::ContextRef ctx_ref, const void* _req, void* _rsp,
          const res::Service<Q, P> _res, const std::shared_ptr<Context> _ctx_ptr, StatusCB _status_cb) -> aimrt::co::Task<void> {
        // 取出服务资源
        ServiceContext& srv_ctx = _ctx_ptr->GetServiceContext(_res, std::source_location::current());

        // 执行服务处理过程
        const aimrt::rpc::Status status = co_await std::any_cast<ServerInvoker<QRaw, PRaw>&>(srv_ctx.server_invoke_f)(
          ctx_ref,
          *static_cast<const QRaw*>(_req),
          *static_cast<PRaw*>(_rsp),
          srv_ctx.serve_f);

        _status_cb(status.Code());
      };

      // 在当前上下文的协程域内执行该服务处理过程
      ctx_ptr->async_scope_.spawn_on(aimrt::co::InlineScheduler(), h(aimrt::rpc::ContextRef(ctx), req, rsp, res, ctx_ptr, std::move(status_cb)));
    };

  // 准备新的服务上下文
  ServiceContext& srv_ctx   = ctx_.service_contexts_.emplace_back();
  srv_ctx.raw_server_holder = {std::move(cb)};
  srv_ctx.func_name         = res.GetName();

  // 注册该函数
  const aimrt_rpc_handle_base_t* rpc = ctx_.core_.GetRpcHandle().NativeHandle();

  const bool status = rpc->register_service_func(
    rpc->impl,
    aimrt::util::ToAimRTStringView(srv_ctx.func_name),
    details::GetCustomTypeSupport<TSrv>(),
    details::GetMessageTypeSupport<QRaw>(),
    details::GetMessageTypeSupport<PRaw>(),
    srv_ctx.raw_server_holder.NativeHandle());

  if (not status)
    ctx_.raise(loc_).Error("Failed to register server func [{}].", res.GetName());

  ctx_.log(loc_).Info("Init server func [{}] succeeded.", res.GetName());

  // 初始化成功，返回该服务资源及其资源描述符
  return {std::move(res), srv_ctx};
}

template <class Q, class P, concepts::SupportedServer<Q, P> TServer>
void Context::OpSrv::DoServe(const res::Service<Q, P>& srv, TServer server, res::Executor exe)
{
  const std::string exe_msg =
    exe.IsValid() ? ::fmt::format("on executor [{}]", exe.name_) : "inline";

  // 取出服务上下文
  ServiceContext& srv_ctx = ctx_.GetServiceContext(srv, loc_);

  // 若服务已经被绑定，则报错
  if (srv_ctx.serve_f.has_value())
    ctx_.raise(loc_).Error("Serve [{}] {} failed. You CANNOT serve twice on the same res::Service !", srv.name_, exe_msg);

  // 标准化服务处理函数
  auto cb = StandardizeServer<Q, P>(std::move(server));

  // 检查该资源是否设置了服务函数注册器，如果是，则使用它来对服务进行注册
  if (srv_ctx.register_server_f.has_value()) {
    std::any_cast<RegisterServerFunction<Q, P>&>(srv_ctx.register_server_f)(
      std::move(cb), ctx_.weak_from_this(), std::move(exe));

    // 绑定服务成功
    ctx_.log(loc_).Info("Serve [{}] {} succeeded.", srv.name_, exe_msg);
    return;
  }

  // 根据是否指定了执行器，进行不同的绑定处理
  if (exe.IsValid()) {
    srv_ctx.serve_f = Server<Q, P>(
      [cb = std::move(cb), ctx_weak_ptr = ctx_.weak_from_this(), exe = std::move(exe)](aimrt::rpc::ContextRef rpc_ctx, const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
        // 取出上下文信息
        std::shared_ptr ctx_ptr = ctx_weak_ptr.lock();

        // 若上下文已经失效，则直接返回服务失败
        if (ctx_ptr == nullptr)
          co_return aimrt::rpc::Status(AIMRT_RPC_STATUS_SVR_NOT_FOUND);

        // 切换至指定执行器中执行
        co_await aimrt::co::Schedule(
          aimrt::co::AimRTScheduler(
            OpExe::GetRawRef(ctx_ptr->exe(exe))));

        // 准备执行上下文
        details::g_thread_ctx = {ctx_weak_ptr, exe, rpc_ctx};

        // 执行用户处理函数，并返回它的结果
        co_return co_await cb(rpc_ctx, q, p);
      });
  } else {
    srv_ctx.serve_f = Server<Q, P>(
      [cb = std::move(cb), ctx_weak_ptr = ctx_.weak_from_this()](aimrt::rpc::ContextRef rpc_ctx, const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
        // 准备执行上下文
        details::g_thread_ctx = {ctx_weak_ptr, {}, rpc_ctx};

        // 执行用户处理函数，并返回它的结果
        co_return co_await cb(rpc_ctx, q, p);
      });
  }

  // 绑定服务成功
  ctx_.log(loc_).Info("Serve [{}] {} succeeded.", srv.name_, exe_msg);
}

template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P> Context::ServerInvoker<Q, P>
Context::OpSrv::CreateServerInvokerFunction() const
{
  return
    [](aimrt::rpc::ContextRef ctx, const Q& q, P& p, std::any& f) -> aimrt::co::Task<aimrt::rpc::Status> {
      if (not f.has_value())
        co_return aimrt::rpc::Status(AIMRT_RPC_STATUS_SVR_NOT_IMPLEMENTED);

      co_return co_await std::any_cast<Server<Q, P>&>(f)(ctx, q, p);
  };
}

template <class Q, class P, concepts::ByConverter QCvt, concepts::ByConverter PCvt>
Context::ServerInvoker<typename QCvt::AnotherType, typename PCvt::AnotherType> Context::OpSrv::CreateServerInvokerFunction() const
{
  using QRaw = typename QCvt::AnotherType;
  using PRaw = typename PCvt::AnotherType;

  return
    [](aimrt::rpc::ContextRef ctx, const QRaw& q_raw, PRaw& p_raw, std::any& f) -> aimrt::co::Task<aimrt::rpc::Status> {
      if (not f.has_value())
        co_return aimrt::rpc::Status(AIMRT_RPC_STATUS_SVR_NOT_IMPLEMENTED);

      constexpr auto q_cvt = QCvt::template ToOriginal<Q>();
      constexpr auto p_cvt = PCvt::template FromOriginal<P>();

      Q q;
      q_cvt(q_raw, q);

      P p;
      aimrt::rpc::Status status = co_await std::any_cast<Server<Q, P>&>(f)(ctx, q, p);
      p_cvt(p, p_raw);

      co_return status;
  };
}

template <class Q, class P, concepts::SupportedServer<Q, P> F>
constexpr auto Context::OpSrv::StandardizeServer(F cb)
{
  if constexpr (concepts::ServerFunction<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef, const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
      co_return cb(q, p);
    };
  } else if constexpr (concepts::ServerCoroutine<F, Q, P> or concepts::ServerRawCoroutine<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef, const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
      co_return co_await cb(q, p);
    };
  } else if constexpr (concepts::ServerFunctionWithCtx<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef ctx, const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
      co_return cb(ctx, q, p);
    };
  } else if constexpr (concepts::ServerCoroutineWithCtx<F, Q, P>)
    return cb;
  else if constexpr (concepts::ServerRawCoroutineWithCtx<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef ctx, const Q& q, P& p) -> co::Task<aimrt::rpc::Status> {
      co_return co_await cb(ctx, q, p);
    };
  }
  else if constexpr (concepts::ServerFunctionReturnVoid<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef, const Q & q, P & p) -> co::Task<aimrt::rpc::Status> {
      cb(q, p);
      co_return aimrt::rpc::Status();
    };
  }
  else if constexpr (concepts::ServerCoroutineReturnVoid<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef, const Q & q, P & p) -> co::Task<aimrt::rpc::Status> {
      co_await cb(q, p);
      co_return aimrt::rpc::Status();
    };
  }
  else if constexpr (concepts::ServerFunctionReturnVoidWithCtx<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef ctx, const Q & q, P & p) -> co::Task<aimrt::rpc::Status> {
      cb(ctx, q, p);
      co_return aimrt::rpc::Status();
    };
  }
  else if constexpr (concepts::ServerCoroutineReturnVoidWithCtx<F, Q, P>) {
    return [cb = std::move(cb)](aimrt::rpc::ContextRef ctx, const Q & q, P & p) -> co::Task<aimrt::rpc::Status> {
      co_await cb(ctx, q, p);
      co_return aimrt::rpc::Status();
    };
  }
  else
    static_assert(trait::always_false_v<F>);
}
}
