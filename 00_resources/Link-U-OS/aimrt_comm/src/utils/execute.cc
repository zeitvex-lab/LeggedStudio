// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./execute.h"
namespace aimrte::utils
{

int Execute(std::string_view cmd, std::string &result)
{
  try {
    char buffer[255];
    FILE *pipe = popen(cmd.data(), "r");
    if (!pipe) {
      result = "popen failed！";
      return 1;
    }
    while (!feof(pipe)) {
      if (fgets(buffer, 255, pipe) != NULL) {
        result += buffer;
      }
    }
    int status = pclose(pipe);
    if (status != 0) {
      result = "Command executed failed with exit status: " + std::to_string(WEXITSTATUS(status));
      return status;
    }
  } catch (const std::exception &e) {
    result = "Error executing command:{} " + std::string(e.what());
    return 1;
  }
  return 0;
}

}  // namespace aimrte::utils
