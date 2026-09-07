# tools/ 资产工具链

外部工具的包装入口（源在参考项目仓库，避免复制维护）：

## 地形生成（rough 场景可再生产物）

```
# MjSpec 程序化地形（平地+box 障碍），桌面 Python：
python -c "
import sys; sys.path.insert(0, 'adapters/mjlab')
from scene_builder import build_flat_scene, add_box_obstacles
..."
```
复杂 hfield 地形参照 unitree_rl_mjlab `scene_terrain.xml` + `visualize_terrain.py`（生成脚本待引入）。
