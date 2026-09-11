# microduck-studio — 参考资源

> **来源**：`00_open/microduck-studio/`　｜　**类型**：参考项目
> **关联机型**：microduck（MicroDuck 双足）
> **定位**：MicroDuck Studio（编辑/可视化）
> **收录**：27 个文件 / 87 KB（其中推理策略/模型文件 0 个）
> **已省略**：2 个文件 / 1.8 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（1 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **评测与测试**（3 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（23 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （9 个文件）
docker/  （4 个文件）
    microduck/
    microduck-rl/
    studio/
docs/  （1 个文件）
    (直接文件)/
scripts/  （1 个文件）
    (直接文件)/
src/  （9 个文件）
    microduck_studio/
tests/  （3 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 9 |
| `(无扩展名)` | 6 |
| `.md` | 4 |
| `.sh` | 2 |
| `.example` | 1 |
| `.yaml` | 1 |
| `.toml` | 1 |
| `.js` | 1 |
| `.html` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
.dockerignore
.env.example
.gitignore
AGENTS.md
LICENSE
README.md
README.zh-CN.md
compose.yaml
docker/microduck-rl/Dockerfile
docker/microduck/Dockerfile
docker/microduck/entrypoint.sh
docker/studio/Dockerfile
docs/ROADMAP.md
pyproject.toml
scripts/dev-stack.sh
src/microduck_studio/__init__.py
src/microduck_studio/app.py
src/microduck_studio/config.py
src/microduck_studio/discovery.py
src/microduck_studio/jobs.py
src/microduck_studio/protocol.py
src/microduck_studio/static/app.js
src/microduck_studio/static/index.html
src/microduck_studio/static/styles.css
tests/test_app.py
tests/test_jobs.py
tests/test_protocol.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 139 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `docs/images` | 1 | 1.7 MB | [`docs/images/_OMITTED.md`](./docs/images/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
