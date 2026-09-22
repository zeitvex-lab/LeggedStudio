// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "executor.h"

#include <iostream>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <dirent.h>
#include "src/common/util/log_util.h"

#include "src/util/process_log.h"

namespace process_manager
{

void Executor::Reset() {
  merge_env_var_.clear();
  prepare_args_list_.clear();
  stdout_path_.clear();
  stderr_path_.clear();
}

bool Executor::Init() {
  stdout_path_ = info_.stdout_path;
  stderr_path_ = info_.stderror_path;
  MergeAppEnv();
  MergeArgsList();

  return true;
}


bool Executor::UpdateEnvCfg(const std::string& key, const std::string& val) {
  do
  {
    if (key == "stdout") {
      stdout_path_ = val;
      break;
    } else if (key == "stderr") {
      stderr_path_ = val;
      break;
    }

    return false;
  } while (false);

  return true;
}


ProcessErrorCode Executor::ExecutorValidate() {
  std::string path_name = info_.app_file_path;
  auto fs_path = std::filesystem::path(path_name);

  if (path_name.find('/') != std::string::npos)  {
    if (CheckExecutor(fs_path)) {
      return ProcessErrorCode::SUCCESS;
    }
  }

  for (const auto& path_str : info_.path_env) {
    std::filesystem::path new_fs_path = std::filesystem::path(path_str) / path_name;
    if (CheckExecutor(new_fs_path)) {
      return ProcessErrorCode::SUCCESS;
    }
  }

  return ProcessErrorCode::EXECUTOR_CHECK_ERROR;
}


ProcessErrorCode Executor::PrepareExecution()
{
  if (!SetEnv()) {
    return ProcessErrorCode::SET_ENV_ERROR;
  }

  if (!SetStdoutStdErr()) {
    return ProcessErrorCode::SET_STDOUT_STDERR_ERROR;
  }

  if (!SetSession()) {
    return ProcessErrorCode::SET_SESSION_ERROR;
  }

  // 执行之后无法打印出 domain socket 日志
  // 需要放在 SetUser 之前, 因为将失去root权限, 导致部分部分日志无法在当前进程落盘
  CleanFdFromParent();

  if (!SetUser()) {
    return ProcessErrorCode::SET_USER_ERROR;
  }

  return ProcessErrorCode::SUCCESS;
}


bool Executor::StartExec() {
  std::vector<char*> args;
  for (auto& ss : prepare_args_list_) {
    args.push_back(const_cast<char*>(ss.c_str()));
  }

  args.push_back(const_cast<char*>(info_.app_file_path.c_str()));

  for (auto& s : info_.args_list) {
    args.push_back(const_cast<char*>(s.c_str()));
  }
  // 需要添加 NULL 结尾
  args.push_back(nullptr);

  ::execvp(args[0], args.data());

  AIMRT_ERROR_P("execvp failed, args list:");
  int argc = 0;
  for (auto e : args) {
    AIMRT_ERROR_P("args[{}]: {}", argc++, e);
  }
  return false;
}

void Executor::PrintExecutorArgs() {
  // prepare_args_list_
  std::string args_list_str;
  for (auto & str : prepare_args_list_) {
    args_list_str += (str + " ");
  }
  // info_.app_file_path
  args_list_str += (info_.app_file_path + " ");

  // info info_.args_list
  for (auto & str : info_.args_list) {
    args_list_str += (str + " ");
  }

  std::string env_str;
  env_str += (args_list_str + "\n");

  // env: merge_env_var_
  for (auto &[key, val] : merge_env_var_) {
    env_str += (key + ": " + val + "\n");
  }

  // stdout_path_
  // stderr_path_
  env_str += ("stdout: " + stdout_path_ + "\n");
  env_str += ("stderr: " + stderr_path_);

  AIMRT_INFO("[{}] env_str :\n{}", info_.app_name, env_str);
}

bool Executor::CheckExecutor(const std::filesystem::path& path) {
  if (!std::filesystem::exists(path)) {
    AIMRT_DEBUG_P("path: {} is not exists", path.string());
    return false;
  }

  if (!std::filesystem::is_regular_file(path)) {
    AIMRT_DEBUG_P("path: {} is not regular file", path.string());
    return false;
  }

  // 检查执行权限
  if (::access(path.c_str(), X_OK) != 0) {
    AIMRT_DEBUG_P("path: {} not has access right", path.string());
    return false;
  }

  return true;
};


#define LOG_PATH     "LOG_PATH"
#define ROS_LOG_DIR  "ROS_LOG_DIR"
#define EM_APP_NAME  "EM_APP_NAME"
#define AGIBOT_HOME  "AGIBOT_HOME"

void Executor::MergeAppEnv() {
  // 如果app在启动脚本的配置中, 制定了环境变量, 则直接覆盖xml原有的
  merge_env_var_ = info_.env_map;
  for (auto& ele : env_var_) {
    if (merge_env_var_.find(ele.first) == merge_env_var_.end()) {
      merge_env_var_[ele.first] = ele.second;
    }
  }

  // set  LOG_PATH & ROS_LOG_DIR & EM_APP_NAME
  std::string log_path_str;
  if (merge_env_var_.find(LOG_PATH) == merge_env_var_.end()) {
    const char* agibot_home = std::getenv(AGIBOT_HOME);
    if (agibot_home == nullptr) agibot_home = "";

    log_path_str = ::aimrt_fmt::format("{}/agibot/data/log/{}", agibot_home, info_.app_name);
    merge_env_var_[LOG_PATH] = log_path_str;
  } else {
    log_path_str = merge_env_var_[LOG_PATH];
  }

  if (merge_env_var_.find(ROS_LOG_DIR) == merge_env_var_.end()) {
    std::string ros_log_str = ::aimrt_fmt::format("{}/ros", log_path_str);
    merge_env_var_[ROS_LOG_DIR] = ros_log_str;
  }

  if (merge_env_var_.find(EM_APP_NAME) == merge_env_var_.end()) {
    merge_env_var_[EM_APP_NAME] = info_.app_name;
  }
}

void Executor::MergeArgsList() {
  // 先填充 sudo -u #1001 -g #1001 --preserve-env=ROS_LOCALHOST_ONLY... 等信息
  std::string preserve_env{"--preserve-env="};
  preserve_env += base_preserve_env_;

  for (auto& ele : merge_env_var_) {
    preserve_env += ",";
    preserve_env += ele.first;
  }
  // AIMRT_DEBUG("app: {}, preserve_env: {}", info_.app_name, preserve_env);

  uid_t target_uid = info_.user_gid;
  gid_t target_gid = info_.user_gid;

  // sudo 的时候设置
  if (info_.use_sudo) {
    target_gid = 0;
    target_uid = 0;
  }

  std::string gid_str = ::aimrt_fmt::format("#{}", target_gid);
  std::string uid_str = ::aimrt_fmt::format("#{}", target_uid);

  // yes, 启动的程序名称是 sudo.
  prepare_args_list_.emplace_back("sudo");
  prepare_args_list_.emplace_back("-u");
  prepare_args_list_.emplace_back(uid_str);
  prepare_args_list_.emplace_back("-g");
  prepare_args_list_.emplace_back(gid_str);
  prepare_args_list_.emplace_back(std::move(preserve_env));
}


bool Executor::SetUser()
{
  uid_t target_uid = info_.user_gid;
  gid_t target_gid = info_.user_gid;

  // sudo 的时候设置
  if (info_.use_sudo) {
    target_gid = 0;
    target_uid = 0;
  }

  if (::setgid(target_gid) == -1) {
    AIMRT_ERROR_P("SetGid failed. {}", info_.app_name);
    return false;
  }

  if (::setuid(target_uid) == -1) {
    AIMRT_ERROR_P("SetUid failed. {}", info_.app_name);
    return false;
  }

  return true;
}

bool Executor::SetEnv()
{
  // 使用 execvp 替换进程, 所以需要提前设置好环境变量
  for (const auto& [key, val] : merge_env_var_) {
    // 覆盖已经存在的环境变量
    ::setenv(key.c_str(), val.c_str(), 1);
  }
  return true;
}


// 打开或创建文件，返回 fd；失败抛 runtime_error
int open_or_create(const std::string& path)
{
  try {
    if (auto dir = std::filesystem::path(path).parent_path(); !dir.empty())
      std::filesystem::create_directories(dir);
  } catch (const std::filesystem::filesystem_error& e) {
    throw std::runtime_error("create_directories: " + std::string(e.what()));
  }

  int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_APPEND, 0644);
  if (fd == -1)
    throw std::runtime_error("open " + path + ": " + strerror(errno));
  return fd;
}

// 重定向 fd to 指定文件；失败时 fallback 到 /dev/null
bool redirect_fd(int target_fd, const std::string& path)
{
  int new_fd = -1;

  try {
    if (!path.empty())
      new_fd = open_or_create(path);
  } catch (const std::runtime_error& e) {
    AIMRT_WARN_P("open {} failed: {}, fallback to /dev/null", path, e.what());
  }

  if (new_fd == -1) {
    new_fd = ::open("/dev/null", O_WRONLY);
    if (new_fd == -1) {
      AIMRT_ERROR_P("fallback open /dev/null also failed: {}",  strerror(errno));
      return false;
    }
  }

  if (::dup2(new_fd, target_fd) == -1) {
    AIMRT_ERROR_P("dup2 failed: {}, new_fd: {}, target_fd: {}", strerror(errno), new_fd, target_fd);
    return false;
  }

  ::close(new_fd);   // 关闭临时描述符，重定向已完成
  return true;
}

bool Executor::SetStdoutStdErr()
{
  if (!redirect_fd(STDOUT_FILENO, stdout_path_)) {
    return false;
  }

  if (!redirect_fd(STDERR_FILENO, stderr_path_)) {
    return false;
  }

  return true;
}

bool Executor::SetSession()
{
  if (::setsid() == -1) {
    AIMRT_ERROR_P("SetSid failed. {}", info_.app_name);
    return false;
  }
  return true;
}

// 需要在exec之前, 将所有 socket 相关的fd全部关闭, 避免出现端口占用的问题
// 注: 也会关闭 domain socket的fd, 之后将无法输出日志
void Executor::CleanFdFromParent() {
  DIR* d = ::opendir("/proc/self/fd");
  if (!d) {
    AIMRT_ERROR_P("opendir self/fd failed. {}", info_.app_name);
    return;
  }

  std::vector<int> fd_list;
  struct dirent* de;
  while ((de = ::readdir(d))) {
    //  过滤 . 和 ..
    if (de->d_name[0] == '.')
      continue;

    // 270 = 256 + 14, ignore warning
    char lnk[270] = {0};
    snprintf(lnk, sizeof(lnk), "/proc/self/fd/%s", de->d_name);
    char target[256] = {0};
    ssize_t n = ::readlink(lnk, target, sizeof(target) -1);
    if (n < 0) {
      AIMRT_ERROR_P("readlink error. link: {}, {}", lnk, info_.app_name);
      continue;
    }

    try
    {
      std::string target_str(target);
      if (target_str.find("socket") != std::string::npos) {
        fd_list.emplace_back(std::stol(de->d_name));
        // AIMRT_DEBUG_P("find socket fd: {} {} {}", de->d_name, target_str, info_.app_name);
      }
    }
    catch(const std::exception& e)
    {
      AIMRT_ERROR_P("stol failed. d_name: {}, {}", de->d_name, info_.app_name);
    }
  }
  ::closedir(d);

  AIMRT_INFO_P("ready clean old fd size: {} {}", fd_list.size(), info_.app_name);
  for (auto& fd : fd_list) {
    ::close(fd);
  }
}

}
