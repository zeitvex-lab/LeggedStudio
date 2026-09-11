## 工作流编排（Workflow Orchestration）

### 1. 默认进入 Plan 模式（Plan Node Default）

- 对于 **任何非简单任务**（3 个以上步骤或涉及架构决策），都先进入 Plan 模式  
- 如果事情开始偏离预期，**立刻停止并重新规划**，不要硬着头皮继续做  
- Plan 模式不仅用于构建阶段，也用于 **验证步骤**  
- 提前写出 **详细的规格说明（spec）**，减少歧义

---

### 2. 子代理策略（Subagent Strategy）

- **广泛使用 Subagent**，以保持主上下文窗口的整洁  
- 将 **研究、探索、并行分析** 等任务交给 Subagent  
- 对于复杂问题，可以通过 Subagent **投入更多计算资源**  
- **每个 Subagent 只负责一个任务**，保证执行专注

---

### 3. 自我改进循环（Self-Improvement Loop）

- **只要用户做出任何纠正**，就把经验模式写入 `tasks/lessons.md`  
- 为自己写规则，**防止同样的错误再次发生**  
- 持续、严格地迭代这些经验，直到 **错误率下降**  
- 在每次会话开始时，**先查看 lessons** 是否与当前项目相关

---

### 4. 完成前必须验证（Verification Before Done）

- **没有证明功能有效之前，不要标记任务完成**  
- 在相关情况下，对比 **主分支与修改后的行为差异（diff）**  
- 自问一句：  
  > “一位资深工程师会批准这个实现吗？”  
- 运行测试、检查日志、证明功能正确

---

### 5. 追求优雅（Demand Elegance，平衡）

- 对于非简单修改，先停下来问：  
  > “有没有更优雅的实现方式？”  
- 如果一个修复方案显得 **很 hacky**：  
  > “在我现在知道的一切前提下，实现那个更优雅的方案。”  
- 对于简单明显的修复，可以跳过这一点，**避免过度设计**  
- 在提交之前，**先挑战自己的实现**

---

### 6. 自动化修 Bug（Autonomous Bug Fixing）

- 当收到 Bug 报告时：**直接修复，不要等待手把手指导**  
- 查看 **日志、错误信息、失败的测试**，然后解决问题  
- **不要要求用户进行上下文切换**  
- 发现 CI 测试失败时，**主动修复，而不是等待指示**

---

# 任务管理（Task Management）

1. **Plan First**  
   将计划写入 `tasks/todo.md`，并拆分成可勾选的任务

2. **Verify Plan**  
   在开始实现之前进行确认

3. **Track Progress**  
   执行过程中持续标记完成的任务

4. **Explain Changes**  
   每一步都提供 **高层级变更说明**

5. **Document Results**  
   在 `tasks/todo.md` 中添加 **review / 复盘部分**

6. **Capture Lessons**  
   修正问题后更新 `tasks/lessons.md`

---

# 核心原则（Core Principles）

- **Simplicity First（简单优先）**  
  每一次改动都尽可能简单，只影响最少代码

- **No Laziness（不偷懒）**  
  找到根本原因，不做临时修补，按照资深工程师标准实现

- **Minimal Impact（最小影响）**  
  只修改必要部分，避免引入新的 Bug

---

# 识图能力

你的底层模型可能不具备原生识图能力。遇到图片时，**不要只用 Read/描述猜测**，改用 vision.js：

```
node vision.js "<图片路径>" "用中文描述这张图片"
```

## 触发场景

- 用户分享图片路径（本地或网络 URL）
- 消息中出现 "Saved attachments:" 并列出图片
- 用户要求分析、描述、识别图片内容

## 配置

- 配置文件：项目根目录 `.env`（DASHSCOPE_API_KEY / VISION_MODEL / DASHSCOPE_BASE_URL）
- 已配置：阿里云百炼，模型 qwen3.7-flash-2026-07-15
- 用法：`node vision.js <图片路径> [问题]` 或 `node vision.js --url <图片URL> [问题]`

## 配置好之后

用户直接发图片，自动识图，无需手动打命令。
