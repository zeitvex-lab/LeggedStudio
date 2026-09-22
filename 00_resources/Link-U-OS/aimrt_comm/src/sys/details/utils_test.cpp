// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./utils.h"
#include <gtest/gtest.h>
#include <filesystem>

namespace aimrte::sys::details::test
{
class UtilsTest : public ::testing::Test
{
};

TEST_F(UtilsTest, BasicUsage)
{
  const std::string path = "sys_utils_test.txt";
  std::filesystem::remove(path);

  WriteOneLine(path, "abc");
  GTEST_ASSERT_EQ(ReadOneLine(path), "abc");

  GTEST_ASSERT_TRUE(WriteOneLine(path, "edf", std::nothrow));
  GTEST_ASSERT_EQ(ReadOneLine(path), "edf");

  GTEST_ASSERT_FALSE(WriteOneLine(path, "123\n456", std::nothrow));
}
}  // namespace aimrte::sys::details::test
