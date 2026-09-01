"""
Contract 质量估算工具

集成 STL 体积计算到 Contract Schema
用于自动验证 URDF 质量标注的合理性
"""

from pathlib import Path
from typing import Dict, List, Optional
import warnings


def estimate_robot_mass_from_urdf(
    urdf_path: str,
    density: float = 1050.0,
    material: Optional[str] = None
) -> Dict:
    """
    从 URDF 估算机器人总质量

    参数：
        urdf_path: URDF 文件路径
        density: 默认密度 (kg/m³)
        material: 材料名称

    返回：
        {
            'total_mass_kg': float,          # 总质量
            'links': {                       # 每个 link 的详情
                'base_link': {
                    'volume_m3': float,
                    'mass_kg': float,
                    'stl_path': str
                },
                ...
            },
            'method': 'stl_volume',
            'density': float,
            'material': str
        }
    """
    # TODO: 实现完整 URDF 解析和批量计算
    # Phase 0: 仅提供接口定义
    raise NotImplementedError("Phase 1 实现")


def check_mass_consistency(
    urdf_path: str,
    urdf_declared_mass: Optional[float] = None,
    tolerance: float = 0.2
) -> Dict:
    """
    检查 URDF 质量标注的一致性

    参数：
        urdf_path: URDF 文件路径
        urdf_declared_mass: URDF 中声明的总质量（如有）
        tolerance: 容许误差（默认 20%）

    返回：
        {
            'consistent': bool,              # 是否一致
            'declared_mass': float,          # 声明质量
            'estimated_mass': float,         # 估算质量
            'diff_percent': float,           # 差异百分比
            'warnings': List[str]            # 警告信息
        }
    """
    # TODO: Phase 1 实现
    raise NotImplementedError("Phase 1 实现")


def classify_size_by_mass(mass_kg: float) -> str:
    """
    根据质量分类机器人尺寸

    参数：
        mass_kg: 质量（千克）

    返回：
        'S' | 'M' | 'L'
    """
    if mass_kg < 15:
        return 'S'
    elif mass_kg < 35:
        return 'M'
    else:
        return 'L'


# Phase 0: 仅提供接口定义
# Phase 1: 完整实现
# Phase 2: 与 Contract selfcheck 集成
