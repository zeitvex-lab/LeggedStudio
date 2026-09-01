# Task 0.4：STL 体积计算验证

**目标**：验证 STL 体积计算算法准确性，用于自动质量估算

**参考**：
- URDF Studio 几何计算
- 项目愿景第六章（Contract Schema - 质量估算）
- 资产清单中的质量数据

---

## 📋 应用场景

### 为什么需要体积计算？

**问题**：很多 URDF 文件的 `<inertial>` 标签质量不准确或缺失

**解决**：
1. 从 STL 文件计算体积
2. 假设材料密度（如 ABS 塑料 ~1050 kg/m³）
3. 自动估算质量：`质量 = 体积 × 密度`

**用途**：
- Contract Schema 中的质量验证
- URDF 修复建议
- 质量桶分类（S/M/L）

---

## 🧮 算法原理

### SignedVolumeOfTriangle

**思路**：将 STL 网格视为封闭曲面，计算包围的体积

**公式**：
```
V = Σ (v0 · (v1 × v2)) / 6
```

其中：
- v0, v1, v2 是三角形的三个顶点
- × 是叉积
- · 是点积

**特性**：
- ✅ 对凸多面体准确
- ✅ 对闭合网格准确
- ⚠️ 对非闭合网格可能不准（STL 质量问题）

---

## 💻 实现方案

### 方案 A：Python 实现（推荐）

**使用 numpy-stl**：
```python
# stl_volume.py
import numpy as np
from stl import mesh

def calculate_volume(stl_path):
    """
    计算 STL 文件的体积
    
    返回：
        volume: 体积（立方米）
    """
    # 加载 STL
    stl_mesh = mesh.Mesh.from_file(stl_path)
    
    # SignedVolumeOfTriangle
    volume = 0.0
    for triangle in stl_mesh.vectors:
        v0, v1, v2 = triangle
        volume += np.dot(v0, np.cross(v1, v2)) / 6.0
    
    return abs(volume)

def estimate_mass(stl_path, density=1050):
    """
    估算质量
    
    参数：
        stl_path: STL 文件路径
        density: 密度 (kg/m³)，默认 ABS 塑料
    
    返回：
        mass: 质量（kg）
    """
    volume = calculate_volume(stl_path)
    mass = volume * density
    return mass

# 使用示例
if __name__ == '__main__':
    stl_path = 'path/to/go2_base_link.stl'
    
    volume = calculate_volume(stl_path)
    print(f'体积: {volume:.6f} m³')
    
    mass = estimate_mass(stl_path, density=1050)
    print(f'估算质量: {mass:.3f} kg')
```

**依赖**：
```bash
pip install numpy-stl
```

---

### 方案 B：JavaScript 实现（Web 端）

**使用 three.js**：
```javascript
// stlVolume.js
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import * as THREE from 'three';

export function calculateVolume(geometry) {
  const positions = geometry.attributes.position.array;
  let volume = 0;

  // 遍历三角形
  for (let i = 0; i < positions.length; i += 9) {
    const v0 = new THREE.Vector3(positions[i], positions[i+1], positions[i+2]);
    const v1 = new THREE.Vector3(positions[i+3], positions[i+4], positions[i+5]);
    const v2 = new THREE.Vector3(positions[i+6], positions[i+7], positions[i+8]);

    // SignedVolumeOfTriangle
    const cross = new THREE.Vector3();
    cross.crossVectors(v1, v2);
    volume += v0.dot(cross) / 6;
  }

  return Math.abs(volume);
}

export function estimateMass(geometry, density = 1050) {
  const volume = calculateVolume(geometry);
  return volume * density;
}
```

---

## 🧪 测试用例

### 测试 1：标准几何体

**目的**：验证算法准确性

**测试对象**：
```python
# test_standard_shapes.py
import numpy as np
from stl import mesh

def create_cube_stl(size=1.0):
    """创建立方体 STL"""
    # 定义 8 个顶点
    vertices = np.array([
        [0, 0, 0], [size, 0, 0], [size, size, 0], [0, size, 0],
        [0, 0, size], [size, 0, size], [size, size, size], [0, size, size]
    ])
    
    # 定义 12 个三角形（立方体有 6 个面，每面 2 个三角形）
    faces = np.array([
        [0,3,1], [1,3,2],  # 底面
        [4,5,7], [5,6,7],  # 顶面
        [0,1,4], [1,5,4],  # 前面
        [2,3,6], [3,7,6],  # 后面
        [0,4,3], [3,4,7],  # 左面
        [1,2,5], [2,6,5]   # 右面
    ])
    
    cube = mesh.Mesh(np.zeros(faces.shape[0], dtype=mesh.Mesh.dtype))
    for i, face in enumerate(faces):
        for j in range(3):
            cube.vectors[i][j] = vertices[face[j]]
    
    return cube

# 测试
cube = create_cube_stl(1.0)
volume = calculate_volume_from_mesh(cube)
print(f'立方体体积: {volume:.6f} m³')
print(f'理论体积: 1.0 m³')
print(f'误差: {abs(volume - 1.0) / 1.0 * 100:.2f}%')

# 验收：误差 < 1%
assert abs(volume - 1.0) / 1.0 < 0.01
```

**预期结果**：
- 立方体（1m × 1m × 1m）：体积 = 1.0 m³
- 球体（半径 1m）：体积 ≈ 4.189 m³
- 圆柱（半径 1m，高 2m）：体积 ≈ 6.283 m³

**验收**：误差 < 1%

---

### 测试 2：Go2 base_link

**目的**：验证真实模型

**步骤**：
```python
# test_go2.py

# 1. 找到 Go2 base_link STL
import glob
go2_stls = glob.glob('**/go2*base*.stl', recursive=True)
print(f'找到 {len(go2_stls)} 个文件')

# 2. 计算体积和质量
for stl_path in go2_stls:
    volume = calculate_volume(stl_path)
    mass = estimate_mass(stl_path, density=1050)  # ABS 塑料
    
    print(f'\n文件: {stl_path}')
    print(f'体积: {volume:.6f} m³')
    print(f'估算质量: {mass:.3f} kg')

# 3. 对比 URDF 中的质量
# 从 asset inventory 查找 Go2 的实际质量
# Go2 整机质量约 15 kg（M 级）
```

**预期**：
- base_link 估算质量：2-5 kg（合理范围）
- 整机质量（累加所有 link）：10-20 kg

**验收**：
- [ ] 估算值在合理范围
- [ ] 与 URDF 标注差异 < 20%（如果有标注）

---

### 测试 3：不同密度材料

**材料密度参考**：
```python
MATERIAL_DENSITIES = {
    'abs_plastic': 1050,      # ABS 塑料
    'aluminum': 2700,         # 铝合金
    'carbon_fiber': 1600,     # 碳纤维
    'steel': 7850,            # 钢
}

# 测试不同材料假设
for material, density in MATERIAL_DENSITIES.items():
    mass = estimate_mass(stl_path, density)
    print(f'{material}: {mass:.3f} kg')
```

---

## ✅ 验收标准

### 算法准确性
- [ ] 标准几何体误差 < 1%
- [ ] Go2 模型估算合理（2-5 kg for base_link）
- [ ] 与 URDF 标注差异 < 20%

### 代码质量
- [ ] Python 实现可运行
- [ ] 支持批量计算
- [ ] 错误处理（文件不存在、非闭合网格）

### 文档
- [ ] 算法原理说明
- [ ] 使用示例
- [ ] 密度参考表

---

## 📊 任务拆解

### Task 0.4.1：实现算法（Python）
- **预计**：1 小时
- **验收**：立方体测试通过

### Task 0.4.2：测试标准几何体
- **预计**：30 分钟
- **验收**：误差 < 1%

### Task 0.4.3：测试 Go2 模型
- **预计**：1 小时
- **验收**：估算合理

### Task 0.4.4：文档和工具
- **预计**：30 分钟
- **验收**：README + 使用示例

---

## 🔗 应用集成

### 集成到 Contract Schema

**自动质量估算**：
```python
# contracts/utils/mass_estimator.py
from pathlib import Path

def estimate_robot_mass(urdf_path):
    """
    估算机器人总质量
    
    返回：
        {
            'total_mass': float,
            'links': {
                'base_link': {'volume': ..., 'mass': ...},
                'leg_FL': {'volume': ..., 'mass': ...},
                ...
            },
            'method': 'stl_volume',
            'density_assumed': 1050
        }
    """
    pass
```

### 集成到 URDF 验证

**Contract selfcheck**：
```python
# contracts/selfcheck.py

def check_mass_consistency(contract):
    """检查质量一致性"""
    
    # 如果 URDF 有质量标注
    if contract.urdf_mass:
        # 计算 STL 估算质量
        estimated_mass = estimate_robot_mass(contract.urdf_path)
        
        # 对比
        diff_percent = abs(contract.urdf_mass - estimated_mass) / contract.urdf_mass
        
        if diff_percent > 0.2:  # 差异 > 20%
            warnings.append(f'质量差异 {diff_percent:.1%}，建议检查')
```

---

## 🎯 Phase 1 扩展

**如果需要更高精度**：
- 支持多材料（不同 link 不同密度）
- 考虑空腔（内部结构）
- CAD 模型精确计算（非 STL）

**Phase 0 不做这些**，只验证基本算法。

---

**下一步**：实现 Python 版本算法
