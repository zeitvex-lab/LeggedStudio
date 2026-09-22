// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
class Context::OpSrv : public OpBase
{
 public:
  using OpBase::OpBase;

  /**
   * @brief 使用指定的请求响应数据类型，初始化新的服务端资源，用于 Serve() 函数绑定用户服务处理回调，
   *        或在原生通信模型中，通过 Serving() 函数执行用户的处理回调。
   * @note 该函数一般只在 AimRT service impl 子类中使用。
   * @tparam Q 请求数据类型
   * @tparam P 响应数据类型
   * @param service_name 一个服务过程/方法的名称，目前仅用于日志记录。
   * @return 服务端资源标识符，将用于后续绑定用户的处理函数、或由原生通信模型，驱动处理回调的调用。
   */
  template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P>
  [[nodiscard]] res::Service<Q, P> Init(const std::string_view& service_name);

  /**
   * @brief 初始化一个被测的服务端资源
   */
  template <class Q, class P>
  res::Service<Q, P> InitMock(const std::string_view& service_name, IMockServer<Q, P>& mocker);

  /**
   * @brief 将已有的服务资源处理的类型，转换为另外一套类型。
   * @tparam Q 新的请求数据类型
   * @tparam P 新的响应数据类型
   * @tparam QRaw 原始请求数据类型
   * @tparam PRaw 原始响应数据类型
   * @param srv 有效的服务资源，转换之后将失效
   * @return 新的服务资源
   * @deprecated
   */
  template <class Q, class P, concepts::DirectlySupportedType QRaw, concepts::DirectlySupportedType PRaw>
  [[nodiscard]] res::Service<Q, P> InitService(res::Service<QRaw, PRaw>&& srv);

  /**
   * @brief 初始化指定类型的服务资源
   * @tparam Q AimRT 支持的请求数据类型
   * @tparam P AimRT 支持的响应数据类型
   * @tparam TSrv 通信需要的额外类型信息
   * @param func_name 方法名称
   * @return 该调用资源的标识符
   */
  template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P, class TSrv = void>
  [[nodiscard]] res::Service<Q, P> InitFunc(const std::string_view& func_name);

  /**
   * @brief 初始化指定类型的服务资源
   * @tparam Q 用于自定义的请求数据类型
   * @tparam P 用于自定义的响应数据类型
   * @tparam QCvt 用于转换用户请求数据类型的类型转换器
   * @tparam PCvt 用于转换用户请求数据类型的类型转换器
   * @tparam TSrv 通信需要的额外类型信息
   * @param func_name 方法名称
   * @return 该调用资源的标识符
   */
  template <class Q, class P, concepts::ByConverter QCvt, concepts::ByConverter PCvt, class TSrv = void>
  [[nodiscard]] res::Service<Q, P> InitFunc(const std::string_view& func_name);

 public:
  /**
   * @brief 注册指定服务资源的服务处理回调，该回调发生在原生通信系统的回调中。
   * @tparam Q 请求数据类型
   * @tparam P 响应数据类型
   * @param srv     服务资源标识符
   * @param server  服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
   *                (const Q &, P &)，返回 rpc::Status.
   *                该处理器将在原生通信的回调中执行，请勿编写过重的内容。
   */
  template <class Q, class P, concepts::SupportedServer<Q, P> TServer>
  void ServeInline(const res::Service<Q, P>& srv, TServer server);

  /**
   * @brief 调用给定的服务资源，执行其中绑定的服务函数。
   * @note 该函数一般只在 AimRT service impl 子类中使用。
   * @tparam Q 请求数据类型
   * @tparam P 响应数据类型
   * @return 处理结果
   */
  template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P>
  aimrt::co::Task<aimrt::rpc::Status> Serving(
    const res::Service<Q, P>& srv, aimrt::rpc::ContextRef ctx, const Q& q, P& p);

 private:
  /**
   * @brief 基础的 service server 初始化过程。
   * @return 新的 service 资源，以及部分初始化的服务上下文。
   */
  template <class Q, class P, class TSrv, concepts::DirectlySupportedType QRaw = Q, concepts::DirectlySupportedType PRaw = P>
  std::pair<res::Service<Q, P>, ServiceContext&> DoInitFunc(const std::string_view& func_name);

  /**
   * @brief 统一的 server 绑定过程。
   */
  template <class Q, class P, concepts::SupportedServer<Q, P> TServer>
  void DoServe(const res::Service<Q, P>& srv, TServer server, res::Executor exe);

  /**
   * @return 调用服务处理函数的函数
   */
  template <concepts::DirectlySupportedType Q, concepts::DirectlySupportedType P>
  ServerInvoker<Q, P> CreateServerInvokerFunction() const;

  /**
   * @return 转换类型、然后进行服务处理的函数
   */
  template <class Q, class P, concepts::ByConverter QCvt, concepts::ByConverter PCvt>
  ServerInvoker<typename QCvt::AnotherType, typename PCvt::AnotherType> CreateServerInvokerFunction() const;

  /**
   * @brief 标准化服务处理函数为 co::Task<rpc::Status>(rpc::ContextRef, const Q &, P &)
   */
  template <class Q, class P, concepts::SupportedServer<Q, P> F>
  static constexpr auto StandardizeServer(F cb);

  friend class OpExe;
};
}  // namespace aimrte::core
