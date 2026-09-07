# tools/ 资产工具链

外部工具的包装入口（源在参考项目仓库，避免复制维护）：

## 动作转换（motions/ 前置，LLoco 提供）

```
# G1 CSV → mjlab tracking NPZ（LLoco cli 入口，在其 venv 下运行）
cd C:/Users/31560/Documents/00_open/lain_job/LLoco
uv run csv-to-npz --input-file src/lloco/assets/motions/g1/dance1_subject2.csv \
  --output-name dance1-subject2 --robot g1
```

产物放机器人包 `motions/<name>.npz`（自描述 schema：fps/dof_names/body_names/...，
dof_names 必须与 contract.json 的 actuated_joints 一致——见 docs/ROBOT_PACKAGE.md）。

## 地形生成（rough 场景可再生产物）

```
# MjSpec 程序化地形（平地+box 障碍），桌面 Python：
python -c "
import sys; sys.path.insert(0, 'adapters/mjlab')
from scene_builder import build_flat_scene, add_box_obstacles
..."
```
复杂 hfield 地形参照 unitree_rl_mjlab `scene_terrain.xml` + `visualize_terrain.py`（生成脚本待引入）。
