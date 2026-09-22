// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/test/test.h"

namespace aimrte::interface_mode
{
class MyTest : public ::testing::Test
{
 protected:
  test::ModuleTestController ctrl;
};

TEST_F(MyTest, BasicUsage)
{
  ctrl.LetRun();
}
}  // namespace aimrte::interface_mode
