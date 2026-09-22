// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./result.h"
#include "src/test/test.h"

namespace aimrte::test
{
class ResultTest : public TestBase
{
};

TEST_F(ResultTest, BasicUsage)
{
  Result<int, double> res = Ok(1);
  GTEST_ASSERT_TRUE(res.IsOk());

  ifLet(res) = Ok | [](int& x) {
    std::cout << ++x << std::endl;
  };

  GTEST_ASSERT_TRUE(ExpectOutputContent("2"));

  res = Err(3.0);
  GTEST_ASSERT_TRUE(res.IsErr());

  match(res) |
    trait::impl{
      Ok | [&](const int x) {
        std::cout << x + 1 << std::endl;
      },
      Err | [&](const double x) {
        std::cout << x + 2.0 << std::endl;
      },
    };

  GTEST_ASSERT_TRUE(ExpectOutputContent("5"));
}

TEST_F(ResultTest, VoidValue)
{
  Result<void, int> res = Ok();

  auto match_once = [&]() {
    match(res) |
      trait::impl{
        Ok | []() {
          std::cout << "ok" << std::endl;
        },
        Err | [](const double x) {
          std::cout << "err" << std::endl;
        },
      };
  };

  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("ok"));

  res = Err(1);
  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("err"));
}

TEST_F(ResultTest, VoidError)
{
  Result<int, void> res = Ok(1);

  auto match_once = [&]() {
    match(res) |
      trait::impl{
        Ok | [](int) {
          std::cout << "ok" << std::endl;
        },
        Err | []() {
          std::cout << "err" << std::endl;
        },
      };
  };

  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("ok"));

  res = Err();
  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("err"));
}

TEST_F(ResultTest, VoidValueAndError)
{
  Result<void, void> res = Ok();

  auto match_once = [&]() {
    match(res) |
      trait::impl{
        Ok | []() {
          std::cout << "ok" << std::endl;
        },
        Err | []() {
          std::cout << "err" << std::endl;
        },
      };
  };

  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("ok"));

  res = Err();
  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("err"));
}

TEST_F(ResultTest, UsedInReturn)
{
  auto return_result = []() {
    return Ok(2);
  };

  Result<int, bool> res = return_result();

  ifLet(res) = Ok | [](int x) {
    std::cout << "ok" << std::endl;
  };
  GTEST_ASSERT_TRUE(ExpectOutputContent("ok"));

  ifLet(res) = Err | [](int) {
    std::cout << "err" << std::endl;
  };
  GTEST_ASSERT_TRUE(not ExpectOutputContent("err"));
}

TEST_F(ResultTest, AllKindsOfOperands)
{
  std::string lvalue;
  const std::string const_lvalue;

  Result<std::string, std::string> res = Ok(lvalue);
  res                                  = Ok(const_lvalue);
  res                                  = Ok(std::move(lvalue));

  res = Err(lvalue);
  res = Err(const_lvalue);
  res = Err(std::move(lvalue));
}

TEST_F(ResultTest, ReturnErrorAndLog)
{
  // need ctx
  ModuleTestController ctrl;
  ctrl.SetConfigContent(R"(
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
)");

  ctrl.LetRun();

  auto return_error = []() -> Result<int, std::string> {
    return Err(std::string("some error message")).log();
  };

  GTEST_ASSERT_TRUE(return_error().IsErr());
  // GTEST_ASSERT_TRUE(ExpectOutputContent("error"));
}

TEST_F(ResultTest, IfLetMacro)
{
  Result<int, float> res = Ok(1);

  if AIMRTE (let(res), as(Ok), then(int x)) {
    GTEST_ASSERT_EQ(x, 1);
  } else {
    GTEST_FAIL();
  }

  if AIMRTE (let(res), as(Err), then(float x)) {
    GTEST_FAIL();
  }

  res = Err(2.0f);

  if AIMRTE (let(res), as(Ok), then(int x)) {
    GTEST_FAIL();
  }

  if AIMRTE (let(res), as(Err), then(float x)) {
    GTEST_ASSERT_EQ(x, 2.0);
  }
}

TEST_F(ResultTest, Unwarp)
{
  Result<int, float> x = Ok(1);

  GTEST_ASSERT_EQ(x.Unwarp()++, 1);
  GTEST_ASSERT_EQ(x.ConstUnwarp(), 2);

  x = Err(2.0f);
  AIMRTE_TEST_SHOULD_PANIC(x.Unwarp());
}
}  // namespace aimrte::test
