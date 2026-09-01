# Backend API 文档

**Legged Studio 后端 API**

---

## 🚀 启动方式

### 最小服务（Task 0.1）
```bash
python backend/server.py
# 访问 http://127.0.0.1:8765
```

### 完整 API（推荐）
```bash
python backend/api.py
# 访问 http://127.0.0.1:8765
# Swagger 文档：http://127.0.0.1:8765/docs
```

---

## 📋 API 端点

### 基础端点

#### GET /
根端点，返回 API 信息

#### GET /health
健康检查

**响应**：
```json
{
  "status": "ok",
  "version": "0.1.0",
  "python_version": "3.12.2",
  "phase": "Phase 0"
}
```

---

### Asset Inventory

#### GET /api/assets/summary
获取资产清单摘要

**响应**：
```json
{
  "total": 107,
  "by_size": {"S": 35, "M": 42, "L": 30},
  "by_locomotion": {"P": 67, "W": 40},
  "families": ["Go1", "Go2", "A1", ...]
}
```

#### GET /api/assets/robots
查询机器人资产

**参数**：
- `size`: S | M | L（可选）
- `locomotion`: P | W（可选）
- `family`: 家族名（可选）
- `usable_only`: 仅可用（默认 true）

**示例**：
```bash
curl "http://127.0.0.1:8765/api/assets/robots?size=M&locomotion=P"
```

#### GET /api/assets/robots/{family}
按家族获取机器人详情

**示例**：
```bash
curl "http://127.0.0.1:8765/api/assets/robots/Go2"
```

---

### STL 工具

#### POST /api/tools/stl/volume
计算 STL 体积

**请求体**：
```json
{
  "stl_path": "path/to/file.stl"
}
```

**响应**：
```json
{
  "volume_m3": 0.002500,
  "stl_path": "..."
}
```

#### POST /api/tools/stl/estimate-mass
估算质量

**请求体**：
```json
{
  "stl_path": "path/to/file.stl",
  "material": "abs_plastic",
  "density": null
}
```

**响应**：
```json
{
  "volume_m3": 0.002500,
  "mass_kg": 2.625,
  "density": 1050,
  "material": "abs_plastic",
  "size_class": "S"
}
```

**材料选项**：
- `abs_plastic`（默认）
- `aluminum`
- `carbon_fiber`
- `steel`
- `titanium`

---

### Contract

#### GET /api/contracts/template
获取 Contract 模板

**响应**：
```json
{
  "schema_version": "robot-contract-1.0",
  "json_schema": {...},
  "example": {...}
}
```

#### POST /api/contracts/validate
验证 Contract

**请求体**：
```json
{
  "schema_version": "robot-contract-1.0",
  "robot_id": "go2",
  ...
}
```

**响应**：
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

---

### 系统信息

#### GET /api/system/info
获取系统信息

**响应**：
```json
{
  "platform": "Windows",
  "python_version": "3.12.2",
  "architecture": "AMD64"
}
```

#### GET /api/system/environment
获取环境状态

**响应**：
```json
{
  "control_plane": {
    "python_version": "3.12.2",
    "status": "running"
  },
  "adapters": {
    "mjlab": {
      "name": "MJLab Adapter",
      "venv_exists": true,
      "status": "installed"
    }
  }
}
```

---

## 🧪 测试

### 测试健康检查
```bash
curl http://127.0.0.1:8765/health
```

### 测试资产摘要
```bash
curl http://127.0.0.1:8765/api/assets/summary
```

### 测试系统信息
```bash
curl http://127.0.0.1:8765/api/system/info
```

---

## 📖 Swagger 文档

启动服务器后访问：
- **Swagger UI**：http://127.0.0.1:8765/docs
- **ReDoc**：http://127.0.0.1:8765/redoc

---

## 🔧 开发

### 添加新端点

1. 在 `backend/api.py` 添加函数
2. 使用装饰器 `@app.get()` 或 `@app.post()`
3. 添加类型标注和文档字符串
4. 测试端点

### 错误处理

所有端点都有统一的错误处理：
- 404：资源不存在
- 500：服务器内部错误

---

**完整 API 参考：启动服务器后访问 /docs**
