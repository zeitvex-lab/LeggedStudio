// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./const_cast.h"

#include "src/test/test.h"
#include <gtest/gtest.h>
#include <iostream>

namespace aimrte::test
{
class ConstCastTest : public TestBase
{
};

TEST_F(ConstCastTest, BasicUsage)
{
  struct {
    void Say() const
    {
      std::cout << "const" << std::endl;
    }

    void Say()
    {
      std::cout << "non" << std::endl;
    }
  } obj;

  const auto& const_obj = obj;

  obj.Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("non"));

  trait::add_const(obj).Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("const"));

  const_obj.Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("const"));

  trait::remove_const(const_obj).Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("non"));

  trait::add_const(&obj)->Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("const"));

  trait::remove_const(&const_obj)->Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("non"));

  trait::remove_const(obj).Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("non"));

  trait::add_const(const_obj).Say();
  GTEST_ASSERT_TRUE(ExpectOutputContent("const"));
}
}  // namespace aimrte::test
