// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./utils.h"
#include <fstream>

namespace aimrte::sys::details
{
std::string ReadOneLine(const std::string& path)
{
  std::ifstream file(path);
  if (not file.is_open())
    return {};

  std::string content;
  std::getline(file, content);
  return content;
}

void WriteOneLine(const std::string& path, const std::string& content)
{
  std::ofstream file(path);
  if (not file.is_open())
    throw std::runtime_error("unable to write file: " + path);

  if (content.find('\n') != std::string::npos)
    throw std::logic_error("one line file content has \\n !");

  file << content;
}

bool WriteOneLine(const std::string& path, const std::string& content, std::nothrow_t)
try {
  WriteOneLine(path, content);
  return true;
} catch (...) {
  return false;
}
}  // namespace aimrte::sys::details
