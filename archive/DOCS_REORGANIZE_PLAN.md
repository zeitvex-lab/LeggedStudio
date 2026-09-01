# 📋 文档整理方案

**目标**：将 11 个散乱的 MD 文档整理成结构化、易查找的体系

---

## 📊 当前问题

**现状**（11 个文档）：
```
COORDINATION.md
INDEX.md
PHASE0_PROGRESS.md
PHASE0_REPORT.md
PROGRESS_ANALYSIS.md
PYTHON_VERSION_DECISION.md
QUICKSTART.md
README.md
STATUS.md
STATUS_CURRENT.md
SUMMARY.md
TEST_TASK_0_1.md
```

**问题**：
- ❌ 文件名不统一（有的全大写，有的下划线）
- ❌ 功能重叠（STATUS.md vs STATUS_CURRENT.md）
- ❌ 无法快速找到想要的文档
- ❌ 新人不知道从哪里开始

---

## ✅ 整理方案

### 方案 A：重命名 + 归档（推荐）

**新结构**：
```
legged_studio/
├── 00_当前状态.md              ← STATUS_CURRENT.md (重命名)
├── 01_快速测试指南.md          ← QUICKSTART.md (重命名)
├── 02_Phase0进度报告.md        ← PHASE0_REPORT.md (重命名)
├── README.md                   ← 保持不变（项目入口）
├── README_文档中心.md          ← 新建（导航中心）
│
├── docs/                       ← 新建文档目录
│   ├── 00_核心/
│   │   ├── Python版本决策.md   ← PYTHON_VERSION_DECISION.md
│   │   └── 架构设计.md         ← 新建（从 PHASE0_REPORT 提取）
│   ├── 01_进度/
│   │   ├── 任务清单.md         ← PHASE0_PROGRESS.md
│   │   └── 进度分析.md         ← PROGRESS_ANALYSIS.md
│   ├── 02_协作/
│   │   ├── 协作说明.md         ← COORDINATION.md
│   │   └── 工作总结.md         ← SUMMARY.md
│   └── 03_测试/
│       └── Task01详细步骤.md   ← TEST_TASK_0_1.md
│
└── archive/                    ← 归档旧文档
    ├── STATUS.md               ← 归档（已被 STATUS_CURRENT 替代）
    └── INDEX.md                ← 归档（已被 README_文档中心 替代）
```

**优势**：
- ✅ 数字前缀便于排序（00 最重要）
- ✅ 分类清晰（核心/进度/协作/测试）
- ✅ 中文命名直观
- ✅ 新人一眼看懂

---

### 方案 B：仅创建导航页（备选）

保持所有文件名不变，创建一个强大的导航页（README_文档中心.md）

**优势**：
- ✅ 无需重命名（不破坏现有链接）
- ✅ 通过导航解决查找问题

**劣势**：
- ❌ 文件列表仍然混乱
- ❌ 文件名不统一

---

## 🎯 推荐执行（方案 A）

### Step 1：重命名核心文档

```bash
mv STATUS_CURRENT.md 00_当前状态.md
mv QUICKSTART.md 01_快速测试指南.md
mv PHASE0_REPORT.md 02_Phase0进度报告.md
```

### Step 2：整理到 docs/ 目录

```bash
# 创建分类目录
mkdir -p docs/{00_核心,01_进度,02_协作,03_测试}

# 移动文档
mv PYTHON_VERSION_DECISION.md docs/00_核心/Python版本决策.md
mv PHASE0_PROGRESS.md docs/01_进度/任务清单.md
mv PROGRESS_ANALYSIS.md docs/01_进度/进度分析.md
mv COORDINATION.md docs/02_协作/协作说明.md
mv SUMMARY.md docs/02_协作/工作总结.md
mv TEST_TASK_0_1.md docs/03_测试/Task01详细步骤.md
```

### Step 3：归档旧文档

```bash
mkdir -p archive
mv STATUS.md archive/
mv INDEX.md archive/
```

### Step 4：创建新文档

- ✅ `README_文档中心.md`（已创建）
- ✅ `web/index.html`（现代化欢迎页，已创建）

---

## 📖 最终文档树

```
legged_studio/
├── README.md                    # 项目简介（入口）
├── README_文档中心.md           # 文档导航中心 ⭐
│
├── 00_当前状态.md               # 快速状态概览
├── 01_快速测试指南.md           # 2 分钟测试
├── 02_Phase0进度报告.md         # 详细报告
│
├── docs/                        # 分类文档
│   ├── 00_核心/
│   │   ├── Python版本决策.md
│   │   └── 架构设计.md
│   ├── 01_进度/
│   │   ├── 任务清单.md
│   │   └── 进度分析.md
│   ├── 02_协作/
│   │   ├── 协作说明.md
│   │   └── 工作总结.md
│   └── 03_测试/
│       └── Task01详细步骤.md
│
├── web/
│   └── index.html               # 现代化欢迎页 ✨
│
└── archive/                     # 归档
    ├── STATUS.md
    └── INDEX.md
```

**文件数量**：
- 根目录：4 个核心文档（数字前缀，一目了然）
- docs/：7 个分类文档（按类别组织）
- 总计：11 个 → 精简为核心 4 + 分类 7

---

## ✅ 执行计划

### 立即执行

由于重命名涉及多个文件，建议：

1. **创建新导航** ✅（已完成）
   - README_文档中心.md
   - web/index.html

2. **用户确认方案**
   - 是否采用方案 A（重命名 + 分类）
   - 或保持方案 B（仅导航）

3. **批量整理**
   - 执行重命名脚本
   - 移动到分类目录
   - 归档旧文档

---

**整理后效果**：
- ✅ 新人 3 分钟上手（00 → 01 → 02）
- ✅ 文档易查找（分类明确）
- ✅ 结构清晰（数字 + 中文）
- ✅ 现代化界面（web/index.html）

---

**等待用户确认后执行整理。** 📋
