// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "database.h"
#include <iostream>
#include <sstream>

namespace aimrte::database
{

SecureDatabase::SecureDatabase(const fs::path& db_path, bool is_encrypt)
    : db_path_(db_path), is_encrypt_(is_encrypt), db_(nullptr, &sqlite3_close) {}

SecureDatabase::~SecureDatabase()
{
  if (is_open()) close();
}

bool SecureDatabase::bind_parameters(sqlite3_stmt* stmt, const std::vector<DBValue>& params) const
{
  for (size_t i = 0; i < params.size(); ++i) {
    int idx         = static_cast<int>(i + 1);
    const auto& val = params[i];
    if (std::holds_alternative<std::nullptr_t>(val)) {
      if (sqlite3_bind_null(stmt, idx) != SQLITE_OK) return false;
    } else if (std::holds_alternative<bool>(val)) {
      if (sqlite3_bind_int(stmt, idx, std::get<bool>(val)) != SQLITE_OK) return false;
    } else if (std::holds_alternative<int>(val)) {
      if (sqlite3_bind_int(stmt, idx, std::get<int>(val)) != SQLITE_OK) return false;
    } else if (std::holds_alternative<int64_t>(val)) {
      if (sqlite3_bind_int64(stmt, idx, std::get<int64_t>(val)) != SQLITE_OK) return false;
    } else if (std::holds_alternative<double>(val)) {
      if (sqlite3_bind_double(stmt, idx, std::get<double>(val)) != SQLITE_OK) return false;
    } else if (std::holds_alternative<std::string>(val)) {
      const auto& s = std::get<std::string>(val);
      if (sqlite3_bind_text(stmt, idx, s.c_str(), static_cast<int>(s.size()), SQLITE_TRANSIENT) != SQLITE_OK) return false;
    } else if (std::holds_alternative<std::vector<uint8_t>>(val)) {
      const auto& v = std::get<std::vector<uint8_t>>(val);
      if (sqlite3_bind_blob(stmt, idx, v.data(), static_cast<int>(v.size()), SQLITE_TRANSIENT) != SQLITE_OK) return false;
    } else
      return false;
  }
  return true;
}

DBValue SecureDatabase::extract_value(sqlite3_stmt* stmt, int col_index) const
{
  int type = sqlite3_column_type(stmt, col_index);
  switch (type) {
    case SQLITE_INTEGER:
      return sqlite3_column_int64(stmt, col_index);
    case SQLITE_FLOAT:
      return sqlite3_column_double(stmt, col_index);
    case SQLITE_TEXT:
      return std::string(reinterpret_cast<const char*>(sqlite3_column_text(stmt, col_index)));
    case SQLITE_BLOB: {
      const void* data = sqlite3_column_blob(stmt, col_index);
      int size         = sqlite3_column_bytes(stmt, col_index);
      return std::vector<uint8_t>((uint8_t*)data, (uint8_t*)data + size);
    }
    case SQLITE_NULL:
    default:
      return nullptr;
  }
}

bool SecureDatabase::initialize() { return fs::exists(db_path_) ? open() : create(); }

bool SecureDatabase::create()
{
  sqlite3* raw_db = nullptr;

  int flags = SQLITE_OPEN_READWRITE |
              SQLITE_OPEN_CREATE |
              SQLITE_OPEN_FULLMUTEX;  // <-- 关键：线程安全

  if (sqlite3_open_v2(db_path_.string().c_str(), &raw_db, flags, nullptr) != SQLITE_OK) {
    last_error_ = sqlite3_errmsg(raw_db);
    sqlite3_close(raw_db);
    return false;
  }

  db_.reset(raw_db);
  return true;
}

bool SecureDatabase::open()
{
  if (!fs::exists(db_path_)) return false;

  sqlite3* raw_db = nullptr;

  int flags = SQLITE_OPEN_READWRITE |
              SQLITE_OPEN_FULLMUTEX;

  if (sqlite3_open_v2(db_path_.string().c_str(), &raw_db, flags, nullptr) != SQLITE_OK) {
    last_error_ = sqlite3_errmsg(raw_db);
    sqlite3_close(raw_db);
    return false;
  }
  // 开启 WAL
  sqlite3_exec(raw_db, "PRAGMA journal_mode=WAL;", nullptr, nullptr, nullptr);

  // 推荐：提高并发表现
  sqlite3_exec(raw_db, "PRAGMA synchronous=NORMAL;", nullptr, nullptr, nullptr);
  db_.reset(raw_db);
  return true;
}

void SecureDatabase::close()
{
  db_.reset();
}

// 写操作（unique_lock）
bool SecureDatabase::execute(const std::string& sql, const std::vector<DBValue>& params)
{
  std::unique_lock lock(rw_mtx_);
  sqlite3_stmt* stmt = nullptr;
  if (sqlite3_prepare_v2(db_.get(), sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
    last_error_ = sqlite3_errmsg(db_.get());
    return false;
  }
  if (!bind_parameters(stmt, params)) {
    sqlite3_finalize(stmt);
    last_error_ = "Failed to bind parameters";
    return false;
  }
  int rc = sqlite3_step(stmt);
  sqlite3_finalize(stmt);
  if (rc != SQLITE_DONE) last_error_ = sqlite3_errmsg(db_.get());
  return rc == SQLITE_DONE;
}

// 查询操作（shared_lock）
DBResult SecureDatabase::query(const std::string& sql, const std::vector<DBValue>& params) const
{
  DBResult result;
  std::shared_lock lock(rw_mtx_);
  sqlite3_stmt* stmt = nullptr;
  if (sqlite3_prepare_v2(db_.get(), sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
    last_error_ = sqlite3_errmsg(db_.get());
    return result;
  }
  if (!bind_parameters(stmt, params)) {
    sqlite3_finalize(stmt);
    last_error_ = "Failed to bind parameters";
    return result;
  }
  while (sqlite3_step(stmt) == SQLITE_ROW) {
    DBRow row;
    int col_count = sqlite3_column_count(stmt);
    for (int i = 0; i < col_count; ++i) {
      std::string name = sqlite3_column_name(stmt, i);
      row[name]        = extract_value(stmt, i);
    }
    result.push_back(std::move(row));
  }
  sqlite3_finalize(stmt);
  return result;
}

// Insert / Update / Remove 写操作
bool SecureDatabase::insert(const std::string& table_name, const DBRow& data)
{
  if (data.empty()) return false;
  std::ostringstream columns, values;
  std::vector<DBValue> params;
  bool first = true;
  for (auto& [col, val] : data) {
    if (!first) {
      columns << ",";
      values << ",";
    }
    first = false;
    columns << col;
    values << "?";
    params.push_back(val);
  }
  return execute("INSERT INTO " + table_name + " (" + columns.str() + ") VALUES (" + values.str() + ")", params);
}

bool SecureDatabase::insert_or_replace(const std::string& table_name, const DBRow& data)
{
  if (data.empty()) return false;
  std::ostringstream columns, values;
  std::vector<DBValue> params;
  bool first = true;
  for (auto& [col, val] : data) {
    if (!first) {
      columns << ",";
      values << ",";
    }
    first = false;
    columns << col;
    values << "?";
    params.push_back(val);
  }
  return execute("INSERT OR REPLACE INTO " + table_name + " (" + columns.str() + ") VALUES (" + values.str() + ")", params);
}

bool SecureDatabase::update(const std::string& table_name, const DBRow& data, const std::string& where_condition, const std::vector<DBValue>& where_params)
{
  if (data.empty()) return false;
  std::ostringstream sets;
  std::vector<DBValue> params;
  bool first = true;
  for (auto& [col, val] : data) {
    if (!first) sets << ",";
    first = false;
    sets << col << "=?";
    params.push_back(val);
  }
  params.insert(params.end(), where_params.begin(), where_params.end());
  std::string sql = "UPDATE " + table_name + " SET " + sets.str();
  if (!where_condition.empty()) sql += " WHERE " + where_condition;
  return execute(sql, params);
}

bool SecureDatabase::remove(const std::string& table_name, const std::string& where_condition, const std::vector<DBValue>& where_params)
{
  std::string sql = "DELETE FROM " + table_name;
  if (!where_condition.empty()) sql += " WHERE " + where_condition;
  bool result = execute(sql, where_params);
  return result;
}

// 查询辅助函数
std::optional<DBRow> SecureDatabase::query_one(const std::string& table_name, const std::vector<std::string>& columns, const std::string& where_condition, const std::vector<DBValue>& where_params) const
{
  std::string cols = columns.empty() ? "*" : "";
  if (!columns.empty()) {
    for (size_t i = 0; i < columns.size(); ++i) {
      if (i > 0) cols += ",";
      cols += columns[i];
    }
  }
  std::string sql = "SELECT " + cols + " FROM " + table_name;
  if (!where_condition.empty()) sql += " WHERE " + where_condition;
  sql += " LIMIT 1";
  DBResult res = query(sql, where_params);
  if (res.empty()) {
    return std::nullopt;
  }
  return res[0];
}

DBResult SecureDatabase::query_many(const std::string& table_name, const std::vector<std::string>& columns, const std::string& where_condition, const std::vector<DBValue>& where_params, const std::string& order_by, int limit) const
{
  std::string cols = columns.empty() ? "*" : "";
  if (!columns.empty()) {
    for (size_t i = 0; i < columns.size(); ++i) {
      if (i > 0) cols += ",";
      cols += columns[i];
    }
  }
  std::string sql = "SELECT " + cols + " FROM " + table_name;
  if (!where_condition.empty()) sql += " WHERE " + where_condition;
  if (!order_by.empty()) sql += " ORDER BY " + order_by;
  if (limit > 0) sql += " LIMIT " + std::to_string(limit);
  return query(sql, where_params);
}

int64_t SecureDatabase::count(const std::string& table_name, const std::string& where_condition, const std::vector<DBValue>& where_params) const
{
  std::string sql = "SELECT COUNT(*) AS count FROM " + table_name;
  if (!where_condition.empty()) sql += " WHERE " + where_condition;
  DBResult res = query(sql, where_params);
  if (res.empty()) return -1;
  auto it = res[0].find("count");
  if (it != res[0].end() && std::holds_alternative<int64_t>(it->second)) return std::get<int64_t>(it->second);
  if (it != res[0].end() && std::holds_alternative<int>(it->second)) return std::get<int>(it->second);
  return -1;
}

bool SecureDatabase::column_exists(const std::string& table_name, const std::string& column_name) const
{
  DBResult res = query("PRAGMA table_info(" + table_name + ")", {});
  for (const auto& row : res) {
    auto it = row.find("name");
    if (it != row.end() && std::holds_alternative<std::string>(it->second) && std::get<std::string>(it->second) == column_name) {
      return true;
    }
  }
  return false;
}

bool SecureDatabase::add_column(const std::string& table_name, const ColumnDefinition& col)
{
  if (column_exists(table_name, col.name)) return true;  // 已存在，不操作
  std::ostringstream sql;
  sql << "ALTER TABLE " << table_name << " ADD COLUMN " << col.name << " " << col.type;

  if (col.is_not_null) sql << " NOT NULL";
  if (col.default_value.has_value()) sql << " DEFAULT " << col.default_value.value();

  return execute(sql.str(), {});  // 空参数
}

// 表管理
bool SecureDatabase::table_exists(const std::string& table_name) const
{
  DBResult res = query("SELECT name FROM sqlite_master WHERE type='table' AND name=?", {table_name});
  return !res.empty();
}

bool SecureDatabase::create_table(const std::string& table_name, const std::vector<std::string>& columns)
{
  if (columns.empty()) return false;
  std::ostringstream oss;
  bool first = true;
  for (auto& col : columns) {
    if (!first) oss << ",";
    first = false;
    oss << col;
  }
  return execute("CREATE TABLE IF NOT EXISTS " + table_name + " (" + oss.str() + ")");
}

bool SecureDatabase::create_table(const std::string& table_name, const std::vector<ColumnDefinition>& columns)
{
  if (columns.empty()) return false;
  std::ostringstream oss;
  bool first = true;
  for (auto& col : columns) {
    if (!first) oss << ",";
    first = false;
    oss << col.name << " " << col.type;
    if (col.is_primary_key) oss << " PRIMARY KEY";
    if (col.is_auto_increment) oss << " AUTOINCREMENT";
    if (col.is_not_null) oss << " NOT NULL";
    if (col.is_unique) oss << " UNIQUE";
    if (col.default_value.has_value()) oss << " DEFAULT " << col.default_value.value();
  }
  return execute("CREATE TABLE IF NOT EXISTS " + table_name + " (" + oss.str() + ")");
}

bool SecureDatabase::drop_table(const std::string& table_name)
{
  return execute("DROP TABLE IF EXISTS " + table_name);
}

}  // namespace aimrte::database
