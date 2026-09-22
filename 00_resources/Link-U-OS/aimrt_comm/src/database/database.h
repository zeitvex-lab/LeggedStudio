// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <queue>
#include <shared_mutex>
#include <string>
#include <thread>
#include <variant>
#include <vector>
#include "sqlite3.h"

#ifndef SQLITE_TRANSIENT
#define SQLITE_TRANSIENT ((void (*)(void*)) -1)
#endif

namespace aimrte::database {

namespace fs = std::filesystem;

/** 数据库值类型 */
using DBValue = std::variant<std::nullptr_t, bool, int, int64_t, double, std::string, std::vector<uint8_t>>;

/** 数据库行类型 */
using DBRow = std::map<std::string, DBValue>;

/** 数据库结果集类型 */
using DBResult = std::vector<DBRow>;

/** 列定义结构体 */
struct ColumnDefinition {
    std::string name;
    std::string type;
    bool is_primary_key = false;
    bool is_auto_increment = false;
    bool is_not_null = false;
    bool is_unique = false;
    std::optional<std::string> default_value;

    ColumnDefinition(const std::string& col_name, const std::string& col_type)
        : name(col_name), type(col_type) {}

    ColumnDefinition& primary_key(bool value = true) { is_primary_key = value; return *this; }
    ColumnDefinition& auto_increment(bool value = true) { is_auto_increment = value; return *this; }
    ColumnDefinition& not_null(bool value = true) { is_not_null = value; return *this; }
    ColumnDefinition& unique(bool value = true) { is_unique = value; return *this; }
    ColumnDefinition& set_default_value(const std::string& value) { default_value = value.empty() ? "''" : "'" + value + "'"; return *this; }
    ColumnDefinition& auto_increment_primary_key() { is_primary_key = true; is_auto_increment = true; return *this; }
};

/** 安全数据库管理器（线程安全） */
class SecureDatabase {
private:
    fs::path db_path_;
    bool is_encrypt_;
    std::unique_ptr<sqlite3, decltype(&sqlite3_close)> db_;
    mutable std::string last_error_;  // 允许在 const 函数中修改
    mutable std::shared_mutex rw_mtx_;  // 读写锁

    bool bind_parameters(sqlite3_stmt* stmt, const std::vector<DBValue>& params) const;
    DBValue extract_value(sqlite3_stmt* stmt, int col_index) const;

public:
    SecureDatabase(const fs::path& db_path, bool is_encrypt = false);
    ~SecureDatabase();

    bool initialize();
    bool create();
    bool open();
    void close();
    sqlite3* get() const { return db_ ? db_.get() : nullptr; }
    bool is_open() const { return db_ != nullptr; }

    // 写操作
    bool execute(const std::string& sql, const std::vector<DBValue>& params = {});
    bool insert(const std::string& table_name, const DBRow& data);
    bool insert_or_replace(const std::string& table_name, const DBRow& data);
    bool update(const std::string& table_name, const DBRow& data, const std::string& where_condition = "", const std::vector<DBValue>& where_params = {});
    bool remove(const std::string& table_name, const std::string& where_condition = "", const std::vector<DBValue>& where_params = {});

    // 读操作
    DBResult query(const std::string& sql, const std::vector<DBValue>& params = {}) const;
    std::optional<DBRow> query_one(const std::string& table_name, const std::vector<std::string>& columns = {}, const std::string& where_condition = "", const std::vector<DBValue>& where_params = {}) const;
    DBResult query_many(const std::string& table_name, const std::vector<std::string>& columns = {}, const std::string& where_condition = "", const std::vector<DBValue>& where_params = {}, const std::string& order_by = "", int limit = 0) const;
    int64_t count(const std::string& table_name, const std::string& where_condition = "", const std::vector<DBValue>& where_params = {}) const;

    // 列管理
    bool column_exists(const std::string& table_name, const std::string& column_name) const;
    bool add_column(const std::string& table_name, const ColumnDefinition& col);

    // 表管理
    bool table_exists(const std::string& table_name) const;
    bool create_table(const std::string& table_name, const std::vector<std::string>& columns);
    bool create_table(const std::string& table_name, const std::vector<ColumnDefinition>& columns);
    bool drop_table(const std::string& table_name);

    // 事务
    bool begin_transaction() { return execute("BEGIN TRANSACTION"); }
    bool commit_transaction() { return execute("COMMIT"); }
    bool rollback_transaction() { return execute("ROLLBACK"); }

    std::string last_error() { return last_error_; }

    SecureDatabase(const SecureDatabase&) = delete;
    SecureDatabase& operator=(const SecureDatabase&) = delete;
    SecureDatabase(SecureDatabase&&) = default;
    SecureDatabase& operator=(SecureDatabase&&) = default;
};

} // namespace aimrte::database
