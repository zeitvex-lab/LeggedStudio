// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./renew.h"
#include "src/test/test.h"
#include <string>

namespace aimrte::test
{
class RenewTest : public TestBase
{
};

TEST_F(RenewTest, BasicUsage)
{
  class MyData
  {
   public:
    explicit MyData(std::string msg) : msg_(std::move(msg))
    {
      std::cout << "create " << msg_ << std::endl;
    }

    ~MyData()
    {
      std::cout << "destroy " << msg_ << std::endl;
    }

   private:
    std::string msg_;
  };

  MyData data("123");
  GTEST_ASSERT_TRUE(ExpectOutputContent("create 123"));

  trait::renew(data, "456");
  GTEST_ASSERT_TRUE(ExpectOutputContent({"destroy 123", "create 456"}));
}
}  // namespace aimrte::test
