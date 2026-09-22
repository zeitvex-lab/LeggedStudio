// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <openssl/crypto.h>  // OPENSSL_cleanse
#include <openssl/evp.h>
#include <openssl/kdf.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include "sqlite3.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <array>
#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>
#include "src/ctx/anytime.h"
namespace aimrte::database::security
{

extern "C" {
int sqlite3_key_v2(sqlite3 *, const char *, const void *, int);
}

namespace fs = std::filesystem;

constexpr char MAGIC[]     = "AGI-WRAP";
constexpr size_t MAGIC_LEN = 8;
constexpr size_t SALT_LEN  = 16;
constexpr size_t IV_LEN    = 12;
constexpr size_t TAG_LEN   = 16;
constexpr size_t MK_LEN    = 32;  // 主密钥 256bit

static_assert(MAGIC_LEN == sizeof(MAGIC) - 1, "MAGIC_LEN mismatch");

/**
 * @brief 错误码枚举
 */
enum class SecurityError {
  SUCCESS = 0,
  RANDOM_GENERATION_FAILED,
  DEVICE_ID_GENERATION_FAILED,
  HKDF_FAILED,
  AES_ENCRYPTION_FAILED,
  AES_DECRYPTION_FAILED,
  FILE_READ_FAILED,
  FILE_WRITE_FAILED,
  INVALID_FILE_FORMAT,
  DATABASE_OPEN_FAILED,
  DATABASE_KEY_FAILED,
  DATABASE_VERIFICATION_FAILED,
  NETWORK_INTERFACE_NOT_FOUND,
  MAC_ADDRESS_NOT_FOUND
};

// OpenSSL RAII 智能指针
using MD_CTX_ptr     = std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>;
using CIPHER_CTX_ptr = std::unique_ptr<EVP_CIPHER_CTX, decltype(&EVP_CIPHER_CTX_free)>;
using PKEY_CTX_ptr   = std::unique_ptr<EVP_PKEY_CTX, decltype(&EVP_PKEY_CTX_free)>;

// SQLite 智能指针
using SQLite3_ptr      = std::unique_ptr<sqlite3, decltype(&sqlite3_close)>;
using SQLite3_stmt_ptr = std::unique_ptr<sqlite3_stmt, decltype(&sqlite3_finalize)>;

// 设备指纹类型别名
using DeviceId  = std::array<unsigned char, 32>;
using DeviceKey = std::array<unsigned char, 32>;
using Noise     = std::array<unsigned char, 16>;

/*
 * 加密文件结构
 * | MAGIC(8) | SALT(16) | IV(12) | TAG(16) | CT(32) |
 */
struct WrapBlob {
  char magic[MAGIC_LEN];
  std::array<unsigned char, SALT_LEN> salt{};
  std::array<unsigned char, IV_LEN> iv{};
  std::array<unsigned char, TAG_LEN> tag{};
  std::array<unsigned char, MK_LEN> ct{};
  std::array<unsigned char, 16> noise{};

  // 构造函数确保magic字段正确初始化
  WrapBlob()
  {
    std::memcpy(magic, MAGIC, MAGIC_LEN);
  }

  // 验证magic字段
  bool is_valid() const
  {
    return std::memcmp(magic, MAGIC, MAGIC_LEN) == 0;
  }
};

/**
 * @brief 文件写入类
 */
class SecureFileWriter
{
 private:
  int fd_;
  bool closed_;

 public:
  SecureFileWriter(const fs::path &path) : fd_(-1), closed_(false)
  {
    fd_ = ::open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
  }

  ~SecureFileWriter()
  {
    close();
  }

  bool is_open() const { return fd_ >= 0; }

  bool write(const void *data, size_t size)
  {
    if (!is_open() || !data || size == 0) return false;

    const char *ptr = static_cast<const char *>(data);
    size_t written  = 0;

    while (written < size) {
      ssize_t result = ::write(fd_, ptr + written, size - written);
      if (result < 0) {
        if (errno == EINTR) continue;
        return false;
      }
      written += static_cast<size_t>(result);
    }
    return true;
  }

  bool sync()
  {
    return is_open() && ::fsync(fd_) == 0;
  }

  void close()
  {
    if (is_open() && !closed_) {
      ::close(fd_);
      closed_ = true;
    }
  }

  // 禁用拷贝
  SecureFileWriter(const SecureFileWriter &)            = delete;
  SecureFileWriter &operator=(const SecureFileWriter &) = delete;
};

/**
 * @brief 生成随机字节
 * @param p 输出缓冲区
 * @param n 字节数
 * @return 是否成功
 */
bool random_bytes(unsigned char *p, size_t n);

/**
 * @brief 计算 SHA256 哈希
 * @param data 输入数据
 * @param n 数据长度
 * @param out 输出缓冲区
 */
void sha256(const unsigned char *data, size_t n, unsigned char out[32]);

/**
 * @brief 安全的字符串转换（移除冒号并转大写）
 * @param input 输入字符串
 * @return 处理后的字符串
 */
std::optional<std::string> normalize_mac_address(std::string s);

/**
 * @brief 读取并去除尾部空白字符
 * @param p 文件路径
 * @return 读取到的字符串
 */
std::optional<std::string> read_text_trim(const fs::path &p);

/**
 * @brief 获取默认路由的网卡名
 * @return 网卡名
 */
std::optional<std::string> get_default_iface();

/**
 * @brief 获取网卡的 MAC 地址
 * @param ifname 网卡名
 * @return MAC 地址
 */
std::optional<std::string> get_mac_for_iface(const std::string &ifname);

/**
 * @brief 生成设备指纹
 * @param devid 输出缓冲区
 * @return 是否成功
 */
bool make_devid(DeviceId &devid);

/**
 * @brief 生成扰动值
 * @param disturbance 扰动值
 * @return 是否成功
 */
bool make_shift_salt(std::array<unsigned char, 32> &disturbance, std::array<unsigned char, 16> &noise);

/**
 * @brief 读取加密文件
 * @param path 文件路径
 * @param blob 输出缓冲区
 * @return 是否成功
 */
bool read_wrap(const fs::path &path, WrapBlob &blob);

/**
 * @brief 写入加密文件
 * @param path 文件路径
 * @param blob 输入缓冲区
 * @return 是否成功
 */
bool write_wrap(const fs::path &path, const WrapBlob &blob);
/**
 * @brief 生成设备密钥
 * @param devid 设备指纹
 * @param salt 加密文件的盐
 * @param devk 输出缓冲区
 * @return 是否成功
 */
bool hkdf_devk(const DeviceId &devid, const std::array<unsigned char, SALT_LEN> &salt, const std::array<unsigned char, 32> &disturbance, DeviceKey &devk);

/**
 * @brief AES-GCM 加密
 * @param key 加密密钥
 * @param pt 明文数据
 * @param ptlen 明文长度
 * @param iv 初始化向量（输出）
 * @param tag 认证标签（输出）
 * @param ct 密文数据（输出）
 * @return 是否成功
 */
bool aes_gcm_encrypt(const DeviceKey &key, const unsigned char *pt, size_t ptlen, std::array<unsigned char, IV_LEN> &iv, std::array<unsigned char, TAG_LEN> &tag, unsigned char *ct);

/**
 * @brief AES-GCM 解密
 * @param key 解密密钥
 * @param ct 密文数据
 * @param ctlen 密文长度
 * @param iv 初始化向量
 * @param tag 认证标签
 * @param pt 明文数据（输出）
 * @return 是否成功
 */
bool aes_gcm_decrypt(const DeviceKey &key, const unsigned char *ct, size_t ctlen, const std::array<unsigned char, IV_LEN> &iv, const std::array<unsigned char, TAG_LEN> &tag, unsigned char *pt);

/**
 * @brief 验证数据库是否加密
 * @param db 数据库连接
 * @return 是否加密
 */
bool verify_db(sqlite3 *db);

/**
 * @brief 加密主密钥
 * @param wrap_path 加密文件路径
 * @param mk 主密钥（输出）
 * @return 是否成功
 */
bool encrypt_mk(const fs::path &wrap_path, std::vector<uint8_t> &out_mk);

/**
 * @brief 解密主密钥
 * @param wrap_path 加密文件路径
 * @param mk 主密钥（输出）
 * @return 是否成功
 */
bool decrypt_mk(const fs::path &wrap_path, std::vector<uint8_t> &out_mk);

/**
 * @brief 加密数据库
 * @param wrap_path 加密文件路径
 * @param db_path 数据库路径
 * @return 是否成功
 */
bool encrypt_db(const fs::path &wrap_path, const fs::path &db_path);

/**
 * @brief 解密数据库
 * @param wrap_path 加密文件路径
 * @param db_path 数据库路径
 * @param pdb 输出数据库连接
 * @return 是否成功
 */
bool decrypt_db(const fs::path &wrap_path, const fs::path &db_path, sqlite3 **pdb);
}  // namespace aimrte::database::security
