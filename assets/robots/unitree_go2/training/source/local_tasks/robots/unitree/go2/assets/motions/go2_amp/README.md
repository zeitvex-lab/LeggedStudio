# Go2 AMP 专家动作数据（`*.txt`）

## 为什么在这里

`local_tasks/robots/unitree/go2/tasks/go2_skills/amp_dreamwaq/motion.py` 的
`Go2AmpMotionLoader` 按 **相对自身** 的路径读取本目录：

```python
root = Path(__file__).parents[3] / "assets" / "motions" / "go2_amp"
...
for path in sorted(root.glob("*.txt")):
    payload = json.loads(path.read_text())
```

缺任何一个 `.txt` 都会 `FileNotFoundError: No Go2 AMP motion files found in …`。
**2026-09-20 前本目录为空**，导致 `go2-amp-dreamwaq` profile 自迁入起就**无法训练**
（冒烟建环境即失败）——训练源搬了、数据没搬。

## 出处（可复核）

| | |
|---|---|
| 上游 | `00_resources/lain_job/LLoco/src/lloco/assets/motions/go2_amp/` |
| 副本校验 | `00_resources/LainLab/src/assets/motions/go2_amp/` 与上表**逐字节相同**（13/13 文件 sha256 一致，2026-09-20 实测） |
| 许可 | Apache-2.0（`00_resources/lain_job/LLoco/LICENSE`） |
| 文件 | 13 个：`backward / forward / forward_left / forward_right / left / left_new / right / right_new / rotate / rotate_inverse / stand / turn_left / turn_right` |
| 体积 | 1.135 MB（合计 2286 帧） |

## 格式契约（加载器依赖，改数据前先读）

每个 `.txt` 是 **JSON**，三个键：`Frames` / `FrameDuration` / `MotionWeight`。

- `Frames`：`(N, 49)` 的二维数组（**49 维**，不是判别器吃的 31 维）；
- `FrameDuration`：本段动作的帧间隔（本批 0.02 或 0.04 s；源为 25 Hz，策略为 50 Hz，
  故加载器按**连续时间**插值取样，而不是拿相邻帧当转移）；
- `MotionWeight`：该段被采样的权重。

`Go2AmpMotionLoader._state_at_time` 把 49 维切成判别器用的 **31 维**：

```
data[:, 7:19]  (12)  → q
data[:, 31:37] ( 6)  → 体线/角速度
data[:, 37:49] (12)  → dq
data[:, 2:3]   ( 1)  → 地形相对根高度
─────────────────────
              31 维
```

（四元数与足尖字段被显式省略，见该方法内注释。）
