// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once


namespace aimrte::core
{
template <concepts::DirectlySupportedType T>
res::Channel<T> Context::OpSub::Init(const std::string_view& topic_name)
{
  // 以当前的类型，以及话题名称，创建新的信道上下文
  auto [ch, ch_ctx] = DoInit<T>(topic_name);

  // 基于该类型，设置发布函数与订阅函数
  ch_ctx.sub_f = CreateSubscribeFunction<T>();

  // 返回该发布器的资源描述符
  return ch;
}

template <class T, concepts::ByConverter TConverter>
res::Channel<T> Context::OpSub::Init(const std::string_view& topic_name)
{
  using TRaw = typename TConverter::AnotherType;

  // 以当前的类型，以及话题名称，创建新的信道上下文
  auto [ch, ch_ctx] = DoInit<T, TRaw>(topic_name);

  // 基于该类型，设置发布函数与订阅函数
  ch_ctx.sub_f = CreateSubscribeFunction<T, TConverter>();

  // 返回该发布器的资源描述符
  return ch;
}

template <class T>
res::Channel<T> Context::OpSub::InitMock(const std::string_view& topic_name, IMockSubscriber<T>& mocker)
{
  // 新建订阅通道资源
  ChannelContext& ch_ctx = ctx_.channel_contexts_.emplace_back();

  // 使用 mock 接管订阅的过程，对被测订阅通道进行数据饲喂，驱动被测订阅者进行功能处理
  ch_ctx.sub_f = SubscribeFunction<T>(
    [&mocker](auto, ChannelCallback<T> cb, std::weak_ptr<Context> ctx_ptr, res::Executor exe) -> bool {
      mocker.cb_ = [cb, ctx_ptr{ctx_ptr}](T msg) {
        details::g_thread_ctx = {ctx_ptr};
        cb(std::make_shared<const T>(std::move(msg))).Sync();
      };

      if (not exe.IsValid())
        return true;

      mocker.async_cb_ = [ctx_ptr{ctx_ptr.lock()}, cb, exe{std::move(exe)}](T msg, typename IMockSubscriber<T>::AnalyzeCaller analyzer) {
        ctx_ptr->exe(exe).Post(
          [&cb, msg{std::move(msg)}, analyzer{std::move(analyzer)}]() mutable -> co::Task<void> {
            co_await cb(std::make_shared<const T>(std::move(msg)));
            analyzer();
          });
      };

      return true;
    });

  ctx_.log(loc_).Debug("Subscriber [{}] is mocked.", topic_name);

  // 为 mocker 设置资源标识符，并返回给调用者，以便后续使用
  mocker.res_.name_       = topic_name;
  mocker.res_.idx_        = ctx_.channel_contexts_.size() - 1;
  mocker.res_.context_id_ = ctx_.id_;
  return mocker.res_;
}

template <class T, concepts::SupportedSubscriber<T> TCallback>
void Context::OpSub::SubscribeInline(const res::Channel<T>& ch, TCallback callback)
{
  DoSubscribe(ch, std::move(callback), {});
}

template <class T, concepts::DirectlySupportedType TRaw>
std::pair<res::Channel<T>, Context::ChannelContext&> Context::OpSub::DoInit(const std::string_view& topic_name)

{
  // 准备新的上下文
  ChannelContext ch_ctx;

  // 取出指定信道名称的订阅器
  ch_ctx.sub = ctx_.core_.GetChannelHandle().GetSubscriber(topic_name);
  ctx_.check(ch_ctx.sub, loc_).ErrorThrow("Get subscribe for topic [{}] failed.", topic_name);

  // 初始化成功，维护该发布器资源
  ctx_.channel_contexts_.push_back(std::move(ch_ctx));
  ctx_.log(loc_).Info("Init subscriber for topic [{}] succeeded.", topic_name);

  // 返回该发布器的资源描述符
  res::Channel<T> res;
  res.name_       = topic_name;
  res.idx_        = ctx_.channel_contexts_.size() - 1;
  res.context_id_ = ctx_.id_;
  return {std::move(res), ctx_.channel_contexts_.back()};
}

template <concepts::DirectlySupportedType T, concepts::SubscriberCoroutine<T> F>
bool Context::OpSub::RawSubscribe(
  aimrt::channel::SubscriberRef subscriber, std::weak_ptr<Context> ctx_weak_ptr, res::Executor exe, F callback){
  // 设置在给定的执行器上、订阅回调函数或协程的执行。
  if (exe.IsValid()) {
    return subscriber.Subscribe(
      details::GetMessageTypeSupport<T>(),
      [callback = std::move(callback), ctx_weak_ptr = std::move(ctx_weak_ptr), exe = std::move(exe)](
        const aimrt_channel_context_base_t*, const void* msg_ptr, aimrt_function_base_t* release_callback_base) {
        // 取出上下文数据
        const std::shared_ptr ctx_ptr = ctx_weak_ptr.lock();

        // 若上下文已经失效，忽略该数据
        if (nullptr == ctx_ptr)
          return;

        // 在指定的执行器中回调处理
        ctx_ptr->exe(exe).Post(
          [callback, msg = details::MakeSharedMessage<T>(msg_ptr, release_callback_base)]() mutable -> co::Task<void> {
            co_return co_await callback(std::move(msg));
          });
      });
  }

  // 设置在原生的通信回调中、执行用户订阅函数
  return subscriber.Subscribe(
    details::GetMessageTypeSupport<T>(),
    [callback = std::move(callback), ctx_ptr = std::move(ctx_weak_ptr)](
      const aimrt_channel_context_base_t*, const void* msg_ptr, aimrt_function_base_t* release_callback_base) {
      // 准备执行上下文
      details::g_thread_ctx = {ctx_ptr};

      // 唤起用户的回调
      co::SyncInline(callback, details::MakeSharedMessage<T>(msg_ptr, release_callback_base));
    });
}

template <concepts::DirectlySupportedType T>
Context::SubscribeFunction<T> Context::OpSub::CreateSubscribeFunction()
{
  return
    [](
      aimrt::channel::SubscriberRef sub,
      ChannelCallback<T> cb,
      std::weak_ptr<Context> ctx_ptr,
      res::Executor exe) -> bool {
      return RawSubscribe<T>(sub, std::move(ctx_ptr), std::move(exe), std::move(cb));
    };
}

template <class T, concepts::ByConverter TConverter>
Context::SubscribeFunction<T> Context::OpSub::CreateSubscribeFunction()
{
  using TMsg = typename TConverter::AnotherType;

  return
    [](
      aimrt::channel::SubscriberRef sub,
      ChannelCallback<T> cb,
      std::weak_ptr<Context> ctx_ptr,
      res::Executor exe) -> bool {
      return RawSubscribe<TMsg>(
        sub, std::move(ctx_ptr), std::move(exe),
        [cb = std::move(cb)](std::shared_ptr<const TMsg> src_msg) -> co::Task<void> {
          constexpr auto cvt = TConverter::template ToOriginal<T>();
          auto dst_msg       = std::make_shared<T>();
          cvt(*src_msg, *dst_msg);
          co_return co_await cb(std::move(dst_msg));
        });
  };
}

template <class T, concepts::SupportedSubscriber<T> TCallback>
void Context::OpSub::DoSubscribe(const res::Channel<T> &ch, TCallback callback, res::Executor exe)
{
  const std::string exe_msg =
    exe.IsValid() ? ::fmt::format("on executor [{}]", exe.name_) : "inline";

  // 取出信道上下文
  ChannelContext& ch_ctx = ctx_.GetChannelContext(ch, loc_);

  // 取出该资源类型的注册函数
  SubscribeFunction<T>& sub_f = std::any_cast<SubscribeFunction<T>&>(ch_ctx.sub_f);

  // 执行注册
  const bool ret =
    sub_f(ch_ctx.sub, StandardizeSubscriber<T>(std::move(callback)), ctx_.weak_from_this(), std::move(exe));

  // 处理结果
  if (ret)
    ctx_.log(loc_).Info("Subscribe [{}] {} succeeded.", ch.name_, exe_msg);
  else
    ctx_.raise(loc_).Error("Subscribe [{}] {} failed.", ch.name_, exe_msg);
}

template <class T, concepts::SupportedSubscriber<T> F>
constexpr auto Context::OpSub::StandardizeSubscriber(F cb)
{
  if constexpr (concepts::SubscriberFunction<F, T>) {
    return [cb = std::move(cb)](std::shared_ptr<const T> msg) -> co::Task<void> {
      co_return cb(std::move(msg));
    };
  } else if constexpr (concepts::SubscriberCoroutine<F, T>) {
    return cb;
  } else if constexpr (concepts::SubscriberRawCoroutine<F, T>) {
    return [cb = std::move(cb)](std::shared_ptr<const T> msg) -> co::Task<void> {
      co_return co_await cb(std::move(msg));
    };
  } else if constexpr (concepts::SubscriberFunctionDeref<F, T>) {
    return [cb = std::move(cb)](std::shared_ptr<const T> msg) -> co::Task<void> {
      co_return cb(*msg);
    };
  } else if constexpr (concepts::SubscriberCoroutineDeref<F, T> or concepts::SubscriberRawCoroutineDeref<F, T>) {
    return [cb = std::move(cb)](std::shared_ptr<const T> msg) -> co::Task<void> {
      co_return co_await cb(*msg);
    };
  } else
    static_assert(trait::always_false_v<T>);
}
}
