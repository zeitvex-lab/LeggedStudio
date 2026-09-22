// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./interface.h"
#include <gtest/gtest.h>

namespace aimrte::impl
{
template <>
void Convert(const int& src, std::string& dst)
{
  dst = std::to_string(src);
}

template <>
void Convert(const std::string& src, double& dst)
{
  dst = std::stod(src);
}
}  // namespace aimrte::impl

namespace aimrte::test
{
class ConvertTest : public ::testing::Test
{
};

TEST_F(ConvertTest, from_to)
{
  GTEST_ASSERT_EQ("123", convert::From<int>(123).To<std::string>());
  GTEST_ASSERT_EQ("123", convert::From(123).To<std::string>());
  GTEST_ASSERT_EQ("123", convert::To<std::string>(123));

  GTEST_ASSERT_EQ(1.0, convert::From<std::string>("1.0").To<double>());
}

TEST_F(ConvertTest, by)
{
  std::string dst;
  convert::By<std::string>::FromOriginal<int>()(123, dst);
  GTEST_ASSERT_EQ("123", dst);

  convert::By<int>::ToOriginal<std::string>()(456, dst);
  GTEST_ASSERT_EQ("456", dst);

  constexpr auto f = convert::By<int>::ToOriginal<std::string>();

  auto ff = []() {
    std::string dst;
    f(789, dst);
    GTEST_ASSERT_EQ("789", dst);
  };

  ff();
}
}  // namespace aimrte::test
