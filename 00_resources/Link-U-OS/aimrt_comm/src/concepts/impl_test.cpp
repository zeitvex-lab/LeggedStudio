// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./impl.h"
#include <gtest/gtest.h>

namespace aimrte::test
{
class ConceptsTest : public ::testing::Test
{
};

template <concepts::Function<bool(int, double)>>
constexpr bool TestFunctionConcept()
{
  return true;
}

template <class>
constexpr bool TestFunctionConcept()
{
  return false;
}

template <class F, class... TArgs>
  requires(concepts::ReturnVoidFunction<F, TArgs...>)
constexpr bool TestVoidFunctionConcept()
{
  return true;
}

template <class, class...>
constexpr bool TestVoidFunctionConcept()
{
  return false;
}

TEST_F(ConceptsTest, BasicUsage)
{
  GTEST_ASSERT_TRUE((
    TestFunctionConcept<decltype([](int, double) -> bool {
      return true;
    })>()));

  GTEST_ASSERT_TRUE((
    TestFunctionConcept<decltype([](int, int) -> bool {
      return true;
    })>()));

  GTEST_ASSERT_FALSE(
    TestFunctionConcept<decltype([](int, double) -> void {
    })>());

  GTEST_ASSERT_FALSE((
    TestFunctionConcept<decltype([](std::string, int) -> bool {
      return true;
    })>()));

  GTEST_ASSERT_TRUE((
    TestVoidFunctionConcept<decltype([](int, double) -> void {
                            }),
                            int, double>()));

  GTEST_ASSERT_FALSE((
    TestVoidFunctionConcept<decltype([](int, double) -> int {
                              return 0;
                            }),
                            int, double>()));

  GTEST_ASSERT_FALSE((
    TestVoidFunctionConcept<decltype([](int, double, int) -> void {
                            }),
                            int, double>()));
}
}  // namespace aimrte::test
