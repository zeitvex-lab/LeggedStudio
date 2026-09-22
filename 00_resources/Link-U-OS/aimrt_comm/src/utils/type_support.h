// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <algorithm>
#include <filesystem>
#include <string>
#include <sstream>
#include <unordered_map>
#include <vector>

namespace aimrte::utils
{
template <typename PathT>
bool GetTypeSupportPkgs(const std::string& ld_library_path, std::vector<PathT>& type_support_pkgs)
{
  if (ld_library_path.empty()) {
    return false;
  }
  std::stringstream ss(ld_library_path);
  std::string path;
  while (std::getline(ss, path, ':')) {
    if (path.empty() || !std::filesystem::exists(path) || !std::filesystem::is_directory(path)) {
      continue;
    }
    try {
      for (const auto& entry : std::filesystem::directory_iterator(path)) {
        if (entry.is_regular_file() && entry.path().extension() == ".so" &&
            entry.path().filename().string().find("type_support") != std::string::npos &&
            std::find_if(type_support_pkgs.begin(), type_support_pkgs.end(), [&entry](const PathT& item) {
              return item.path == entry.path().filename().string();
            }) == type_support_pkgs.end()) {
          type_support_pkgs.push_back({entry.path().filename().string()});
        }
      }
    } catch (const std::filesystem::filesystem_error& ex) {
    }
  }
  return true;
}

bool GetTopicMetaList(const std::string& yaml_path, std::unordered_map<std::string, std::string>& topic_map);
}  // namespace aimrte::utils
