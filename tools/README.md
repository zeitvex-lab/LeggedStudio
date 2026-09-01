# STL 体积计算工具

快速质量估算工具，基于 STL 文件计算体积。

---

## 安装依赖

```bash
pip install numpy-stl
```

---

## 使用方法

### 1. 测试算法

```bash
python tools/stl_volume.py --test
```

**输出**：
```
STL 体积计算算法测试
理论体积: 1.000000 m³
计算体积: 1.000000 m³
误差: 0.0001%
✅ 测试通过
```

---

### 2. 单文件估算

```bash
python tools/stl_volume.py --stl path/to/base_link.stl --material abs_plastic
```

**输出**：
```
质量估算结果
文件: base_link.stl
体积: 0.002500 m³
质量: 2.625 kg
密度: 1050 kg/m³ (abs_plastic)
```

---

### 3. 批量估算（整个机器人）

```bash
python tools/stl_volume.py --urdf-dir path/to/go2_description --material aluminum
```

**输出**：
```
批量质量估算（材料：aluminum）
找到 15 个 STL 文件

📦 base_link.stl
   体积: 0.002500 m³
   质量: 6.750 kg

📦 leg_FL.stl
   体积: 0.000500 m³
   质量: 1.350 kg

...

总质量估算: 18.500 kg
```

---

### 4. 自定义密度

```bash
python tools/stl_volume.py --stl base_link.stl --density 1200
```

---

## 支持的材料

| 材料 | 密度 (kg/m³) | 说明 |
|---|---|---|
| `abs_plastic` | 1050 | ABS 塑料（默认） |
| `aluminum` | 2700 | 铝合金 |
| `carbon_fiber` | 1600 | 碳纤维 |
| `steel` | 7850 | 钢 |
| `titanium` | 4500 | 钛合金 |

---

## Python API

```python
from tools.stl_volume import calculate_volume_from_stl, estimate_mass

# 计算体积
volume = calculate_volume_from_stl('base_link.stl')
print(f'体积: {volume} m³')

# 估算质量
result = estimate_mass('base_link.stl', material='aluminum')
print(f"质量: {result['mass_kg']} kg")
```

---

## 算法说明

**SignedVolumeOfTriangle**

对于 STL 网格的每个三角形 (v0, v1, v2)：
```
V_triangle = (v0 · (v1 × v2)) / 6
V_total = Σ |V_triangle|
```

**限制**：
- ✅ 闭合网格：准确
- ⚠️ 非闭合网格：可能不准确

---

## 测试结果

```
✅ 立方体（1m³）：误差 < 0.001%
✅ Go2 base_link：估算 2-5 kg（合理）
```

---

## 集成到 Contract

见 `contracts/utils/mass_estimator.py`（待实现）
