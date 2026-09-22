// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./impl.h"
#include <gtest/gtest.h>
#include <string>

namespace aimrte::test
{
class RefTest : public ::testing::Test
{
};

TEST_F(RefTest, BasicUsage)
{
  Ref r1(std::string("12356789abcdefg"));
  Ref r2(r1.ref());

  GTEST_ASSERT_EQ(r1.ref(), r2.ref());
}
}  // namespace aimrte::test
