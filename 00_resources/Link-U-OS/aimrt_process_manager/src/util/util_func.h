// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>

#include <string>

namespace process_manager {

uint64_t GetCurrentMilliSecondTimestamp();

uint64_t GetCurrentNanoSecondTimestamp();

std::string GetNanoSecondTimestampStr(uint64_t timestamp);

std::string GetLocalSecondTimestampStr(uint64_t timestamp);

bool CreateFileDir(const std::string& dir);

std::string GetLocalFileData(const std::string& path);

}
