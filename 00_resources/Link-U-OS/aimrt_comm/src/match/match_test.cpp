// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/match/match.h"
#include "src/test/test.h"

namespace aimrte::test
{
class MatchTest : public TestBase
{
};

struct MyClass {
  MyClass()
  {
    std::cout << "MyClass()" << std::endl;
  }

  MyClass(const MyClass&)
  {
    std::cout << "MyClass(copy)" << std::endl;
  }

  MyClass(MyClass&&) noexcept
  {
    std::cout << "MyClass(move)" << std::endl;
  }

  MyClass& operator=(const MyClass&)
  {
    std::cout << "MyClass=(copy)" << std::endl;
    return *this;
  }

  MyClass& operator=(MyClass&&) noexcept
  {
    std::cout << "MyClass=(move)" << std::endl;
    return *this;
  }

  ~MyClass()
  {
    std::cout << "~MyClass()" << std::endl;
  }
};

AIMRTE_ENUM_CLASS(
  XX,
  (A, int, double),
  (B, bool, MyClass),
  (C, std::string, int, std::string));

TEST_F(MatchTest, CreateAndCopy)
{
  XX a = XX::A(1, 2);
  XX c(a);

  // default construct is deleted
  // XX x;

  XX b = XX::B(true, MyClass());
  GTEST_ASSERT_TRUE(ExpectOutputContent({"MyClass()", "MyClass(move)"}));

  a = b;
  GTEST_ASSERT_TRUE(ExpectOutputContent("MyClass(copy)"));
}

TEST_F(MatchTest, Match)
{
  XX a = XX::A(1, 2);

  auto match_once = [&] {
    match(a) |
      trait::impl{
        XX::A | [](int& x, const double y) {
          ++x;
          std::cout << x << " " << y << std::endl;
        },
        XX::B | [](const bool z, MyClass&) {
          std::cout << "match lvalue: " << z << std::endl;
        },
        XX::C | [](const std::string& x, int, const std::string&) {
          std::cout << x << std::endl;
        },
      };
  };

  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("2 2"));

  a = XX::B(true, MyClass{});
  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("match lvalue: 1"));

  a = XX::C("abc", 3, "edf");
  match_once();
  GTEST_ASSERT_TRUE(ExpectOutputContent("abc"));
}

TEST_F(MatchTest, MatchWithReturnValue)
{
  const double r =
    match(XX::C("abc", 30, "edf")) |
    trait::impl{
      XX::A | [](int, double) {
        return 1.1;
      },
      XX::B | [](bool, auto) {
        // return true; // all arms should have the same return type
        return 2.2;
      },
      XX::C | [](std::string&& a, const int b, std::string&& c) {
        return 3.3;
      },
    };

  GTEST_ASSERT_EQ(r, 3.3);
}

TEST_F(MatchTest, MatchByMacro)
{
  XX c = XX::A(1, 2);

  AIMRTE(match(c))
  {
    case AIMRTE(as(XX::A), then(int x, double y)) {
      GTEST_ASSERT_EQ(x, 1);
      GTEST_ASSERT_EQ(y, 2.0);
    } break;

      default: {
      GTEST_FAIL();
    }
  }
}

TEST_F(MatchTest, IfLet)
{
  XX c = XX::A(1, 2);

  ifLet(c) = XX::B | [](auto, auto) {
    std::cout << "c is not XX::B !" << std::endl;
  };
  GTEST_ASSERT_TRUE(not ExpectOutputContent("B"));

  ifLet(c) = XX::A | [](int& x, const double y) {
    ++x;
    std::cout << "if let lvalue: " << x << " " << y << std::endl;
  };
  GTEST_ASSERT_TRUE(ExpectOutputContent("if let lvalue: 2 2"));

  ifLet(XX::C("qqq", 40, "xxx")) = XX::C | [](auto&& x, auto&& y, auto&& z) {
    std::cout << "if let rvalue " << x << " " << y << " " << z << std::endl;
  };
  GTEST_ASSERT_TRUE(ExpectOutputContent("if let rvalue qqq 40 xxx"));

  // if let with boolean condition cascading judgment
  ifLet(c) | XX::B | [](auto, auto) {
    std::cout << "c is not XX::B ! Somehing wrong !" << std::endl;
  } or
    ifLet(c) | XX::A | [](int& x, const double y) {
      ++x;
      std::cout << "if let use >: " << x << " " << y << std::endl;
    };

  GTEST_ASSERT_TRUE(ExpectOutputContent(">:"));

  // use trait::otherwise to handle the 'else' case
  ifLet(c) | XX::B | [](auto, auto) {
    std::cout << "c is not XX::B ! Somehing wrong !" << std::endl;
  } or
    trait::otherwise{
      []() {
        std::cout << "c is not XX::B. Everything good !" << std::endl;
      },
    };
  GTEST_ASSERT_TRUE(ExpectOutputContent("good"));
}

TEST_F(MatchTest, IfLetByMacro)
{
  auto if_let_rvalue = []() -> int {
    if AIMRTE (let(XX::A(1, 2)), as(XX::A), then(int&& x, const double y)) {
      return x + y;
    }

    return 0;
  };

  GTEST_ASSERT_EQ(if_let_rvalue(), 3);

  auto if_let_lvalue = []() -> int {
    XX x = XX::A(3, 4);

    if AIMRTE (let(x), as(XX::A), then(int& x, double y)) {
      return x + y;
    }

    return 0;
  };

  GTEST_ASSERT_EQ(if_let_lvalue(), 7);

  auto if_let_else = []() -> int {
    XX x = XX::A(3, 4);

    if AIMRTE (let(x), as(XX::B), then(bool x, MyClass y)) {
      return 1;
    } else {
      return 2;
    }
  };

  GTEST_ASSERT_EQ(if_let_else(), 2);
}

template <class TValue, class TError>
AIMRTE_ENUM_TEMPLATE_CLASS(
  Expected,
  (TValue, TError),
  (Value, TValue),
  (Error, TError));

TEST_F(MatchTest, TemplateEnumClass)
{
  Expected x = Expected<int, float>::Value(1);

  ifLet(x) = Expected<int, float>::Value | [](int& x) {
    std::cout << ++x << std::endl;
  };

  GTEST_ASSERT_TRUE(ExpectOutputContent("2"));

  match(x) |
    trait::impl{
      Expected<int, float>::Value | [](int& x) {
        std::cout << ++x << std::endl;
      },
      Expected<int, float>::Error | [](double x) {
        std::cout << ++x << std::endl;
      },
    };

  GTEST_ASSERT_TRUE(ExpectOutputContent("3"));
}

TEST_F(MatchTest, Is)
{
  XX x = XX::B(true, MyClass());

  GTEST_ASSERT_TRUE(x.is(XX::B));
  GTEST_ASSERT_FALSE(x.is(XX::C));
}

TEST_F(MatchTest, AllKindsOfOperands)
{
  std::string lvalue;
  const std::string const_lvalue;

  XX x = XX::C(lvalue, 2, const_lvalue);
  GTEST_ASSERT_TRUE(x.is(XX::C));
}

TEST_F(MatchTest, TemplateIfLetByMacro)
{
  Expected x = Expected<int, float>::Value(1);

  if AIMRTE (let(x), as(Expected<int, float>::Value), then(int x)) {
    GTEST_ASSERT_EQ(x, 1);
  } else {
    GTEST_FAIL();
  }

  if AIMRTE (let(x), as(Expected<int, float>::Error), then(float x)) {
    GTEST_FAIL();
  }
}
}  // namespace aimrte::test
