# tron1-rl-deploy-python — 参考资源

> **来源**：`00_open/tron1-rl-deploy-python/`　｜　**类型**：参考项目
> **关联机型**：limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）
> **定位**：TRON1 Python 部署与策略文件
> **收录**：76 个文件 / 31.4 MB（其中推理策略/模型文件 54 个）
> **已省略**：1 个文件 / 4.7 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **部署与推理**（68 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（8 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （8 个文件）
controllers/  （68 个文件）
    (直接文件)/
    model/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.onnx` | 54 |
| `.yaml` | 10 |
| `.py` | 5 |
| `(无扩展名)` | 4 |
| `.md` | 3 |

## 文件索引（项目内相对路径）

```text
.gitignore
.gitmodules
LICENSE
NOTICE
README.md
README_cn.md
README_en.md
controllers/PointfootController.py
controllers/SolefootController.py
controllers/WheelfootController.py
controllers/__init__.py
controllers/model/PF_P441A/params.yaml
controllers/model/PF_P441A/policy/encoder.onnx
controllers/model/PF_P441A/policy/isaacgym/encoder.onnx
controllers/model/PF_P441A/policy/isaacgym/policy.onnx
controllers/model/PF_P441A/policy/isaaclab/encoder.onnx
controllers/model/PF_P441A/policy/isaaclab/policy.onnx
controllers/model/PF_P441A/policy/policy.onnx
controllers/model/PF_P441B/params.yaml
controllers/model/PF_P441B/policy/encoder.onnx
controllers/model/PF_P441B/policy/isaacgym/encoder.onnx
controllers/model/PF_P441B/policy/isaacgym/policy.onnx
controllers/model/PF_P441B/policy/isaaclab/encoder.onnx
controllers/model/PF_P441B/policy/isaaclab/policy.onnx
controllers/model/PF_P441B/policy/policy.onnx
controllers/model/PF_P441C/params.yaml
controllers/model/PF_P441C/policy/encoder.onnx
controllers/model/PF_P441C/policy/isaacgym/encoder.onnx
controllers/model/PF_P441C/policy/isaacgym/policy.onnx
controllers/model/PF_P441C/policy/isaaclab/encoder.onnx
controllers/model/PF_P441C/policy/isaaclab/policy.onnx
controllers/model/PF_P441C/policy/policy.onnx
controllers/model/PF_P441C2/params.yaml
controllers/model/PF_P441C2/policy/encoder.onnx
controllers/model/PF_P441C2/policy/isaacgym/encoder.onnx
controllers/model/PF_P441C2/policy/isaacgym/policy.onnx
controllers/model/PF_P441C2/policy/isaaclab/encoder.onnx
controllers/model/PF_P441C2/policy/isaaclab/policy.onnx
controllers/model/PF_P441C2/policy/policy.onnx
controllers/model/PF_TRON1A/params.yaml
controllers/model/PF_TRON1A/policy/encoder.onnx
controllers/model/PF_TRON1A/policy/isaacgym/encoder.onnx
controllers/model/PF_TRON1A/policy/isaacgym/policy.onnx
controllers/model/PF_TRON1A/policy/isaaclab/encoder.onnx
controllers/model/PF_TRON1A/policy/isaaclab/policy.onnx
controllers/model/PF_TRON1A/policy/policy.onnx
controllers/model/PF_TRON1B/params.yaml
controllers/model/PF_TRON1B/policy/isaacgym/encoder.onnx
controllers/model/PF_TRON1B/policy/isaacgym/policy.onnx
controllers/model/PF_TRON1B/policy/isaaclab/encoder.onnx
controllers/model/PF_TRON1B/policy/isaaclab/policy.onnx
controllers/model/SF_TRON1A/params.yaml
controllers/model/SF_TRON1A/policy/encoder.onnx
controllers/model/SF_TRON1A/policy/isaacgym/encoder.onnx
controllers/model/SF_TRON1A/policy/isaacgym/policy.onnx
controllers/model/SF_TRON1A/policy/isaaclab/encoder.onnx
controllers/model/SF_TRON1A/policy/isaaclab/policy.onnx
controllers/model/SF_TRON1A/policy/policy.onnx
controllers/model/SF_TRON1B/params.yaml
controllers/model/SF_TRON1B/policy/isaacgym/encoder.onnx
controllers/model/SF_TRON1B/policy/isaacgym/policy.onnx
controllers/model/SF_TRON1B/policy/isaaclab/encoder.onnx
controllers/model/SF_TRON1B/policy/isaaclab/policy.onnx
controllers/model/WF_TRON1A/params.yaml
controllers/model/WF_TRON1A/policy/encoder.onnx
controllers/model/WF_TRON1A/policy/isaacgym/encoder.onnx
controllers/model/WF_TRON1A/policy/isaacgym/policy.onnx
controllers/model/WF_TRON1A/policy/isaaclab/encoder.onnx
controllers/model/WF_TRON1A/policy/isaaclab/policy.onnx
controllers/model/WF_TRON1A/policy/policy.onnx
controllers/model/WF_TRON1B/params.yaml
controllers/model/WF_TRON1B/policy/isaacgym/encoder.onnx
controllers/model/WF_TRON1B/policy/isaacgym/policy.onnx
controllers/model/WF_TRON1B/policy/isaaclab/encoder.onnx
controllers/model/WF_TRON1B/policy/isaaclab/policy.onnx
main.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `doc` | 1 | 4.7 MB | [`doc/_OMITTED.md`](./doc/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
