// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./option.h"
#include "src/test/test.h"

namespace aimrte::test
{
class OptionTest : public TestBase
{
};

TEST_F(OptionTest, BasicUsage)
{
  Option y = Some(1);
  GTEST_ASSERT_TRUE(y.IsSome());

  ifLet(y) = Some | [](int& x) {
    std::cout << ++x << std::endl;
  };

  GTEST_ASSERT_TRUE(ExpectOutputContent("2"));

  y = None;
  GTEST_ASSERT_TRUE(y.IsNone());

  match(y) |
    trait::impl{
      Some | [&](int x) {
        std::cout << x << std::endl;
      },
      None | [&]() {
        std::cout << "none" << std::endl;
      },
    };

  GTEST_ASSERT_TRUE(ExpectOutputContent("none"));
}

TEST_F(OptionTest, IfLetMacro)
{
  Option y = Some(1);

  if AIMRTE (let(y), as(Some), then(int x)) {
    GTEST_ASSERT_EQ(x, 1);
  } else {
    GTEST_FAIL();
  }

  y = None;

  if AIMRTE (let(y), as(Some), then(int x)) {
    GTEST_FAIL();
  }
}

TEST_F(OptionTest, Unwarp)
{
  Option x = Some(1);

  GTEST_ASSERT_EQ(x.Unwarp()++, 1);
  GTEST_ASSERT_EQ(x.ConstUnwarp(), 2);

  x = None;
  AIMRTE_TEST_SHOULD_PANIC(x.Unwarp());
}
}  // namespace aimrte::test
