// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once


namespace aimrte::core
{
template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P, concepts::RawClient<Q, P> TClient>
res::Service<Q, P> Context::OpCli::Init(const std::string_view& service_name, TClient client)
{
  // 创建新的服务资源
  ServiceContext& srv_ctx = ctx_.service_contexts_.emplace_back();

  // 绑定当前通信类型的服务调用过程
  srv_ctx.call_f = Client<Q, P>(
    [client = std::move(client)](aimrt::rpc::ContextRef ctx, const Q& q, P& p) -> aimrt::co::Task<aimrt::rpc::Status> {
      co_return co_await client(ctx, q, p);
    });

  ctx_.log(loc_).Info("Init client for service [{}] succeeded.", service_name);

  // 返回新的资源标识符
  res::Service<Q, P> srv;
  srv.name_       = service_name;
  srv.idx_        = ctx_.service_contexts_.size() - 1;
  srv.context_id_ = ctx_.id_;
  return srv;
}

template <class Q, class P>
res::Service<Q, P> Context::OpCli::InitMock(const std::string_view& service_name, IMockClient<Q, P>& mocker)
{
  // 新建客户端服务资源
  ServiceContext& srv_ctx = ctx_.service_contexts_.emplace_back();

  // 使用 mock 接管客户端发起调用的过程，对被测的客户端发起的请求数据进行分析，并回传预设的响应数据与 rpc 状态
  // 给被测客户端，驱动其功能处理
  srv_ctx.call_f = Client<Q, P>(
    [&mocker](aimrt::rpc::ContextRef ctx, const Q& q, P& p) -> aimrt::co::Task<aimrt::rpc::Status> {
      aimrt::rpc::Status ret{};
      mocker.AnalyzeAndFeedback(ctx, q, p, ret);
      co_return ret;
    });

  ctx_.log(loc_).Debug("Client [{}] is mocked.", service_name);

  // 为 mocker 设置资源标识符，并返回给调用者，以便后续使用
  mocker.res_.name_       = service_name;
  mocker.res_.idx_        = ctx_.service_contexts_.size() - 1;
  mocker.res_.context_id_ = ctx_.id_;
  return mocker.res_;
}

template <class Q, class P, concepts::DirectlySupportedType QRaw, concepts::DirectlySupportedType PRaw>
res::Service<Q, P> Context::OpCli::InitService(res::Service<QRaw, PRaw>&& srv)
{
  using QCvt = convert::By<QRaw>;
  using PCvt = convert::By<PRaw>;

  // 取出已有的服务资源
  ServiceContext& srv_ctx = ctx_.GetServiceContext(srv, loc_);

  // 重新绑定客户端调用过程（如果它存在的话）
  if (srv_ctx.call_f.has_value()) {
    srv_ctx.call_f = Client<Q, P>(
      [raw_call_f = std::move(srv_ctx.call_f)](aimrt::rpc::ContextRef ctx, const Q& q, P& p) -> aimrt::co::Task<aimrt::rpc::Status> {
        constexpr auto q_cvt = QCvt::template FromOriginal<Q>();
        constexpr auto p_cvt = PCvt::template ToOriginal<P>();

        QRaw q_raw;
        q_cvt(q, q_raw);

        PRaw p_raw;
        aimrt::rpc::Status status = co_await std::any_cast<const Client<QRaw, PRaw>&>(raw_call_f)(ctx, q_raw, p_raw);
        p_cvt(p_raw, p);

        co_return status;
      });
  }

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
res::Service<Q, P> Context::OpCli::InitFunc(const std::string_view& func_name)
{
  // 以当前的类型，以及方法名称，创建新的服务上下文
  auto [srv, srv_ctx] = DoInit<Q, P, TSrv>(func_name);

  // 基于该类型，设置服务调用函数
  srv_ctx.call_f = CreateCallFunction<Q, P>(func_name);

  // 返回该客户端的资源描述符
  return srv;
}

template <class Q, class P, concepts::ByConverter QCvt, concepts::ByConverter PCvt, class TSrv>
res::Service<Q, P> Context::OpCli::InitFunc(const std::string_view& func_name)
{
  using QRaw = typename QCvt::AnotherType;
  using PRaw = typename PCvt::AnotherType;

  // 基于这些类型，以及方法名称，创建新的服务上下文
  auto [srv, srv_ctx] = DoInit<Q, P, TSrv, QRaw, PRaw>(func_name);

  // 基于该类型，设置服务调用函数
  srv_ctx.call_f = CreateCallFunction<Q, P, QCvt, PCvt>(func_name);

  // 返回该客户端的资源描述符
  return srv;
}

template <class Q, class P>
co::Task<aimrt::rpc::Status>
Context::OpCli::Call(const res::Service<Q, P>& srv, const Q& q, P& p)
{
  return [](Context & _ctx, const std::source_location _loc, const res::Service<Q, P>& _srv, const Q& _q,  P& _p) -> co::Task<aimrt::rpc::Status> {
    aimrt::rpc::Context rpc_ctx;
    co_return co_await OpCli::DoCall(_ctx, _loc, _srv, rpc_ctx, _q, _p);
  }(ctx_, loc_, srv, q, p);
}

template <class Q, class P>
co::Task<aimrt::rpc::Status> Context::OpCli::Call(const res::Service<Q, P>& srv, aimrt::rpc::ContextRef ctx, const Q& q, P& p)
{
  return DoCall(ctx_, loc_, srv, std::move(ctx), q, p);
}

template <class Q, class P, class TSrv, concepts::DirectlySupportedType QRaw, concepts::DirectlySupportedType PRaw>
std::pair<res::Service<Q, P>, Context::ServiceContext&> Context::OpCli::DoInit(const std::string_view& func_name)
{
  // 要求服务资源原始请求类型与响应类型是匹配的一套类型
  static_assert(concepts::SameDirectlySupportedType<QRaw, PRaw>);

  // 新建服务资源描述符
  res::Service<Q, P> res;
  res.name_       = details::WrapRpcFuncName<QRaw>(func_name);
  res.idx_        = ctx_.service_contexts_.size();
  res.context_id_ = ctx_.id_;

  // 注册该 rpc client
  const bool status = ctx_.core_.GetRpcHandle().RegisterClientFunc(
    res.GetName(),
    details::GetCustomTypeSupport<TSrv>(),
    details::GetMessageTypeSupport<QRaw>(),
    details::GetMessageTypeSupport<PRaw>());

  if (not status)
    ctx_.raise(loc_).Error("Failed to register client func [{}].", res.GetName());

  ctx_.log(loc_).Info("Init client func [{}] succeeded.", res.GetName());

  // 初始化成功，新增服务资源上下文，并返回该资源描述符
  return {std::move(res), ctx_.service_contexts_.emplace_back()};
}

template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P> Context::Client<Q, P>
Context::OpCli::CreateCallFunction(const std::string_view &func_name) const
{
  return
    [rpc{ctx_.core_.GetRpcHandle()}, func_name{details::WrapRpcFuncName<Q>(func_name)}](aimrt::rpc::ContextRef ctx_ref, const Q& q, P& p) -> aimrt::co::Task<aimrt::rpc::Status> {
      std::shared_ptr<aimrt::rpc::Context> ctx;

      if (not ctx_ref) {
        ctx     = std::make_shared<aimrt::rpc::Context>();
        ctx_ref = aimrt::rpc::ContextRef(ctx);
      }

      if (ctx_ref.GetSerializationType().empty())
        ctx_ref.SetSerializationType(details::GetSerializationType<Q>());

      struct Awaitable {
        std::string_view func_name;
        aimrt::rpc::RpcHandleRef rpc_handle_ref;
        aimrt::rpc::ContextRef ctx_ref;
        const void* req_ptr;
        void* rsp_ptr;

        aimrt::rpc::Status status;

        constexpr bool await_ready() const noexcept { return false; }

        void await_suspend(std::coroutine_handle<> h)
        {
          rpc_handle_ref.Invoke(
            func_name,
            ctx_ref, req_ptr, rsp_ptr,
            [this, h](const std::uint32_t code) {
              status = aimrt::rpc::Status(code);
              h.resume();
            });
        }

        auto await_resume() noexcept { return status; }
      };

      co_return co_await Awaitable{
        .func_name      = func_name,
        .rpc_handle_ref = rpc,
        .ctx_ref        = ctx_ref,
        .req_ptr        = static_cast<const void*>(&q),
        .rsp_ptr        = static_cast<void*>(&p),
      };
  };
}

template <class Q, class P, concepts::ByConverter QCvt, concepts::ByConverter PCvt>
Context::Client<Q, P> Context::OpCli::CreateCallFunction(const std::string_view &func_name) const
{
  using QRaw = typename QCvt::AnotherType;
  using PRaw = typename PCvt::AnotherType;

  return
    [raw_call_f = CreateCallFunction<QRaw, PRaw>(func_name)](aimrt::rpc::ContextRef ctx_ref, const Q& q, P& p) -> aimrt::co::Task<aimrt::rpc::Status> {
      constexpr auto q_cvt = QCvt::template FromOriginal<Q>();
      constexpr auto p_cvt = PCvt::template ToOriginal<P>();

      QRaw q_raw;
      q_cvt(q, q_raw);

      PRaw p_raw;
      aimrt::rpc::Status status = co_await raw_call_f(ctx_ref, q_raw, p_raw);
      p_cvt(p_raw, p);

      co_return status;
  };
}

template <class Q, class P>
co::Task<aimrt::rpc::Status> Context::OpCli::DoCall(
   Context & ctx, std::source_location loc, const res::Service<Q, P> & srv, aimrt::rpc::ContextRef rpc_ctx, const Q & q, P & p)
{
  // 取出服务上下文
  ServiceContext& srv_ctx = ctx.GetServiceContext(srv, loc);

  // 若允许 trace，则为上下文添加相关信息，确保 trace 被启动或延续
  if (ctx.enable_trace_) [[unlikely]] {
    assert(rpc_ctx.NativeHandle() != nullptr);

    // 检查是否从上游收到 trace 信息，若没有，则开始新的 trace
    if (const auto & opt = details::g_thread_ctx.active_rpc_context; opt.has_value()) {
      ctx.core_.GetRpcHandle().MergeServerContextToClientContext(*opt, rpc_ctx);

      if (rpc_ctx.GetMetaValue("aimrt_otp-traceparent").empty())
        rpc_ctx.SetMetaValue("aimrt_otp-start_new_trace", "True");
    }
    else
      rpc_ctx.SetMetaValue("aimrt_otp-start_new_trace", "True");
  }

  // 进行远程调用
  co_return co_await std::any_cast<Client<Q, P>&>(srv_ctx.call_f)(rpc_ctx, q, p);
}
}
