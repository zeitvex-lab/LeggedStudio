// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./bind.h"
#include <gtest/gtest.h>

namespace aimrte::test
{
class BindTest : public ::testing::Test
{
};

TEST_F(BindTest, BasicUsage)
{
  int g_a = 0;
  std::string g_b;

  auto f = [&](int a, const std::string& b) {
    g_a = a;
    g_b = b;
  };

  trait::bind_<2>(f)(1, "2");
  GTEST_ASSERT_EQ(g_a, 1);
  GTEST_ASSERT_EQ(g_b, "2");

  trait::bind_<1>(f, 3)("4");
  GTEST_ASSERT_EQ(g_a, 3);
  GTEST_ASSERT_EQ(g_b, "4");

  trait::bind_<0>(f, 5, "6")();
  GTEST_ASSERT_EQ(g_a, 5);
  GTEST_ASSERT_EQ(g_b, "6");

  trait::bind<int, std::string>(f)(7, "8");
  GTEST_ASSERT_EQ(g_a, 7);
  GTEST_ASSERT_EQ(g_b, "8");

  trait::bind<int>(f, 9)("10");
  GTEST_ASSERT_EQ(g_a, 9);
  GTEST_ASSERT_EQ(g_b, "10");

  trait::bind(f, 11, "12")();
  GTEST_ASSERT_EQ(g_a, 11);
  GTEST_ASSERT_EQ(g_b, "12");
}
}  // namespace aimrte::test
