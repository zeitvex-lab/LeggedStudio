// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./test_base.h"
#include <fstream>
#include <ranges>

namespace aimrte::test
{
void TestBase::SetUp()
{
  // 重定向 std::cout 到我们的缓冲区中，用于日志内容分析
  old_cout_buffer_ptr = std::cout.rdbuf();
  std::cout.rdbuf(output_buffer_.rdbuf());

  // 执行子类初始化过程
  OnSetup();
}

void TestBase::TearDown()
{
  // 执行子类关闭过程
  OnTearDown();

  // 将我们的缓冲区中剩余内容输出，并恢复 std::cout
  std::cout.rdbuf(old_cout_buffer_ptr);
  std::cout << output_buffer_.str() << std::endl;
  output_buffer_.str("");
}

bool TestBase::ExpectOutputContent(const std::string& str)
{
  return ExpectOutputContent({str});
}

bool TestBase::ExpectOutputContent(const std::initializer_list<std::string>& strs)
{
  const std::string content = output_buffer_.str();

  // 检查是否有给定内容
  const bool status = not std::ranges::any_of(
    strs,
    [&](const std::string& str) {
      return content.find(str) == std::string::npos;
    });

  // 恢复 cout ，将当前内容输出，然后继续后续分析
  std::cout.rdbuf(old_cout_buffer_ptr);
  std::cout << content << std::flush;

  output_buffer_.str("");
  std::cout.rdbuf(output_buffer_.rdbuf());

  // 返回刚才的检查结果
  return status;
}
}  // namespace aimrte::test
