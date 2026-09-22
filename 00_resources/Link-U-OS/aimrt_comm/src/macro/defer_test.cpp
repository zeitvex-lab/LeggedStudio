// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./defer.h"
#include <gtest/gtest.h>

namespace aimrte::test
{
class DeferTest : public ::testing::Test
{
};

TEST_F(DeferTest, BasicUsage)
{
  int x = 1;

  {
    AIMRTE(defer(x = 2));
    GTEST_ASSERT_EQ(x, 1);
  }

  GTEST_ASSERT_EQ(x, 2);
}
}  // namespace aimrte::test
