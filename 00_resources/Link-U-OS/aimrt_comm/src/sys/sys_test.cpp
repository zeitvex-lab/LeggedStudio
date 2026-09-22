// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include <gtest/gtest.h>
#include <filesystem>
#include <source_location>
#include <thread>

#include "./info.h"
#include "./internal/fs.h"

namespace aimrte::sys::test
{
class SysTest : public ::testing::Test
{
 protected:
  void SetUp() override
  {
    home_ = std::filesystem::path(std::source_location::current().file_name()).parent_path().string() + "/test";
    setenv("AGIBOT_HOME", home_.data(), 1);
  }

 protected:
  std::string home_;
};

TEST_F(SysTest, InternalFs)
{
  GTEST_ASSERT_EQ(internal::GetRoot(), home_ + "/agibot");
  GTEST_ASSERT_EQ(internal::GetInfoRoot(), home_ + "/agibot/data/info");
  GTEST_ASSERT_EQ(internal::GetSysRoot(), home_ + "/agibot/sys");
  GTEST_ASSERT_EQ(internal::GetOTARoot(), home_ + "/agibot/data/ota");
  GTEST_ASSERT_EQ(internal::GetSoftwareRoot(), home_ + "/agibot/software");
  GTEST_ASSERT_EQ(internal::GetLogRoot(), home_ + "/agibot/data/log");
  GTEST_ASSERT_EQ(internal::GetDataRoot(), home_ + "/agibot/data/var");

  GTEST_ASSERT_EQ(internal::GetSNPath(), home_ + "/agibot/data/info/sn");
  GTEST_ASSERT_EQ(internal::GetNamePath(), home_ + "/agibot/data/info/name");
  GTEST_ASSERT_EQ(internal::GetModelPath(), home_ + "/agibot/data/info/model");
  GTEST_ASSERT_EQ(internal::GetSOCIndexPath(), home_ + "/agibot/data/info/soc_index");
}

TEST_F(SysTest, Info)
{
  GTEST_ASSERT_EQ(GetSN(), "TEST_SN_CODE_IS_STRING");
  GTEST_ASSERT_EQ(GetName(), "TEST_ROBOT_NAME_IS_STRING");
  GTEST_ASSERT_EQ(GetModel(), "TEST_MODEL_IS_STRING");
  GTEST_ASSERT_EQ(GetSOCIndex(), 100);
}
}  // namespace aimrte::sys::test
