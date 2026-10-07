# 插件协议 `legged-plugin-1.0` —— 第三方接入须知

> 这份文档写给**在仓库之外写插件的人**：一条清单 + 一个真实现 + 一条校验声明，插件就同时进入
> 产品面（Web / CLI / 首页卡片）与门禁。
>
> **本文不是真值**，只是入口：真值在文件里，判据有机器守（每节都标了"谁守"）。文档与真值
> 不许分叉 —— 分叉由 `tools/doc_reality_check.py` 与各门禁判红。

---

## 1. 三条不变量

| # | 不变量 | 真值 | 谁守 |
|---|---|---|---|
| 1 | **清单即声明**：一个插件一个文件，路径即身份 `registry/plugins/<seam>/<id>.json` | `registry/plugin-registry.json`（`manifest_dir` / `manifest_schema`） | `backend/test_plugin_registry.py` |
| 2 | **引用即真**：清单里的 provider 是**真** `module:attr`（importlib 解析），不是名字巧合 | 清单自身的 `cli.provider` / `home_card.provider` | `backend/test_panel_registry.py`（四投影解析） |
| 3 | **门禁有家**：每个守门脚本都在验证器目录里有一条声明 | `registry/verify/index.json` | `tools/audit_plugin_verify.py --check`（覆盖率 100%） |

> 口径：**不新造清单**。要加"能让别人写扩展"的东西，先问它属于哪个 seam；seam 不够就改
> `registry/plugin-registry.json` 的 `seams`（13 个冻结项，改动即显式裁决）。

---

## 2. 接入三步

1. **写清单**：`registry/plugins/<seam>/<id>.json`（schema `legged-plugin-1.0`；`id` 必须等于文件名 stem）。
2. **写实现**：任何可导入模块里的一个函数/对象，清单用 `module:attr` 指过去（`backend/`、`plugins/`、你自己的包都行 —— 没有任何白名单）。
3. **登记校验**：往 `registry/verify/index.json` 加一条 `command`（`env` 为空 ⇒ 进 CI 的 unit-tests 段；需训练栈/产物/可选依赖 ⇒ 填 `env`，见 §5）。

三步之外**不需要改核心代码**：面板的导航/侧栏/桌面/CLI/首页卡片全部由清单**投影**生成。

---

## 3. 清单字段（`legged-plugin-1.0`）

| 字段 | 必填 | 含义 |
|---|---|---|
| `schema` | ✅ | 固定 `"legged-plugin-1.0"` |
| `seam` | ✅ | 属 13 个冻结 seam（§4） |
| `id` | ✅ | 插件 id，**必须等于清单文件名**（`panel/home.json` → `home`） |
| `provides` | ✅ | 声明本插件提供的服务键，**必须含自身** `"<seam>/<id>"` |
| `title` / `group` / `order` | ○ | 产品面展示用（导航分组与排序；`order` 小的在前） |
| `kind` / `entry` | ○（面板必需 `entry`） | 产品面落点（如 `workbench.html#home`） |
| `desktop` | ○ | `false` = 不进桌面导航（仍可被 CLI / HTTP 投影消费） |
| `requires.services` | ○ | 依赖的服务名（如 `backend`）；不可用时置灰并给出原因 |
| `cli` | ○ | `{command, provider}` —— CLI 命令名 + provider |
| `home_card` | ○ | `{provider, order, note}` —— 首页卡片数据源（与 CLI **同一个 provider**） |

**三面一源**：`cli.provider` 与 `home_card.provider` 指向同一个函数 —— 不写两份读数，
因此不存在"CLI 看到另一套数据"。provider 必须是**纯数据函数**（返回 JSON 可序列化对象，
不打印、不设退出码）。

---

## 4. seam 清单（13 个冻结项）

```
algorithm  controller  evaluator  family  pack  panel
profile    reward      robot      sensor  skill task  terrain
```

* 每个 seam 的**注册表文件**（若有）在 `registry/plugin-registry.json#registries` 里登记
  （`seam` / `path` / `schema`，`runtime: true` 的三份是运行时档位）；
* 每个 seam 的**插件清单**放 `registry/plugins/<seam>/`（自动发现，不入 `registries`）；
* `kernel` **不是 seam**，用于验证器目录里"横切/内核"类门禁的归类。

---

## 5. 校验门：我们守什么，怎么自己跑

验证器目录 `registry/verify/index.json`（schema `plugin-verify-1.0`）每条：

```json
{"command": "python tools/audit_families.py", "seam": "family", "note": "…"}
{"command": "python tools/validate_training_smoke.py", "seam": "profile", "env": "training-venv"}
```

| 维度 | 规则 | 谁守 |
|---|---|---|
| `seam` | 属闭合清单（§4 + `kernel`） | `backend/verify_catalog.py` |
| `env` | 闭合词汇 `training-venv` / `mjlab` / `artifact` / `onnxruntime` / `manual`；**为空 = 进 CI unit-tests 段** | 同上 |
| 覆盖率 | `tools/` 下每个 `^(audit\|validate\|check)_*.py` 都必须有家 | `tools/audit_plugin_verify.py --check` |
| 清单不手维护 | `.cnb.yml` 不许再手列审计/校验命令，只挂 `--run` | 同上 |

自己跑一遍：

```bash
python tools/audit_plugin_verify.py --check   # 目录形状 + 覆盖率 + .cnb.yml 不手列
python tools/audit_plugin_verify.py --list    # 打印派生出的门禁清单（gates / env-gated）
python tools/audit_plugin_verify.py --run     # 依次执行 gates（CI unit-tests 段就这一行）
```

**第三方视角**：目录是控制面一等数据，可编程读取（不吐绝对路径、不含仓库内部判据）：

```python
from backend.verify_catalog import summary
manifest = summary()          # {schema, catalog, counts{total,planned,env_gated}, gates[...]}
```

---

## 6. 最小示例：加一个面板

`registry/plugins/panel/hello.json`：

```json
{
  "schema": "legged-plugin-1.0",
  "id": "hello",
  "seam": "panel",
  "provides": ["panel/hello"],
  "title": "示例",
  "kind": "page",
  "entry": "workbench.html#home",
  "group": "工作台",
  "order": 90,
  "desktop": true,
  "requires": {"services": ["backend"]},
  "cli": {"command": "hello", "provider": "backend.cli_panels:hello_summary"},
  "home_card": {"provider": "backend.cli_panels:hello_summary", "order": 90}
}
```

实现（`backend/cli_panels.py` 里加一个纯数据函数，或放你自己的模块）：

```python
def hello_summary() -> dict:
    return {"greeting": "hello", "panels": 1}
```

就这些：导航出现"示例"、`legacy panel hello` 打印读数、首页出现卡片、`/api/panels/hello`
可查 —— **没有第四处要改**。

---

## 7. 不许做的事（都是判红项）

| 禁止 | 为什么 | 谁抓 |
|---|---|---|
| 控制面 `import` 训练栈（mjlab/torch） | 隔离是硬边界：控制面经 JSON/产物与 worker 交互 | `tools/audit_provision_phases.py` / 契约测试 |
| 新造第二份清单（另起目录/数组） | 双份清单迟早分叉，"有测试 ≠ 门禁在守" | §1 不变量 1 |
| 把机型名写进 `kits/` 或前端 | 族/面板都该零特判 | `tools/audit_machine_literals.py`（只减不涨） |
| 新增审计脚本但不登记 | 游离门禁 = 没人跑 | `tools/audit_plugin_verify.py --check` |
| 手改 `.cnb.yml` 的门禁清单 | 清单是派生物 | 同上 |
| patch 整行替换以外的合并语义 | merge 的半覆盖正是缩放事故同源病 | `plugins/runtime.py` 与 `00_know/06` §18 不变量 |
