// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/macro/macro.h"
#include <gtest/gtest.h>

namespace aimrte::test
{
class MacroTest : public ::testing::Test
{
};

auto UseUniversalMacro(int x) AIMRTE(noexcept(x))

  TEST_F(MacroTest, BasicUsage)
{
  {
    constexpr int N = 999;

    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS(), 0);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS(1), 1);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS(1, 2), 2);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS(1, 2, 3), 3);

    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_N(), 0);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_N(1), N);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_N(1, 2), N);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_N(1, 2, 3), N);

    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_1_N(), 0);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_1_N(1), 1);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_1_N(1, 2), N);
    GTEST_ASSERT_EQ(AIMRTE_COUNT_ARGS_0_1_N(1, 2, 3), N);
  }

  {
    GTEST_ASSERT_EQ(AIMRTE_CONCAT(1, 2), 12);
    GTEST_ASSERT_EQ(AIMRTE_CONCAT(1, 2, 3), 123);
  }

  {
#define MY_MACRO(x) +x

    GTEST_ASSERT_EQ(AIMRTE_INVOKE(MY_MACRO, 1, 2, 3), 6);

#define MY_MACRO_2(x, y) +(x * y)

    // fixed one parameter '4', expand the macro with '1', '2', '3'
    GTEST_ASSERT_EQ(AIMRTE_INVOKE_WITH(MY_MACRO_2, 1, 4, 1, 2, 3), 24);

#define MY_MACRO_3(x, y, z) +(x * y * z)

    // fixed first two parameters '4' and '5', expand the macro with the remains
    GTEST_ASSERT_EQ(AIMRTE_INVOKE_WITH(MY_MACRO_3, 2, 4, 5, 1, 2, 3), 120);
  }

  {
#define MY_MACRO(idx, x) +(x * idx)

    GTEST_ASSERT_EQ(AIMRTE_INVOKE_INDEX(MY_MACRO, 1, 2, 3), 8);

#define MY_MACRO_2(idx, x, y) +(idx * x * y)

    // fixed one parameter '4', expand the macro with '1', '2', '3'
    GTEST_ASSERT_EQ(AIMRTE_INVOKE_INDEX_WITH(MY_MACRO_2, 1, 4, 1, 2, 3), 32);

#define MY_MACRO_3(idx, x, y, z) +(idx * x * y * z)

    // fixed first two parameters '4' and '5', expand the macro with the remains
    GTEST_ASSERT_EQ(AIMRTE_INVOKE_INDEX_WITH(MY_MACRO_3, 2, 4, 5, 1, 2, 3), 160);
  }
}
}  // namespace aimrte::test
