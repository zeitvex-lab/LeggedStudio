// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./security.h"

namespace aimrte::database::security
{
const char *PEPPER = "agibot-pepper-v1-sqlcipher";

// 错误信息映射
std::string_view get_error_message(SecurityError error)
{
  switch (error) {
    case SecurityError::SUCCESS:
      return "操作成功";
    case SecurityError::RANDOM_GENERATION_FAILED:
      return "随机数生成失败";
    case SecurityError::DEVICE_ID_GENERATION_FAILED:
      return "设备指纹生成失败";
    case SecurityError::HKDF_FAILED:
      return "HKDF密钥派生失败";
    case SecurityError::AES_ENCRYPTION_FAILED:
      return "AES-GCM加密失败";
    case SecurityError::AES_DECRYPTION_FAILED:
      return "AES-GCM解密失败";
    case SecurityError::FILE_READ_FAILED:
      return "文件读取失败";
    case SecurityError::FILE_WRITE_FAILED:
      return "文件写入失败";
    case SecurityError::INVALID_FILE_FORMAT:
      return "文件格式无效";
    case SecurityError::DATABASE_OPEN_FAILED:
      return "数据库打开失败";
    case SecurityError::DATABASE_KEY_FAILED:
      return "数据库密钥设置失败";
    case SecurityError::DATABASE_VERIFICATION_FAILED:
      return "数据库验证失败";
    case SecurityError::NETWORK_INTERFACE_NOT_FOUND:
      return "网络接口未找到";
    case SecurityError::MAC_ADDRESS_NOT_FOUND:
      return "MAC地址未找到";
    default:
      return "未知错误";
  }
}

/**
 * @brief 生成随机字节
 * @param p 输出缓冲区
 * @param n 字节数
 * @return 是否成功
 */
bool random_bytes(unsigned char *p, size_t n)
{
  if (!p || n == 0) return false;
  return RAND_bytes(p, static_cast<int>(n)) == 1;
}

/**
 * @brief 计算 SHA256 哈希
 * @param data 输入数据
 * @param n 数据长度
 * @param out 输出缓冲区
 */
void sha256(const unsigned char *data, size_t n, unsigned char out[32])
{
  if (data && out) {
    SHA256(data, n, out);
  }
}

/**
 * @brief 安全的字符串转换（移除冒号并转大写）
 * @param input 输入字符串
 * @return 处理后的字符串
 */
std::optional<std::string> normalize_mac_address(std::string s)
{
  s.erase(std::remove_if(s.begin(), s.end(), [](unsigned char c) {
            return c == ':' || c == '-';
          }),
          s.end());
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
    return std::tolower(c);
  });
  if (s.size() != 12) return std::nullopt;
  if (!std::all_of(s.begin(), s.end(), [](unsigned char c) {
        return std::isxdigit(c);
      })) return std::nullopt;
  return s;
}

/**
 * @brief 读取并去除尾部空白字符
 * @param p 文件路径
 * @return 读取到的字符串
 */
std::optional<std::string> read_text_trim(const fs::path &p)
{
  std::ifstream f(p, std::ios::binary);
  if (!f) return std::nullopt;
  std::string s((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
  while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
  return s;
}

/**
 * @brief 获取网卡的 MAC 地址
 * @param ifname 网卡名
 * @return MAC 地址
 */
std::optional<std::string> get_mac_for_iface()
{
  // 获取机型
  auto model_opt = read_text_trim("/agibot/data/info/model");
  if (!model_opt) {
    AIMRTE_ERROR("无法读取机型信息");
    return std::nullopt;
  }
  std::string model = *model_opt;
  // 网卡路径
  std::string mac_address_file_path;

  // 根据机型获取网卡路径
  if (model.find("_LITE") != std::string::npos) {
    // 如果是后缀是_LITE, 则使用eth_client
    mac_address_file_path = "/sys/class/net/eth_client/address";
  } else if (model.find("_FLAGSHIP") != std::string::npos) {
    // 如果是后缀是_FLAGSHIP, 则使用eth0
    mac_address_file_path = "/sys/class/net/eth0/address";
  } else {
    AIMRTE_ERROR("获取默认网卡 MAC 地址失败");
    return std::nullopt;
  }
  // 读取 MAC 地址
  auto mac = read_text_trim(fs::path(mac_address_file_path));
  if (!mac) {
    AIMRTE_ERROR("获取默认网卡 MAC 地址失败");
    return std::nullopt;
  }

  return normalize_mac_address(*mac);
}

/**
 * @brief 生成设备指纹
 * @param devid 输出缓冲区
 * @return 是否成功
 */
bool make_devid(DeviceId &devid)
{
  MD_CTX_ptr md(EVP_MD_CTX_new(), &EVP_MD_CTX_free);
  if (!md) return false;

  if (EVP_DigestInit_ex(md.get(), EVP_sha256(), nullptr) != 1) {
    return false;
  }

  // 添加机器ID
  if (auto machine_id = read_text_trim("/agibot/data/info/sn")) {
    if (EVP_DigestUpdate(md.get(), machine_id->data(), machine_id->size()) != 1) {
      return false;
    }
  }

  // 添加网络接口MAC地址
  if (auto mac = get_mac_for_iface()) {
    if (EVP_DigestUpdate(md.get(), mac->data(), mac->size()) != 1) {
      return false;
    }
  }

  unsigned int outlen = 0;
  return EVP_DigestFinal_ex(md.get(), devid.data(), &outlen) == 1 && outlen == 32;
}

/**
 * @brief 生成扰动值
 * @param disturbance 扰动值
 * @return 是否成功
 */
bool make_shift_salt(std::array<unsigned char, 32> &disturbance, std::array<unsigned char, 16> &noise)
{
  uint64_t time = 0;
  uint64_t pid  = 0;
  if (noise.empty()) {
    time = static_cast<uint64_t>(std::time(nullptr));
    pid  = static_cast<uint64_t>(::getpid());
    std::memcpy(noise.data(), &time, sizeof(time));
    std::memcpy(noise.data() + sizeof(time), &pid, sizeof(pid));
  } else {
    std::memcpy(&time, noise.data(), sizeof(time));
    std::memcpy(&pid, noise.data() + sizeof(time), sizeof(pid));
  }
  auto devid = read_text_trim("/agibot/data/info/sn");
  auto mac   = get_mac_for_iface();

  // 拼接原始因子
  std::string raw = (std::to_string(time) +
                     devid.value_or("")) +
                    std::to_string(pid) +
                    (mac.value_or(""));

  // SHA256(raw)
  sha256(reinterpret_cast<const unsigned char *>(raw.data()), raw.size(), disturbance.data());
  return true;
}

/**
 * @brief 读取加密文件
 * @param path 文件路径
 * @param blob 输出缓冲区
 * @return 是否成功
 */
bool read_wrap(const fs::path &path, WrapBlob &blob)
{
  std::ifstream f(path, std::ios::binary);
  if (!f) return false;

  // 读取magic
  f.read(blob.magic, sizeof(blob.magic));
  if (!f || !blob.is_valid()) return false;

  // 读取其他字段
  f.read(reinterpret_cast<char *>(blob.salt.data()), blob.salt.size());
  f.read(reinterpret_cast<char *>(blob.iv.data()), blob.iv.size());
  f.read(reinterpret_cast<char *>(blob.tag.data()), blob.tag.size());
  f.read(reinterpret_cast<char *>(blob.ct.data()), blob.ct.size());
  f.read(reinterpret_cast<char *>(blob.noise.data()), blob.noise.size());

  return static_cast<bool>(f);
}

/**
 * @brief 写入加密文件
 * @param path 文件路径
 * @param blob 输入缓冲区
 * @return 是否成功
 */
bool write_wrap(const fs::path &path, const WrapBlob &blob)
{
  SecureFileWriter writer(path);
  if (!writer.is_open()) return false;

  // 写入所有字段
  if (!writer.write(blob.magic, sizeof(blob.magic)) || !writer.write(blob.salt.data(), blob.salt.size()) || !writer.write(blob.iv.data(), blob.iv.size()) || !writer.write(blob.tag.data(), blob.tag.size()) || !writer.write(blob.ct.data(), blob.ct.size()) || !writer.write(blob.noise.data(), blob.noise.size())) {
    return false;
  }

  // 同步到磁盘
  if (!writer.sync()) return false;

  // 设置文件权限
  fs::permissions(path, fs::perms::owner_read | fs::perms::owner_write, fs::perm_options::replace);

  return true;
}

/**
 * @brief 生成设备密钥
 * @param devid 设备指纹
 * @param salt 加密文件的盐
 * @param devk 输出缓冲区
 * @return 是否成功
 */
bool hkdf_devk(const DeviceId &devid, const std::array<unsigned char, SALT_LEN> &salt, const std::array<unsigned char, 32> &disturbance, DeviceKey &devk)
{
  // 创建 HKDF 上下文
  PKEY_CTX_ptr p(EVP_PKEY_CTX_new_id(EVP_PKEY_HKDF, nullptr), &EVP_PKEY_CTX_free);
  if (!p) return false;

  size_t outlen = devk.size();

  if (EVP_PKEY_derive_init(p.get()) != 1) return false;
  if (EVP_PKEY_CTX_set_hkdf_md(p.get(), EVP_sha256()) != 1) return false;

  // 设置 salt
  if (EVP_PKEY_CTX_set1_hkdf_salt(p.get(), salt.data(), static_cast<int>(salt.size())) != 1)
    return false;

  // 设置 ikm（devid）
  if (EVP_PKEY_CTX_set1_hkdf_key(p.get(), devid.data(), static_cast<int>(devid.size())) != 1)
    return false;

  // info: pepper
  if (EVP_PKEY_CTX_add1_hkdf_info(p.get(), reinterpret_cast<const unsigned char *>(PEPPER), static_cast<int>(strlen(PEPPER))) != 1)
    return false;

  // info: disturbance
  if (EVP_PKEY_CTX_add1_hkdf_info(p.get(), disturbance.data(), static_cast<int>(disturbance.size())) != 1)
    return false;

  // 派生输出
  if (EVP_PKEY_derive(p.get(), devk.data(), &outlen) != 1) return false;

  if (outlen != devk.size()) {
    std::fill(devk.begin(), devk.end(), 0);
    return false;
  }

  return true;
}

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
bool aes_gcm_encrypt(const DeviceKey &key, const unsigned char *pt, size_t ptlen, std::array<unsigned char, IV_LEN> &iv, std::array<unsigned char, TAG_LEN> &tag, unsigned char *ct)
{
  if (ptlen != MK_LEN || !pt || !ct) return false;

  // 生成随机IV
  if (!random_bytes(iv.data(), iv.size())) return false;

  CIPHER_CTX_ptr ctx(EVP_CIPHER_CTX_new(), &EVP_CIPHER_CTX_free);
  if (!ctx) return false;

  // 初始化加密上下文
  if (EVP_EncryptInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1 || EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_IVLEN, static_cast<int>(iv.size()), nullptr) != 1 || EVP_EncryptInit_ex(ctx.get(), nullptr, nullptr, key.data(), iv.data()) != 1) {
    return false;
  }

  // 执行加密
  int out = 0, tot = 0;
  if (EVP_EncryptUpdate(ctx.get(), ct, &out, pt, static_cast<int>(ptlen)) != 1) {
    return false;
  }
  tot += out;

  if (EVP_EncryptFinal_ex(ctx.get(), ct + tot, &out) != 1) {
    return false;
  }
  tot += out;

  if (static_cast<size_t>(tot) != ptlen) return false;

  // 获取认证标签
  return EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_GET_TAG, static_cast<int>(tag.size()), tag.data()) == 1;
}

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
bool aes_gcm_decrypt(const DeviceKey &key, const unsigned char *ct, size_t ctlen, const std::array<unsigned char, IV_LEN> &iv, const std::array<unsigned char, TAG_LEN> &tag, unsigned char *pt)
{
  if (ctlen != MK_LEN || !ct || !pt) return false;

  CIPHER_CTX_ptr ctx(EVP_CIPHER_CTX_new(), &EVP_CIPHER_CTX_free);
  if (!ctx) return false;

  // 初始化解密上下文
  if (EVP_DecryptInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1 || EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_IVLEN, static_cast<int>(iv.size()), nullptr) != 1 || EVP_DecryptInit_ex(ctx.get(), nullptr, nullptr, key.data(), iv.data()) != 1) {
    return false;
  }

  // 执行解密
  int out = 0, tot = 0;
  if (EVP_DecryptUpdate(ctx.get(), pt, &out, ct, static_cast<int>(ctlen)) != 1) {
    return false;
  }
  tot += out;

  // 设置认证标签
  if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_TAG, static_cast<int>(tag.size()), const_cast<unsigned char *>(tag.data())) != 1) {
    return false;
  }

  if (EVP_DecryptFinal_ex(ctx.get(), pt + tot, &out) != 1) {
    return false;
  }
  tot += out;

  return static_cast<size_t>(tot) == ctlen;
}

/**
 * @brief 验证数据库是否加密
 * @param db 数据库连接
 * @return 是否加密
 */
bool verify_db(sqlite3 *db)
{
  if (!db) return false;

  sqlite3_stmt *st = nullptr;
  int rc           = sqlite3_prepare_v2(db, "SELECT count(*) FROM sqlite_master;", -1, &st, nullptr);
  if (rc != SQLITE_OK) return false;

  SQLite3_stmt_ptr st_ptr(st, &sqlite3_finalize);
  rc = sqlite3_step(st_ptr.get());
  return rc == SQLITE_ROW;
}

/**
 * @brief 加密主密钥
 * @param wrap_path 加密文件路径
 * @param mk 主密钥（输出）
 * @return 是否成功
 */
bool encrypt_mk(const fs::path &wrap_path, std::vector<uint8_t> &out_mk)
{
  DeviceId devid{};
  if (!make_devid(devid)) {
    AIMRTE_ERROR("设备指纹生成失败");
    return false;
  }

  std::array<unsigned char, SALT_LEN> salt{};
  DeviceKey devk{};
  std::array<unsigned char, IV_LEN> iv{};
  std::array<unsigned char, TAG_LEN> tag{};
  std::array<unsigned char, MK_LEN> mk_buf{};  // 临时主密钥
  std::array<unsigned char, MK_LEN> ct_buf{};
  std::array<unsigned char, 32> disturbance{};
  std::array<unsigned char, 16> noise{};

  // 生成随机主密钥和盐
  if (!random_bytes(mk_buf.data(), mk_buf.size()) || !random_bytes(salt.data(), salt.size())) {
    AIMRTE_ERROR("随机密钥生成失败");
    return false;
  }

  // 生成扰动值
  if (!make_shift_salt(disturbance, noise)) {
    AIMRTE_ERROR("生成扰动值失败");
    return false;
  }

  // 派生设备密钥
  if (!hkdf_devk(devid, salt, disturbance, devk)) {
    AIMRTE_ERROR("HKDF 失败");
    return false;
  }

  // 加密主密钥
  if (!aes_gcm_encrypt(devk, mk_buf.data(), mk_buf.size(), iv, tag, ct_buf.data())) {
    AIMRTE_ERROR("AES-GCM 加密失败");
    return false;
  }

  // 构造并写入加密文件
  WrapBlob blob{};
  blob.salt  = salt;
  blob.iv    = iv;
  blob.tag   = tag;
  blob.ct    = ct_buf;
  blob.noise = noise;

  if (!write_wrap(wrap_path, blob)) {
    AIMRTE_ERROR("写入加密文件失败");
    return false;
  }

  out_mk.assign(mk_buf.begin(), mk_buf.end());
  return true;
}

/**
 * @brief 解密主密钥
 * @param wrap_path 加密文件路径
 * @param mk 主密钥（输出）
 * @return 是否成功
 */
bool decrypt_mk(const fs::path &wrap_path, std::vector<uint8_t> &out_mk)
{
  DeviceId devid{};
  if (!make_devid(devid)) {
    AIMRTE_ERROR("获取设备指纹失败");
    return false;
  }

  WrapBlob blob{};
  if (!read_wrap(wrap_path, blob)) {
    AIMRTE_ERROR("读取 wrap 失败或格式不对");
    return false;
  }

  std::array<unsigned char, 32> disturbance{};
  if (!make_shift_salt(disturbance, blob.noise)) {
    AIMRTE_ERROR("生成扰动值失败");
    return false;
  }

  DeviceKey devk{};
  if (!hkdf_devk(devid, blob.salt, disturbance, devk)) {
    AIMRTE_ERROR("HKDF 失败");
    return false;
  }

  // 确保输出缓冲有空间
  out_mk.resize(MK_LEN);

  // 直接解密到 out_mk
  if (!aes_gcm_decrypt(devk, blob.ct.data(), blob.ct.size(), blob.iv, blob.tag, out_mk.data())) {
    AIMRTE_ERROR("解包失败：设备不匹配或文件损坏");
    out_mk.clear();
    return false;
  }

  return true;
}

/**
 * @brief 加密数据库
 * @param wrap_path 加密文件路径
 * @param db_path 数据库路径
 * @return 是否成功
 */
bool encrypt_db(const fs::path &wrap_path, const fs::path &db_path)
{
  std::vector<uint8_t> mk;
  sqlite3 *db  = nullptr;
  char *errmsg = nullptr;

  // 加密数据库
  if (!encrypt_mk(wrap_path, mk)) {
    return false;
  }

  if (!fs::exists(db_path)) {
    if (sqlite3_open(db_path.string().c_str(), &db) != SQLITE_OK) {
      AIMRTE_ERROR("数据库打开失败");
      return false;
    }

    SQLite3_ptr db_ptr(db, &sqlite3_close);

    if (sqlite3_key_v2(db_ptr.get(), "main", mk.data(), static_cast<int>(mk.size())) != SQLITE_OK) {
      AIMRTE_ERROR("数据库密钥设置失败");
      return false;
    }

    // 创建验证表
    if (sqlite3_exec(db_ptr.get(), "CREATE TABLE IF NOT EXISTS _encryption(version TEXT);", nullptr, nullptr, &errmsg) != SQLITE_OK) {
      if (errmsg) {
        AIMRTE_ERROR("创建验证表失败: {}", errmsg);
        sqlite3_free(errmsg);
      }
      return false;
    }
  } else {
    // 打开数据库
    if (sqlite3_open(db_path.string().c_str(), &db) != SQLITE_OK) {
      AIMRTE_ERROR("无法打开数据库: {}", sqlite3_errmsg(db));
      return false;
    }

    // 检查是否已经是加密数据库
    if (sqlite3_exec(db, "SELECT 1;", nullptr, nullptr, &errmsg) != SQLITE_OK) {
      AIMRTE_INFO("数据库已加密");
      sqlite3_close(db);
      return true;
    }

    // 创建临时文件
    std::string temp_file = db_path.string() + ".enc";

    // 附加加密数据库
    std::string attach_sql = "ATTACH DATABASE '" + temp_file + "' AS encrypted;";
    if (sqlite3_exec(db, attach_sql.c_str(), nullptr, nullptr, &errmsg) != SQLITE_OK) {
      AIMRTE_ERROR("附加数据库失败: {}", errmsg);
      sqlite3_free(errmsg);
      sqlite3_close(db);
      return false;
    }

    // 设置附加数据库密钥
    if (sqlite3_key_v2(db, "encrypted", mk.data(), static_cast<int>(mk.size())) != SQLITE_OK) {
      AIMRTE_ERROR("设置附加数据库密钥失败");
      sqlite3_close(db);
      return false;
    }

    // 导出数据
    if (sqlite3_exec(db, "SELECT sqlcipher_export('encrypted');", nullptr, nullptr, &errmsg) != SQLITE_OK) {
      AIMRTE_ERROR("数据导出失败: {}", errmsg);
      sqlite3_free(errmsg);
      sqlite3_close(db);
      return false;
    }

    // 分离加密数据库
    if (sqlite3_exec(db, "DETACH DATABASE encrypted;", nullptr, nullptr, &errmsg) != SQLITE_OK) {
      AIMRTE_ERROR("分离失败: {}", errmsg);
      sqlite3_free(errmsg);
    }

    sqlite3_close(db);

    // 删除原始数据库
    if (std::remove(db_path.string().c_str()) != 0) {
      AIMRTE_ERROR("删除原始数据库失败");
      return false;
    }

    // 替换为加密后的数据库
    if (std::rename(temp_file.c_str(), db_path.string().c_str()) != 0) {
      AIMRTE_ERROR("替换加密数据库失败");
      return false;
    }
  }

  return true;
}

/**
 * @brief 解密数据库
 * @param wrap_path 加密文件路径
 * @param db_path 数据库路径
 * @param pdb 输出数据库连接
 * @return 是否成功
 */
bool decrypt_db(const fs::path &wrap_path, const fs::path &db_path, sqlite3 **pdb)
{
  if (!pdb) return false;

  std::vector<uint8_t> mk;
  if (!decrypt_mk(wrap_path, mk)) return false;

  if (sqlite3_open(db_path.string().c_str(), pdb) != SQLITE_OK) {
    AIMRTE_ERROR("数据库打开失败");
    return false;
  }

  if (sqlite3_key_v2(*pdb, "main", mk.data(), static_cast<int>(mk.size())) != SQLITE_OK) {
    AIMRTE_ERROR("数据库密钥设置失败");
    sqlite3_close(*pdb);
    *pdb = nullptr;
    return false;
  }

  if (!verify_db(*pdb)) {
    AIMRTE_ERROR("数据库验证失败");
    sqlite3_close(*pdb);
    *pdb = nullptr;
    return false;
  }

  return true;
}
}  // namespace aimrte::database::security
