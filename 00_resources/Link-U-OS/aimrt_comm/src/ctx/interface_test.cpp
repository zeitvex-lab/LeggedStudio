// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/ctx/ctx.h"
#include "src/test/test.h"
#include "src/test_protocol/test_msg_new.aimrt_rpc.pb.h"
#include "src/test_protocol/test_msg_new.pb.h"

#include "./details/fs.h"

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
class InterfaceTest : public TestBase
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
      - type: rotate_file # 文件日志
        options:
          path: ./log # 日志文件路径
          filename: example_helloworld_pkg_mode.log # 日志文件名称
          max_file_size_m: 4 # 日志文件最大尺寸，单位m
          max_file_num: 10 # 最大日志文件数量，0代表无限
  executor: # 执行器配置
    executors: # 当前先支持thread型，未来可根据加载的网络模块提供更多类型
      - name: work_thread_pool # 线程池
        type: asio_thread
        options:
          thread_num: 5 # 线程数，不指定则默认单线程
      - name: single_thread_pool # 线程池
        type: asio_thread
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

  void OnTearDown() override
  {
    ctrl.LetEnd();
  }

  ModuleTestController ctrl;
};

TEST_F(InterfaceTest, Log)
{
  ctrl.LetStart();

  ctx::log().Info("hello world");
  // GTEST_ASSERT_TRUE(ExpectOutputContent("hello world"));

  AIMRTE_TRACE("abc");
  AIMRTE_DEBUG("abc, {}", 1);
  AIMRTE_INFO("edf");
  AIMRTE_WARN("hij");
  AIMRTE_ERROR("lmn");
  AIMRTE_FATAL("opq");

  const std::source_location loc = std::source_location::current();
  AIMRTE_TRACE_AT(loc, "abc");
  AIMRTE_DEBUG_AT(loc, "abc, {}", 1);
  AIMRTE_INFO_AT(loc, "edf");
  AIMRTE_WARN_AT(loc, "hij");
  AIMRTE_ERROR_AT(loc, "lmn");
  AIMRTE_FATAL_AT(loc, "opq");
}

TEST_F(InterfaceTest, Check)
{
  ctrl.LetStart();

  ctx::check(true).Info("aaa");
  // GTEST_ASSERT_TRUE(not ExpectOutputContent("aaa"));

  ctx::check(false).Info("bbb");
  // GTEST_ASSERT_TRUE(ExpectOutputContent("bbb"));

  try {
    ctx::check(true).ErrorThrow("ccc");
    // GTEST_ASSERT_TRUE(not ExpectOutputContent("ccc"));
  } catch (...) {
    GTEST_FAIL();
  }

  try {
    ctx::check(false).ErrorThrow("ddd");
    GTEST_FAIL();
  } catch (...) {
    // GTEST_ASSERT_TRUE(ExpectOutputContent("ddd"));
  }
}

TEST_F(InterfaceTest, Raise)
{
  ctrl.LetStart();

  try {
    ctx::raise().Error("aaa");
    GTEST_FAIL();
  } catch (...) {
    // GTEST_ASSERT_TRUE(ExpectOutputContent("aaa"));
  }
}

TEST_F(InterfaceTest, Executor)
{
  ctrl.LetInit();
  ctx::Executor exe = ctx::init::Executor("work_thread_pool");

  ctrl.LetStart();

  for (int i = 0; i < 1000; ++i) {
    exe.Post(
      [i] {
        ctx::log().Info("msg: abc of {}", i);
      });
  }

  for (int i = 0; i < 1000; ++i) {
    exe.Post(
      [i]() -> co::Task<void> {
        ctx::log().Info("msg: edf of {}", i);
        co_return;
      });
  }

  std::this_thread::sleep_for(std::chrono::seconds(1));
}

TEST_F(InterfaceTest, ExecutorInline)
{
  ctrl.LetInit();
  ctx::Executor exe = ctx::init::Executor("work_thread_pool");

  bool flag = false;
  exe.Inline(
    [&]() {
      ctx::log().Info("very");

      // 在当前所在的执行器上执行，因此其中的过程会拥有当前的上下文
      ctx::exe().Inline(
        [&]() {
          ctx::log().Info("good");
          flag = true;
        });
    });

  GTEST_ASSERT_TRUE(flag);
}

TEST_F(InterfaceTest, ExecutorPostAndQuit)
{
  ctrl.LetInit();
  const ctx::Executor exe = ctx::init::Executor("work_thread_pool");

  ctrl.LetStart();

  std::atomic_int execution_count = 0;
  for (int i = 0; i < 1000; ++i) {
    exe.Post(
      [&]() -> co::Task<void> {
        co_await ctx::Sleep(std::chrono::milliseconds(1000));
        ++execution_count;
      });
  }

  ctrl.LetEnd();
  GTEST_ASSERT_EQ(execution_count, 1000);
}

TEST_F(InterfaceTest, ThreadSafeExecutor)
{
  ctrl.LetInit();

  try {
    const res::Executor exe = ctx::init::ThreadSafeExecutor("single_thread_pool");
  } catch (...) {
    GTEST_FAIL();
  }

  try {
    const res::Executor exe = ctx::init::ThreadSafeExecutor("work_thread_pool");
    GTEST_FAIL();
  } catch (...) {
  }
}

TEST_F(InterfaceTest, Publish)
{
  ctrl.LetInit();

  const ctx::Publisher res1 =
    ctx::init::Publisher<test_protocol::TestMsg>("/my_topic_name");

  const ctx::Publisher res2 =
    ctx::init::Publisher<std::string, convert::By<test_protocol::TestMsg>>("/my_topic_name_2");

  ctrl.LetStart();
  test_protocol::TestMsg protobuf_msg;

  res1.Publish(protobuf_msg);
  res1 << protobuf_msg << protobuf_msg;

  std::string str_msg;
  res2.Publish(str_msg);
  str_msg >> res2;
}

co::Task<void> MySleepFunc()
{
  co_await ctx::Sleep(std::chrono::seconds(1));
}

TEST_F(InterfaceTest, Subscribe)
{
  ctrl.LetInit();

  const ctx::Subscriber<test_protocol::TestMsg> res1 =
    ctx::init::Subscriber<test_protocol::TestMsg>("/my_topic_name");

  const ctx::Subscriber<std::string> res2 =
    ctx::init::Subscriber<std::string, convert::By<test_protocol::TestMsg>>("/my_topic_name_2");

  const res::Executor exe = ctx::init::Executor("work_thread_pool");

  res1.WhenInit().SubscribeInline(
    [](const test_protocol::TestMsg&) {
    });

  res2.WhenInit().SubscribeOn(
    exe,
    [](std::shared_ptr<const std::string>) -> co::Task<void> {
      co_return;
    });
}

TEST_F(InterfaceTest, Client)
{
  ctrl.LetInit();

  // build client
  const aimrt::rpc::RpcHandleRef rpc_handle = ctrl.GetCoreRef().GetRpcHandle();
  aimrt::rpc::RegisterClientFunc<test_protocol::TestServiceCoProxy>(rpc_handle);
  auto proxy = std::make_shared<test_protocol::TestServiceCoProxy>(rpc_handle);

  // init srv
  const ctx::Client srv =
    ctx::init::Client<test_protocol::TestMsg, test_protocol::TestMsg>(
      "MyMethod",
      [proxy](aimrt::rpc::ContextRef ctx, const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::co::Task<aimrt::rpc::Status> {
        co_return co_await proxy->MyMethod(ctx, q, p);
      });

  // call
  ctrl.LetRun();

  test_protocol::TestMsg q, p;
  srv.Call(q, p).Sync();
  srv.Call(q, p).Sync();
}

TEST_F(InterfaceTest, ClientWithConverter)
{
  ctrl.LetInit();

  // build client
  const aimrt::rpc::RpcHandleRef rpc_handle = ctrl.GetCoreRef().GetRpcHandle();
  aimrt::rpc::RegisterClientFunc<test_protocol::TestServiceCoProxy>(rpc_handle);
  auto proxy = std::make_shared<test_protocol::TestServiceCoProxy>(rpc_handle);

  // init srv
  ctx::Client raw_srv =
    ctx::init::Client<test_protocol::TestMsg, test_protocol::TestMsg>(
      "MyMethod",
      [proxy](aimrt::rpc::ContextRef ctx, const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::co::Task<aimrt::rpc::Status> {
        co_return co_await proxy->MyMethod(ctx, q, p);
      });

  // convert
  ctx::Client srv = ctx::init::Service<std::string, std::string>(std::move(raw_srv));

  // call
  ctrl.LetRun();

  std::string q, p;
  srv.Call(q, p).Sync();
}

class TestServiceImpl : public test_protocol::TestServiceCoService
{
 public:
  aimrt::co::Task<aimrt::rpc::Status> MyMethod(aimrt::rpc::ContextRef ctx_ref, const test_protocol::TestMsg& req, test_protocol::TestMsg& rsp) override
  {
    co_return co_await ctx::Serving(res, ctx_ref, req, rsp);
  }

  // 需要在初始化时设置的通信资源
  ctx::Server<test_protocol::TestMsg, test_protocol::TestMsg> res;
};

TEST_F(InterfaceTest, Server)
{
  ctrl.LetInit();

  // init service impl
  auto service_impl = std::make_shared<TestServiceImpl>();
  service_impl->res = ctx::init::Server<test_protocol::TestMsg, test_protocol::TestMsg>("MyService");

  ctrl.GetCoreRef().GetRpcHandle().RegisterService(service_impl.get());

  // set server
  service_impl->res.WhenInit().ServeInline(
    [](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(InterfaceTest, ServerWithConverter)
{
  ctrl.LetInit();

  // init service impl
  auto service_impl = std::make_shared<TestServiceImpl>();
  service_impl->res = ctx::init::Server<test_protocol::TestMsg, test_protocol::TestMsg>("MyService");

  ctrl.GetCoreRef().GetRpcHandle().RegisterService(service_impl.get());

  // convert
  ctx::Server raw_srv = service_impl->res;
  ctx::Server srv     = ctx::init::Service<std::string, std::string>(std::move(raw_srv));

  // set server
  srv.WhenInit().ServeInline(
    [](const std::string& q, std::string& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(InterfaceTest, ServerOnExecutor)
{
  ctrl.LetInit();

  // init service impl
  auto service_impl = std::make_shared<TestServiceImpl>();
  service_impl->res = ctx::init::Server<test_protocol::TestMsg, test_protocol::TestMsg>("MyService");

  ctrl.GetCoreRef().GetRpcHandle().RegisterService(service_impl.get());

  // get executor
  ctx::Executor exe = ctx::init::Executor("work_thread_pool");

  // set server
  service_impl->res.WhenInit().ServeOn(
    exe,
    [](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(InterfaceTest, ClientFunc)
{
  ctrl.LetInit();

  const ctx::Client srv = ctx::init::ClientFunc<test_protocol::TestMsg, test_protocol::TestMsg>("/my/client/func");

  ctrl.LetRun();

  test_protocol::TestMsg q, p;
  aimrt::rpc::Status status = srv.Call(q, p).Sync();

  std::optional<test_protocol::TestMsg> p_opt = srv(q).Sync();
}

TEST_F(InterfaceTest, ClientFuncWithConverter)
{
  ctrl.LetInit();

  const ctx::Client srv =
    ctx::init::ClientFunc<
      std::string,
      std::string,
      convert::By<test_protocol::TestMsg>,
      convert::By<test_protocol::TestMsg>>("/my/client/func");

  ctrl.LetRun();

  std::string q, p;
  srv.Call(q, p).Sync();
}

TEST_F(InterfaceTest, ServerFunc)
{
  ctrl.LetInit();

  const ctx::Server srv = ctx::init::ServerFunc<test_protocol::TestMsg, test_protocol::TestMsg>("/my/server/func");

  srv.WhenInit().ServeInline(
    [](const test_protocol::TestMsg& q, test_protocol::TestMsg& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(InterfaceTest, ServerFuncWithConverter)
{
  ctrl.LetInit();

  const ctx::Server srv =
    ctx::init::ServerFunc<
      std::string,
      std::string,
      convert::By<test_protocol::TestMsg>,
      convert::By<test_protocol::TestMsg>>("/my/server/func");

  srv.WhenInit().ServeInline(
    [](const std::string& q, std::string& p) -> aimrt::rpc::Status {
      return {};
    });
}

TEST_F(InterfaceTest, Sleep)
{
  ctrl.LetRun();

  GTEST_ASSERT_TRUE(
    TimePass(
      std::chrono::seconds(1), std::chrono::milliseconds(100),
      [] {
        ctx::Sleep(std::chrono::seconds(1)).Sync();
      }));
}

TEST_F(InterfaceTest, SleepOnExecutor)
{
  ctrl.LetInit();

  ctx::Executor exe = ctx::init::Executor("work_thread_pool");

  ctrl.LetRun();

  bool status = false;
  exe.Post(
    [&]() -> co::Task<void> {
      status =
        TimePass(
          std::chrono::seconds(1), std::chrono::milliseconds(100),
          []() -> co::Task<void> {
            co_await ctx::Sleep(std::chrono::seconds(1));
          })
          .Sync();

      co_return;
    });

  ctrl.LetEnd();
  GTEST_ASSERT_TRUE(status);
}

TEST_F(InterfaceTest, Loop)
{
  ctrl.LetRun();

  ctx::Loop loop(std::chrono::seconds(1));

  const bool ret = TimePass(
    std::chrono::milliseconds(3300), std::chrono::milliseconds(100),
    [&] {
      int n = 0;
      while (loop.Ok().Sync() and n < 3) {
        switch (n++) {
          case 0:
            break;

          case 1:
            ctx::Sleep(std::chrono::milliseconds(1300)).Sync();
            break;

          case 2:
            ctx::Sleep(std::chrono::milliseconds(300)).Sync();
            break;

          default:
            break;
        }
      }
    });

  GTEST_ASSERT_TRUE(ret);
}

TEST_F(InterfaceTest, Fs)
{
  const std::filesystem::path home = std::filesystem::path(std::source_location::current().file_name()).parent_path().string() + "/test";
  setenv("AGIBOT_HOME", home.string().data(), 1);

  ctrl.LetInit();
  ctrl.GetContext().InitSubContext<ctx::details::Fs>(core::Context::SubContext::Fs, "TestModule");

  auto do_test = [&]() {
    const std::filesystem::path data_path  = ctx::GetDataPath();
    const std::filesystem::path param_path = ctx::GetParamPath();
    const std::filesystem::path temp_path  = ctx::GetTempPath();

    GTEST_ASSERT_EQ(data_path, home / "agibot/data/var/TestModule");
    GTEST_ASSERT_EQ(param_path, home / "agibot/data/param/TestModule");
    GTEST_ASSERT_TRUE(temp_path.string().find("TestModule") != std::string::npos);

    GTEST_ASSERT_TRUE(std::filesystem::is_directory(data_path));
    GTEST_ASSERT_TRUE(std::filesystem::is_directory(param_path));
    GTEST_ASSERT_TRUE(std::filesystem::is_directory(temp_path));
  };

  if (not exists(home)) {
    create_directories(home);
    create_directories(home / "agibot/data/var");
    create_directories(home / "agibot/data/param");
    create_directories(home / "agibot/data/tmp");
  }

  do_test();
  do_test();

  remove_all(home);
}
}  // namespace aimrte::test
