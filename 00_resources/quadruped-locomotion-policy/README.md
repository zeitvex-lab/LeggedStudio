# quadruped-locomotion-policy — 参考资源

> **来源**：HuggingFace [`huggingface.co/Kyu3224/quadruped-locomotion-policy`](https://huggingface.co/Kyu3224/quadruped-locomotion-policy) @ `80bed8c`（2026-09-23 抓取，详见 [`_SOURCE.md`](./_SOURCE.md)）　｜　**类型**：推理策略参考（Isaac Lab 训练 / ONNX·PT）
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go1（宇树 Go1 四足）
> **定位**：quadruped-locomotion-policy（HuggingFace Kyu3224）：Isaac Lab 训练的四足运动策略集合——平坦地形 48 维观测、崎岖地形 48 + 187 高度图 = 235 维观测，12 维力矩动作；覆盖 anymal_c / hound1 / hound2 / spot / unitree_go1 / unitree_go2（含 actuator_net）；仓库为 LFS 指针（ONNX/PT 实体未拉取）
> **收录**：45 个文件 / 9 KB（其中推理策略/模型文件 41 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **部署与推理**（41 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（4 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
onnx/  （21 个文件）
    anymal_c/
    hound1/
    hound2/
    spot/
    unitree_go1/
    unitree_go2/
pt/  （20 个文件）
    anymal_c/
    hound1/
    hound2/
    spot/
    unitree_go1/
    unitree_go2/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.onnx` | 21 |
| `.pt` | 20 |
| `(无扩展名)` | 2 |
| `.md` | 2 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.gitignore
README_upstream.md
_SOURCE.md
onnx/anymal_c/flat.onnx
onnx/anymal_c/flat_robust_100hz.onnx
onnx/hound1/flat.onnx
onnx/hound1/flat_pos.onnx
onnx/hound1/flat_robust.onnx
onnx/hound1/flat_robust_100hz.onnx
onnx/hound1/rough.onnx
onnx/hound2/flat.onnx
onnx/hound2/flat_robust.onnx
onnx/hound2/flat_robust_100hz.onnx
onnx/spot/flat.onnx
onnx/spot/flat_robust_100hz.onnx
onnx/unitree_go1/flat.onnx
onnx/unitree_go1/flat_pos.onnx
onnx/unitree_go1/flat_robust.onnx
onnx/unitree_go1/flat_robust_100hz.onnx
onnx/unitree_go1/rough.onnx
onnx/unitree_go2/flat.onnx
onnx/unitree_go2/flat_robust.onnx
onnx/unitree_go2/flat_robust_100hz.onnx
onnx/unitree_go2/rough.onnx
pt/anymal_c/flat.pt
pt/anymal_c/flat_robust_100hz.pt
pt/hound1/flat.pt
pt/hound1/flat_pos.pt
pt/hound1/flat_robust.pt
pt/hound1/flat_robust_100hz.pt
pt/hound2/flat.pt
pt/hound2/flat_robust.pt
pt/hound2/flat_robust_100hz.pt
pt/spot/flat.pt
pt/spot/flat_robust_100hz.pt
pt/unitree_go1/actuator_net.pt
pt/unitree_go1/flat.pt
pt/unitree_go1/flat_pos.pt
pt/unitree_go1/flat_robust.pt
pt/unitree_go1/flat_robust_100hz.pt
pt/unitree_go1/rough.pt
pt/unitree_go2/flat.pt
pt/unitree_go2/flat_robust.pt
pt/unitree_go2/flat_robust_100hz.pt
```
