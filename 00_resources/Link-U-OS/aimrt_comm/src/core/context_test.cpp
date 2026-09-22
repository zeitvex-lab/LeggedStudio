// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/test/test.h"
#include "src/test_protocol/test_msg_new.aimrt_rpc.pb.h"
#include "src/test_protocol/test_msg_new.pb.h"
#include "src/trait/trait.h"
#include "src/test_protocol/TestService.h"
#include "Eigen/Eigen"

// 实现协议数据类型（test_protocol::TestMsg）与自定义类型（std::string）的转换函数，
// 可用于封装通信接口
namespace aimrte::impl
{
template <>
void Convert(const std::string& src, test_protocol::TestMsg& dst)
{
  *dst.mutable_str() = src;
}

template <>
void Convert(const test_protocol::TestMsg& src, std::string& dst)
{
  dst = src.str();
}
}  // namespace aimrte::impl

namespace aimrte::test
{
class ContextTest : public TestBase
{
 protected:
  void OnSetup() override
  {
    ctrl.SetConfigContent(
      R"yaml(
aimrt:
  configurator:
    temp_cfg_path: ./cfg/tmp # 生成的临时模块配置文件存放路径
  log: # log配置
    core_lvl: INFO # 内核日志等级，可选项：Trace/Debug/Info/Warn/Error/Fatal/Off，不区分大小写
    default_module_lvl: Trace # 模块默认日志等级
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
)yaml");
  }

 protected:
  ModuleTestController ctrl;
};

TEST_F(ContextTest, HelloWorld)
{
  ctrl.LetStart();

  std::cout << "hello world" << std::endl;

  // GTEST_ASSERT_TRUE(ExpectOutputContent("hello world"));
}

TEST_F(ContextTest, Log)
{
  ctrl.LetStart();

  core::Context& ctx = ctrl.GetContext();

  ctx.log().Trace("hello world");
  ctx.log().Debug("hello world");
  ctx.log().Info("hello world");
  ctx.log().Warn("hello world");
  ctx.log().Error("hello world");
  ctx.log().Fatal("hello world");
}

struct ReflectSupportData {
  int x{1};
  std::string y{"hello world"};
  bool z{true};
};

struct StreamSupportData {
  int x{1};
  std::string y{"hello world"};
  bool z{true};

  friend std::ostream& operator<<(std::ostream& os, const StreamSupportData& data)
  {
    os << "x: " << data.x << ", y: " << data.y << ", z: " << data.z;
    return os;
  }
};

TEST_F(ContextTest, LogAnyData)
{
  ctrl.LetStart();
  core::Context& ctx = ctrl.GetContext();

  std::string str{"hello world"};
  const std::string const_str{"const hello world"};
  ctx.log().Info("{}\n{}\n{}\n{}\n{}\n{}\n{}", 1, StreamSupportData{}, ReflectSupportData{}, str, std::move(str), const_str, std::move(const_str));

  Eigen::MatrixXd m;
  m.setRandom(10, 12);
  ctx.log().Info("m: {}", m);
}

TEST_F(ContextTest, Check)
{
  ctrl.LetStart();
  core::Context& ctx = ctrl.GetContext();

  ctx.check(true).Info("aaa");
  // GTEST_ASSERT_TRUE(not ExpectOutputContent("aaa"));

  ctx.check(false).Info("bbb");
  // GTEST_ASSERT_TRUE(ExpectOutputContent("bbb"));

  try {
    ctx.check(true).ErrorThrow("ccc");
    // GTEST_ASSERT_TRUE(not ExpectOutputContent("ccc"));
  } catch (...) {
    GTEST_FAIL();
  }

  try {
    ctx.check(false).ErrorThrow("ddd");
    GTEST_FAIL();
  } catch (...) {
    // GTEST_ASSERT_TRUE(ExpectOutputContent("ddd"));
  }
}

TEST_F(ContextTest, Raise)
{
  ctrl.LetStart();
  core::Context& ctx = ctrl.GetContext();

  try {
    ctx.raise().Error("aaa");
    GTEST_FAIL();
  } catch (...) {
    // GTEST_ASSERT_TRUE(ExpectOutputContent("aaa"));
  }
}

TEST_F(ContextTest, GetExecutorAndPost)
{
  ctrl.LetStart();

  core::Context& ctx = ctrl.GetContext();
  res::Executor res  = ctx.InitExecutor("work_thread_pool");

  for (int i = 0; i < 1000; ++i) {
    ctx.exe(res).Post(
      [&, i] {
        ctx.log().Info("msg: abc of {}", i);
      });
  }

  for (int i = 0; i < 1000; ++i) {
    ctx.exe(res).Post(
      [&, i]() -> co::Task<void> {
        ctx.log().Info("msg: edf of {}", i);
        co_return;
      });
  }

  std::this_thread::sleep_for(std::chrono::seconds(1));
}

TEST_F(ContextTest, GetExecutorAndInline)
{
  ctrl.LetInit();

  core::Context& ctx = ctrl.GetContext();
  res::Executor res  = ctx.InitExecutor("work_thread_pool");

  bool flag = false;
  ctx.exe(res).Inline(
    [&]() {
      flag = true;
    });

  GTEST_ASSERT_TRUE(flag);
}

TEST_F(ContextTest, GetWrongExectuorAndThrow)
try {
  ctrl.LetStart();
  res::Executor res = ctrl.GetContext().InitExecutor("wrong_executor");
  GTEST_FAIL();
} catch (const std::exception& ec) {
  ctrl.GetContext().log().Info("exeception message: {}", ec.what());
}

TEST_F(ContextTest, Publish)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Channel<test_protocol::TestMsg> res1 =
    ctx.pub().Init<test_protocol::TestMsg>("/my_topic_name");

  const res::Channel<std::string> res2 =
    ctx.pub().Init<std::string, convert::By<test_protocol::TestMsg>>("/my_topic_name_2");

  ctrl.LetStart();
  test_protocol::TestMsg protobuf_msg;
  ctx.pub().Publish(res1, protobuf_msg);

  std::string str_msg;
  ctx.pub().Publish(res2, str_msg);
}

TEST_F(ContextTest, Subscribe)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Channel<test_protocol::TestMsg> res1 =
    ctx.sub().Init<test_protocol::TestMsg>("/my_topic_name");

  const res::Channel<std::string> res2 =
    ctx.sub().Init<std::string, convert::By<test_protocol::TestMsg>>("/my_topic_name_2");

  const res::Executor exe = ctx.InitExecutor("work_thread_pool");

  ctx.sub().SubscribeInline(
    res1,
    [](const test_protocol::TestMsg&) {
    });

  ctx.exe(exe).Subscribe(
    res2,
    [](std::shared_ptr<const std::string>) -> co::Task<void> {
      co_return;
    });
}

TEST_F(ContextTest, Client)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  // build client
  const aimrt::rpc::RpcHandleRef rpc_handle = ctrl.GetCoreRef().GetRpcHandle();
  aimrt::rpc::RegisterClientFunc<test_protocol::TestServiceCoProxy>(rpc_handle);
  auto proxy = std::make_shared<test_protocol::TestServiceCoProxy>(rpc_handle);

  // init srv
  const res::Service srv =
    ctx.cli().Init<test_protocol::TestMsg, test_protocol::TestMsg>(
      "MyMethod",
      [proxy](aimrt::rpc::ContextRef ctx, const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::co::Task<aimrt::rpc::Status> {
        co_return co_await proxy->MyMethod(ctx, q, p);
      });

  // call
  ctrl.LetRun();

  test_protocol::TestMsg q, p;
  // aimrt::co::SyncWait(proxy->MyMethod(q, p));

  ctx.cli().Call(srv, q, p).Sync();
  // ctx.cli().Call(srv, q, p).Sync();
}

TEST_F(ContextTest, ClientRos)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  // build client
  const aimrt::rpc::RpcHandleRef rpc_handle = ctrl.GetCoreRef().GetRpcHandle();
  aimrt::rpc::RegisterClientFunc<test_service_interface::srv::TestServiceCoProxy>(rpc_handle);
  auto proxy = std::make_shared<test_service_interface::srv::TestServiceCoProxy>(rpc_handle);

  // init srv
  const res::Service srv =
    ctx.cli().Init<test_service_interface::srv::TestService::Request, test_service_interface::srv::TestService_Response>(
      "MyMethod",
      [proxy](aimrt::rpc::ContextRef ctx, const test_service_interface::srv::TestService_Request& q, test_service_interface::srv::TestService_Response& p) -> aimrt::co::Task<aimrt::rpc::Status> {
        co_return co_await proxy->TestService(ctx, q, p);
      });

  // call
  ctrl.LetRun();

  test_service_interface::srv::TestService_Request q;
  test_service_interface::srv::TestService_Response p;
  ctx.cli().Call(srv, q, p).Sync();
}

TEST_F(ContextTest, ClientWithConverter)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  // build client
  const aimrt::rpc::RpcHandleRef rpc_handle = ctrl.GetCoreRef().GetRpcHandle();
  aimrt::rpc::RegisterClientFunc<test_protocol::TestServiceCoProxy>(rpc_handle);
  auto proxy = std::make_shared<test_protocol::TestServiceCoProxy>(rpc_handle);

  // init srv
  res::Service raw_srv =
    ctx.cli().Init<test_protocol::TestMsg, test_protocol::TestMsg>(
      "MyMethod",
      [proxy](aimrt::rpc::ContextRef ctx, const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::co::Task<aimrt::rpc::Status> {
        co_return co_await proxy->MyMethod(ctx, q, p);
      });

  // convert
  res::Service srv = ctx.cli().InitService<std::string, std::string>(std::move(raw_srv));

  // call
  ctrl.LetRun();

  std::string q, p;
  ctx.cli().Call(srv, q, p).Sync();
}

class TestServiceImpl : public test_protocol::TestServiceCoService
{
 public:
  aimrt::co::Task<aimrt::rpc::Status> MyMethod(aimrt::rpc::ContextRef ctx_ref, const test_protocol::TestMsg& req, test_protocol::TestMsg& rsp) override
  {
    co_return co_await ctx_ptr->srv().Serving(res, ctx_ref, req, rsp);
  }

  // 需要在初始化时设置的通信资源
  res::Service<test_protocol::TestMsg, test_protocol::TestMsg> res;

  // 上下文指针，之后应该使用 ctx:: 接口来获取
  core::Context* ctx_ptr = nullptr;
};

TEST_F(ContextTest, Server)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  // init service impl
  auto service_impl     = std::make_shared<TestServiceImpl>();
  service_impl->ctx_ptr = &ctx;
  service_impl->res     = ctx.srv().Init<test_protocol::TestMsg, test_protocol::TestMsg>("MyService");

  ctrl.GetCoreRef().GetRpcHandle().RegisterService(service_impl.get());

  // set server
  ctx.srv().ServeInline(
    service_impl->res,
    [](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(ContextTest, ServerWithConverter)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  // init service impl
  auto service_impl     = std::make_shared<TestServiceImpl>();
  service_impl->ctx_ptr = &ctx;
  service_impl->res     = ctx.srv().Init<test_protocol::TestMsg, test_protocol::TestMsg>("MyService");

  ctrl.GetCoreRef().GetRpcHandle().RegisterService(service_impl.get());

  // convert
  res::Service raw_srv = service_impl->res;
  res::Service srv     = ctx.srv().InitService<std::string, std::string>(std::move(raw_srv));

  // set server
  ctx.srv().ServeInline(
    srv,
    [](const std::string& q, std::string& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(ContextTest, ServerOnExecutor)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  // init service impl
  auto service_impl     = std::make_shared<TestServiceImpl>();
  service_impl->ctx_ptr = &ctx;
  service_impl->res     = ctx.srv().Init<test_protocol::TestMsg, test_protocol::TestMsg>("MyService");

  ctrl.GetCoreRef().GetRpcHandle().RegisterService(service_impl.get());

  // get executor
  res::Executor exe = ctx.InitExecutor("work_thread_pool");

  // set server
  ctx.exe(exe).Serve(
    service_impl->res,
    [](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(ContextTest, ClientFunc)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Service res = ctx.cli().InitFunc<test_protocol::TestMsg, test_protocol::TestMsg>("/my/client/func");

  ctrl.LetRun();

  test_protocol::TestMsg q, p;
  ctx.cli().Call(res, q, p).Sync();
  ctx.cli().Call(res, q, p).Sync();
}

TEST_F(ContextTest, ClientFuncWithConverter)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Service res =
    ctx.cli().InitFunc<std::string, std::string, convert::By<test_protocol::TestMsg>, convert::By<test_protocol::TestMsg>>("/my/client/func");

  ctrl.LetRun();

  std::string q, p;
  ctx.cli().Call(res, q, p).Sync();
  ctx.cli().Call(res, q, p).Sync();
}

TEST_F(ContextTest, ServerFunc)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Service res = ctx.srv().InitFunc<test_protocol::TestMsg, test_protocol::TestMsg>("/my/server/func");

  ctx.srv().ServeInline(
    res,
    [](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(ContextTest, ServerFuncWithConverter)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Service res =
    ctx.srv().InitFunc<std::string, std::string, convert::By<test_protocol::TestMsg>, convert::By<test_protocol::TestMsg>>("/my/server/func");

  ctx.srv().ServeInline(
    res,
    [](const std::string& q, std::string& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(ContextTest, CustomClientAndServer)
{
  ctrl.LetInit();
  core::Context& ctx = ctrl.GetContext();

  const res::Service res_cli = ctx.cli().InitFunc<test_protocol::TestMsg, test_protocol::TestMsg>("/my/custom/func");
  const res::Service res_srv = ctx.srv().InitFunc<test_protocol::TestMsg, test_protocol::TestMsg>("/my/custom/func");

  bool flag = false;
  ctx.srv().ServeInline(
    res_srv,
    [&](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      flag = q.str() == "abc";
      return {};
    });

  ctrl.LetRun();

  test_protocol::TestMsg q, p;
  q.set_str("abc");
  ctx.cli().Call(res_cli, q, p).Sync();

  GTEST_ASSERT_TRUE(flag);
}
}  // namespace aimrte::test
