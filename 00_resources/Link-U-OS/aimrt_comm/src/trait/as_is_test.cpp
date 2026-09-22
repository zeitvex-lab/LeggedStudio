// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./as_is.h"
#include <gtest/gtest.h>

namespace aimrte::trait::test
{
class AsIsTest : public ::testing::Test
{
};

TEST_F(AsIsTest, BasicUsag)
{
  struct MyData {
    int f() &
    {
      return 1;
    }

    int f() &&
    {
      return 2;
    }
  };

  auto x = MyData();
  GTEST_ASSERT_EQ(as_is<decltype(x)>(x).f(), 1);

  auto&& y = MyData();
  GTEST_ASSERT_EQ(as_is<decltype(y)>(y).f(), 2);

  auto&& z = x;
  GTEST_ASSERT_EQ(as_is<decltype(z)>(z).f(), 1);
}
}  // namespace aimrte::trait::test
