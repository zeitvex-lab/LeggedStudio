"""
STL 体积计算工具

算法：SignedVolumeOfTriangle
用途：从 STL 文件计算体积，估算机器人质量
"""

import numpy as np
from pathlib import Path
from typing import Dict, Optional
import sys


def calculate_volume_from_stl(stl_path: str) -> float:
    """
    计算 STL 文件的体积（SignedVolumeOfTriangle 算法）

    参数：
        stl_path: STL 文件路径

    返回：
        volume: 体积（立方米）

    注意：
        - 仅对闭合网格准确
        - 非闭合网格可能返回错误结果
    """
    try:
        from stl import mesh
    except ImportError:
        print("错误：需要安装 numpy-stl")
        print("运行：pip install numpy-stl")
        sys.exit(1)

    # 加载 STL
    stl_mesh = mesh.Mesh.from_file(stl_path)

    # 累加有向体积
    volume = 0.0
    for triangle in stl_mesh.vectors:
        v0, v1, v2 = triangle
        # SignedVolumeOfTriangle: v0 · (v1 × v2) / 6
        volume += np.dot(v0, np.cross(v1, v2)) / 6.0

    return abs(volume)


def estimate_mass(
    stl_path: str,
    density: float = 1050.0,
    material: Optional[str] = None
) -> Dict[str, float]:
    """
    估算质量

    参数：
        stl_path: STL 文件路径
        density: 密度 (kg/m³)，如果指定 material 则忽略
        material: 材料名称（'abs_plastic', 'aluminum', 'carbon_fiber', 'steel'）

    返回：
        {
            'volume_m3': 体积（立方米）,
            'mass_kg': 质量（千克）,
            'density': 使用的密度,
            'material': 材料名称
        }
    """
    # 材料密度表
    MATERIAL_DENSITIES = {
        'abs_plastic': 1050,      # ABS 塑料（常用）
        'aluminum': 2700,         # 铝合金
        'carbon_fiber': 1600,     # 碳纤维
        'steel': 7850,            # 钢
        'titanium': 4500,         # 钛合金
    }

    # 选择密度
    if material and material in MATERIAL_DENSITIES:
        density = MATERIAL_DENSITIES[material]
        material_name = material
    else:
        material_name = 'custom'

    # 计算体积
    volume = calculate_volume_from_stl(stl_path)

    # 计算质量
    mass = volume * density

    return {
        'volume_m3': volume,
        'mass_kg': mass,
        'density': density,
        'material': material_name,
        'stl_path': stl_path
    }


def create_test_cube(size: float = 1.0, output_path: str = "test_cube.stl"):
    """
    创建测试立方体 STL（用于算法验证）

    参数：
        size: 立方体边长（米）
        output_path: 输出文件路径

    返回：
        volume: 理论体积
    """
    try:
        from stl import mesh
    except ImportError:
        print("错误：需要安装 numpy-stl")
        sys.exit(1)

    # 定义 8 个顶点
    vertices = np.array([
        [0, 0, 0], [size, 0, 0], [size, size, 0], [0, size, 0],
        [0, 0, size], [size, 0, size], [size, size, size], [0, size, size]
    ])

    # 定义 12 个三角形（立方体 6 个面，每面 2 个三角形）
    faces = np.array([
        [0,3,1], [1,3,2],  # 底面 (-Z)
        [4,5,7], [5,6,7],  # 顶面 (+Z)
        [0,1,4], [1,5,4],  # 前面 (-Y)
        [2,3,6], [3,7,6],  # 后面 (+Y)
        [0,4,3], [3,4,7],  # 左面 (-X)
        [1,2,5], [2,6,5]   # 右面 (+X)
    ])

    # 创建 mesh
    cube = mesh.Mesh(np.zeros(faces.shape[0], dtype=mesh.Mesh.dtype))
    for i, face in enumerate(faces):
        for j in range(3):
            cube.vectors[i][j] = vertices[face[j]]

    # 保存
    cube.save(output_path)
    print(f"✅ 测试立方体已保存：{output_path}")

    return size ** 3


def test_algorithm():
    """测试算法准确性"""
    print("=" * 60)
    print("STL 体积计算算法测试")
    print("=" * 60)

    # 测试 1：立方体
    print("\n【测试 1】立方体（1m × 1m × 1m）")
    cube_path = "test_cube.stl"
    theoretical_volume = create_test_cube(size=1.0, output_path=cube_path)

    calculated_volume = calculate_volume_from_stl(cube_path)
    error = abs(calculated_volume - theoretical_volume) / theoretical_volume * 100

    print(f"理论体积: {theoretical_volume:.6f} m³")
    print(f"计算体积: {calculated_volume:.6f} m³")
    print(f"误差: {error:.4f}%")

    if error < 1.0:
        print("✅ 测试通过（误差 < 1%）")
    else:
        print("❌ 测试失败（误差 >= 1%）")

    # 清理
    Path(cube_path).unlink(missing_ok=True)

    return error < 1.0


def batch_estimate_robot(urdf_dir: str, material: str = 'abs_plastic'):
    """
    批量估算机器人质量

    参数：
        urdf_dir: URDF 目录（包含 STL 文件）
        material: 材料假设
    """
    print("\n" + "=" * 60)
    print(f"批量质量估算（材料：{material}）")
    print("=" * 60)

    urdf_path = Path(urdf_dir)
    stl_files = list(urdf_path.glob("**/*.stl")) + list(urdf_path.glob("**/*.STL"))

    if not stl_files:
        print(f"⚠️  未找到 STL 文件：{urdf_dir}")
        return

    print(f"\n找到 {len(stl_files)} 个 STL 文件\n")

    total_mass = 0.0
    results = []

    for stl_file in stl_files:
        try:
            result = estimate_mass(str(stl_file), material=material)
            total_mass += result['mass_kg']
            results.append(result)

            print(f"📦 {stl_file.name}")
            print(f"   体积: {result['volume_m3']:.6f} m³")
            print(f"   质量: {result['mass_kg']:.3f} kg")
            print()

        except Exception as e:
            print(f"❌ {stl_file.name}: {e}")

    print("-" * 60)
    print(f"总质量估算: {total_mass:.3f} kg")
    print("=" * 60)

    return results, total_mass


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='STL 体积计算和质量估算')
    parser.add_argument('--test', action='store_true', help='运行算法测试')
    parser.add_argument('--stl', type=str, help='单个 STL 文件路径')
    parser.add_argument('--urdf-dir', type=str, help='URDF 目录（批量处理）')
    parser.add_argument('--material', type=str, default='abs_plastic',
                       choices=['abs_plastic', 'aluminum', 'carbon_fiber', 'steel', 'titanium'],
                       help='材料类型')
    parser.add_argument('--density', type=float, help='自定义密度 (kg/m³)')

    args = parser.parse_args()

    # 测试模式
    if args.test:
        success = test_algorithm()
        sys.exit(0 if success else 1)

    # 单文件模式
    if args.stl:
        result = estimate_mass(
            args.stl,
            density=args.density if args.density else None,
            material=args.material if not args.density else None
        )

        print("\n" + "=" * 60)
        print("质量估算结果")
        print("=" * 60)
        print(f"文件: {result['stl_path']}")
        print(f"体积: {result['volume_m3']:.6f} m³")
        print(f"质量: {result['mass_kg']:.3f} kg")
        print(f"密度: {result['density']} kg/m³ ({result['material']})")
        print("=" * 60)
        return

    # 批量模式
    if args.urdf_dir:
        batch_estimate_robot(args.urdf_dir, material=args.material)
        return

    # 无参数：显示帮助
    parser.print_help()


if __name__ == '__main__':
    main()
