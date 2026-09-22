// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once


namespace aimrte::core
{
template <concepts::DirectlySupportedType T>
res::Channel<T> Context::OpPub::Init(const std::string_view& topic_name)
{
  // 以当前的类型，以及话题名称，创建新的信道上下文
  auto [ch, ch_ctx] = DoInit<T>(topic_name);

  // 基于该类型，设置发布函数与订阅函数
  ch_ctx.pub_f = CreatePublishFunction<T>();

  // 返回该发布器的资源描述符
  return ch;
}

template <class T, concepts::ByConverter TConverter>
res::Channel<T>
Context::OpPub::Init(const std::string_view& topic_name)
{
  using TRaw = typename TConverter::AnotherType;

  // 以当前的类型，以及话题名称，创建新的信道上下文
  auto [ch, ch_ctx] = DoInit<T, TRaw>(topic_name);

  // 基于该类型，设置发布函数与订阅函数
  ch_ctx.pub_f = CreatePublishFunction<T, TConverter>();

  // 返回该发布器的资源描述符
  return ch;
}

template <class T>
res::Channel<T>
Context::OpPub::InitMock(const std::string_view& topic_name, IMockPublisher<T>& mocker)
{
  // 新建发布通道资源
  ChannelContext& ch_ctx = ctx_.channel_contexts_.emplace_back();

  // 使用 mock 接管发布器的过程，对被测发布通道进行数据分析
  ch_ctx.pub_f = PublishFunction<T>(
    [&mocker](auto, auto, const T& msg) {
      mocker.Analyze(msg);
    });

  ctx_.log(loc_).Debug("Publisher [{}] is mocked.", topic_name);

  // 为 mocker 设置资源标识符，并返回给调用者，以便后续使用
  mocker.res_.name_       = topic_name;
  mocker.res_.idx_        = ctx_.channel_contexts_.size() - 1;
  mocker.res_.context_id_ = ctx_.id_;
  return mocker.res_;
}

template <class T>
void Context::OpPub::Publish(const res::Channel<T>& ch, const T& msg)
{
  aimrt::channel::Context ch_ctx;
  Publish(ch, ch_ctx, msg);
}

template <class T>
void Context::OpPub::Publish(const res::Channel<T> &ch, aimrt::channel::ContextRef ch_ctx, const T &msg) {
  // 取出信道上下文
  ChannelContext& pub_ctx = ctx_.GetChannelContext(ch, loc_);

  // 若允许 trace，则为 channel 上下文添加相关信息，确保 trace 被启动
  if (ctx_.enable_trace_) [[unlikely]] {
    assert(ch_ctx.NativeHandle() != nullptr);

    // TODO: 也许新增 publish 接口，传入 sub_ctx 与 pub_ctx，才能用起来下述过程
    // 本 publish 传入 ch_ctx 接口也暂时没有对外开放
    // pub_ctx.pub.MergeSubscribeContextToPublishContext()

    if (ch_ctx.GetMetaValue("aimrt_otp-traceparent").empty())
      ch_ctx.SetMetaValue("aimrt_otp-start_new_trace", "True");
  }

  // 通过该信道的上下文，发布数据
  std::any_cast<PublishFunction<T>&>(pub_ctx.pub_f)(pub_ctx.pub, ch_ctx, msg);
}

template <class T, concepts::DirectlySupportedType TRaw>
std::pair<res::Channel<T>, Context::ChannelContext&> Context::OpPub::DoInit(const std::string_view& topic_name)
{
  // 准备新的上下文
  ChannelContext ch_ctx;

  // 取出指定信道名称的发布器
  ch_ctx.pub = ctx_.core_.GetChannelHandle().GetPublisher(topic_name);
  ctx_.check(ch_ctx.pub, loc_).ErrorThrow("Get publisher for topic [{}] failed.", topic_name);

  // 基于指定类型，注册发布器
  if (not aimrt::channel::RegisterPublishType<TRaw>(ch_ctx.pub))
    ctx_.raise(loc_).Error("Register publish type for topic [{}] failed.", topic_name);

  // 初始化成功，维护该发布器资源
  ctx_.channel_contexts_.push_back(std::move(ch_ctx));
  ctx_.log(loc_).Info("Init publisher for topic [{}] succeeded.", topic_name);

  // 返回该发布器的资源描述符
  res::Channel<T> res;
  res.name_       = topic_name;
  res.idx_        = ctx_.channel_contexts_.size() - 1;
  res.context_id_ = ctx_.id_;
  return {std::move(res), ctx_.channel_contexts_.back()};
}

template <concepts::DirectlySupportedType T>
Context::PublishFunction<T> Context::OpPub::CreatePublishFunction()
{
  return
    [](aimrt::channel::PublisherRef pub, aimrt::channel::ContextRef ch_ctx, const T& msg) {
      aimrt::channel::Publish(pub, ch_ctx, msg);
  };
}


template <class T, concepts::ByConverter TConverter>
Context::PublishFunction<T> Context::OpPub::CreatePublishFunction()
{
  using TMsg = typename TConverter::AnotherType;

  return
    [](aimrt::channel::PublisherRef pub, aimrt::channel::ContextRef ch_ctx, const T& src_msg) {
      constexpr auto cvt = TConverter::template FromOriginal<T>();
      TMsg dst_msg;
      cvt(src_msg, dst_msg);
      aimrt::channel::Publish(pub, ch_ctx, dst_msg);
  };
}
}
