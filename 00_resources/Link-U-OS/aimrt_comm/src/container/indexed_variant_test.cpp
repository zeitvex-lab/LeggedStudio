// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./indexed_variant.h"
#include <gtest/gtest.h>
#include <atomic>
#include <string>

namespace aimrte::test
{
class IndexedVariantTest : public ::testing::Test
{
};

TEST_F(IndexedVariantTest, BasicUsage)
{
  IndexedVariant<int, int, int> var;

  var.Emplace<0>(1);

  GTEST_ASSERT_EQ(var.Index(), 0);
  GTEST_ASSERT_EQ(var.Get<0>(), 1);

  var.Emplace<1>(2);
  GTEST_ASSERT_EQ(var.Index(), 1);
  GTEST_ASSERT_EQ(var.Get<1>(), 2);

  var.Emplace<2>(3);
  GTEST_ASSERT_EQ(var.Index(), 2);
  GTEST_ASSERT_EQ(var.Get<2>(), 3);

  var = MakeOfIdx<0>(4);
  GTEST_ASSERT_EQ(var.Index(), 0);
  GTEST_ASSERT_EQ(var.Get<0>(), 4);

  var = MakeOfIdx<1>(5);
  GTEST_ASSERT_EQ(var.Index(), 1);
  GTEST_ASSERT_EQ(var.Get<1>(), 5);

  var = MakeOfIdx<2>(6);
  GTEST_ASSERT_EQ(var.Index(), 2);
  GTEST_ASSERT_EQ(var.Get<2>(), 6);

  IndexedVariant<int, int, int> var2{MakeOfIdx<0>(7)};
  GTEST_ASSERT_EQ(var2.Index(), 0);
  GTEST_ASSERT_EQ(var2.Get<0>(), 7);

  IndexedVariant<int, int, int> var3{std::in_place_index<1>, 8};
  GTEST_ASSERT_EQ(var3.Index(), 1);
  GTEST_ASSERT_EQ(var3.Get<1>(), 8);

  var3.Emplace(std::in_place_index<2>, 9);
  GTEST_ASSERT_EQ(var3.Index(), 2);
  GTEST_ASSERT_EQ(var3.Get<2>(), 9);

  IndexedVariant<int, std::atomic_int, std::atomic_bool, std::string> var4{MakeOfIdx<1>(10)};
  GTEST_ASSERT_EQ(var4.Index(), 1);
  GTEST_ASSERT_EQ(var4.Get<1>().load(), 10);

  static_assert(std::is_copy_assignable_v<IndexedVariant<int, int, std::string>>);
  static_assert(not std::is_copy_assignable_v<IndexedVariant<std::atomic_int, int, std::string>>);

  struct Node {
    explicit Node(const int n) : value(n) {}

    const int value;
  };

  static_assert(not std::is_default_constructible_v<Node>);
  static_assert(not std::is_default_constructible_v<IndexedVariant<Node, int>>);
  static_assert(std::is_default_constructible_v<IndexedVariant<int, Node>>);

  IndexedVariant<Node, int> var6{MakeOfIdx<0>(11)};
  GTEST_ASSERT_EQ(var6.Index(), 0);
  GTEST_ASSERT_EQ(var6.Get<0>().value, 11);
}

TEST_F(IndexedVariantTest, Visit)
{
  IndexedVariant<int, std::atomic_int, std::atomic_bool, std::string> var{MakeOfIdx<1>(10)};

  auto get_value = [&]() -> int {
    return var.Visit(
      []<class T>(const std::size_t index, T& data) {
        if constexpr (std::is_same_v<std::atomic_int, T>) {
          if (index == 1)
            return data.load();
          else
            return -1;
        } else
          return -2;
      });
  };

  GTEST_ASSERT_EQ(get_value(), 10);

  var.Visit(
    []<class T>(const std::size_t index, T& data) {
      if constexpr (std::is_same_v<std::atomic_int, T>)
        data.store(11);
    });

  GTEST_ASSERT_EQ(get_value(), 11);

  const auto& var2 = var;
  var2.Visit(
    []<class T>(const std::size_t, T& data) {
      static_assert(std::is_const_v<T>);
    });

  var             = MakeOfIdx<3>("hello world");
  auto get_string = [&]() -> std::string {
    return var.Visit(
      []<class T>(const std::size_t index, T& data) -> std::string {
        if constexpr (std::is_same_v<std::string, T>) {
          if (index == 3)
            return data;
          else
            return "-1";
        } else
          return "-2";
      });
  };

  GTEST_ASSERT_EQ(get_string(), "hello world");
  const std::string value = std::move(var).Visit(
    []<class T>(const std::size_t index, T&& data) -> std::string {
      if constexpr (std::is_same_v<std::string, T>)
        return std::move(data);
      else
        return {};
    });

  GTEST_ASSERT_EQ(value, "hello world");
  GTEST_ASSERT_EQ(get_string(), "");
}
}  // namespace aimrte::test
