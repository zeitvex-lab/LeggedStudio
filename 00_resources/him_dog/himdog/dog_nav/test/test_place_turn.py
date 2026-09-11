#!/usr/bin/env python3
# ========================================================================================
# test_place_turn.py — 测试放置自动转身角度计算
# ========================================================================================
#
# 验证 CalcPlaceTurnAngle 的逻辑:
#   给定放货站位坐标、归位区坐标、当前朝向、吸盘侧
#   → 计算转身角度
#   → 验证转身后吸盘确实对准归位区
#
# 新布局（放货站位 10-14，归位区 01-04）:
#   【点13】【01】【点10】【02】【点11】【03】【点12】【04】【点14】
#   点10: 左吸盘→zone1(01), 右吸盘→zone2(02)
#   点11: 左吸盘→zone2(02), 右吸盘→zone3(03)
#   点12: 左吸盘→zone3(03), 右吸盘→zone4(04)
#   点13: 右吸盘→zone1(01)  ← 消转圈站位（zone1在点13右侧）
#   点14: 左吸盘→zone4(04)  ← 消转圈站位（zone4在点14左侧）
#
# 每个 (吸盘侧, zone) 都有唯一自然站位，turn 永远是小角度修正，无转圈倒车
#
# 运行:
#   python3 test/test_place_turn.py

import math
import sys

# ========================================================================================
# 放货映射（与 navigation_dog.cpp LoadStaticMaps 一致）
# ========================================================================================
# 放货站位 × 吸盘侧 → 归位区编号
PLACE_ZONE_MAP = {
    10: {"left": 1, "right": 2},
    11: {"left": 2, "right": 3},
    12: {"left": 3, "right": 4},
    13: {"right": 1},
    14: {"left": 4},
}


# ========================================================================================
# 核心算法（与 C++ 版 CalcPlaceTurnAngle 一致）
# ========================================================================================

def normalize_angle(a):
    """将角度归一化到 [-PI, PI]"""
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def calc_place_turn_angle(place_coord, zone_coord, cur_yaw, direction):
    """
    计算放置时转身角度

    参数:
      place_coord: (px, py) 放货站位坐标
      zone_coord:  (zx, zy) 归位区坐标
      cur_yaw:     当前朝向（弧度）
      direction:   "left" 或 "right"

    返回:
      转身角度（弧度），正值=左转，负值=右转
    """
    px, py = place_coord
    zx, zy = zone_coord

    # 归位区相对于放货站位的方向
    zone_angle = math.atan2(zy - py, zx - px)

    # 吸盘侧当前方向
    if direction == "left":
        sucker_angle = cur_yaw + math.pi / 2.0
    else:
        sucker_angle = cur_yaw - math.pi / 2.0

    # 转身角度 = 让吸盘对准归位区
    turn = normalize_angle(zone_angle - sucker_angle)
    return turn


# ========================================================================================
# 测试框架
# ========================================================================================

def deg(rad):
    return rad * 180.0 / math.pi


def verify(place_coord, zone_coord, cur_yaw, direction):
    """
    计算转身角度并验证正确性
    验证方法: 转身后，吸盘方向应该对准归位区
    """
    turn = calc_place_turn_angle(place_coord, zone_coord, cur_yaw, direction)

    # 转身后的朝向
    new_yaw = cur_yaw + turn

    # 转身后吸盘方向
    if direction == "left":
        sucker_after = new_yaw + math.pi / 2.0
    else:
        sucker_after = new_yaw - math.pi / 2.0

    # 归位区方向
    zone_angle = math.atan2(zone_coord[1] - place_coord[1],
                             zone_coord[0] - place_coord[0])

    # 误差
    error = abs(normalize_angle(zone_angle - sucker_after))

    ok = error < 0.01  # 0.01 rad ≈ 0.6°

    return ok, turn, error


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.total = 0

    def check(self, name, condition, detail=""):
        self.total += 1
        if condition:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            print(f"  ❌ {name}  {detail}")

    def summary(self):
        print(f"\n{'='*60}")
        print(f"  结果: {self.passed}/{self.total} 通过", end="")
        if self.failed == 0:
            print("  🎉 全部通过！")
        else:
            print(f"  ❌ {self.failed} 个失败")
        print(f"{'='*60}")
        return self.failed == 0


# ========================================================================================
# 测试用例
# ========================================================================================

def test_basic():
    """基础测试：新布局，放货站位 10/11/12，归位区在上方"""
    print("\n" + "="*60)
    print("  测试1: 基础场景（新布局，归位区在上方）")
    print("="*60)

    r = TestResult()

    # 场地布局（归位区在放货站位正上方）:
    #   zone1(0,2)  zone2(1,2)  zone3(2,2)  zone4(3,2)   ← 归位区
    #   点13(-1,1) 点10(0,1) 点11(1,1) 点12(2,1) 点14(3,1)  ← 放货站位
    zones = {1: (0, 2), 2: (1, 2), 3: (2, 2), 4: (3, 2)}
    places = {13: (-1, 1), 10: (0, 1), 11: (1, 1), 12: (2, 1), 14: (3, 1)}

    cur_yaw = math.pi / 2.0  # 朝上（面朝归位区）

    # 遍历每个站位 × 吸盘侧（每个组合都有自然站位，0 转向）
    for pp, side_map in sorted(PLACE_ZONE_MAP.items()):
        for d, zone_id in side_map.items():
            ok, turn, err = verify(places[pp], zones[zone_id], cur_yaw, d)
            r.check(
                f"点{pp}→zone{zone_id}, 朝上, {d}吸盘: 转{deg(turn):7.1f}° (误差{deg(err):.2f}°)",
                ok, f"误差={deg(err):.2f}°")

    return r


def test_no_turn_completeness():
    """★ 验证消转圈完备性：每个 (吸盘侧, zone) 都有自然站位

    新布局加了点13(右吸zone1)和点14(左吸zone4)后，所有 (吸盘侧, zone) 组合
    都能在 PLACE_ZONE_MAP 里反查到唯一站位 —— 这才是"无转圈"的本质保证
    （跟 turn 角度大小无关，turn 只是到位后的微调）。

    本测试验证两件事:
      1. 反查完备：遍历 8 个 (吸盘侧, zone) 组合，每个都能找到站位
      2. 角度合理：用对应站位坐标算 turn，吸盘都能对准目标 zone（误差 < 0.6°）
    """
    print("\n" + "="*60)
    print("  测试2: ★ 消转圈完备性（点13/14 让每组合都有自然站位）")
    print("="*60)

    r = TestResult()

    # 模拟坐标（归位区在上行，站位在下行，13/14 在两端）
    zones = {1: (0, 2), 2: (1, 2), 3: (2, 2), 4: (3, 2)}
    places = {13: (-1, 1), 10: (0, 1), 11: (1, 1), 12: (2, 1), 14: (3, 1)}

    cur_yaw = math.pi / 2.0  # 朝上（面朝归位区）

    # 反查表：吸盘侧 + zone → 站位
    reverse_map = {}
    for pp, side_map in PLACE_ZONE_MAP.items():
        for d, zone_id in side_map.items():
            reverse_map[(d, zone_id)] = pp

    # 遍历 8 个组合，验证反查完备 + 角度对准
    for direction in ["left", "right"]:
        for zone_id in [1, 2, 3, 4]:
            key = (direction, zone_id)
            if key not in reverse_map:
                r.check(f"{direction}吸盘放zone{zone_id}: 有自然站位", False, "反查不到站位（需转圈）")
                continue
            pp = reverse_map[key]
            ok, turn, err = verify(places[pp], zones[zone_id], cur_yaw, direction)
            r.check(
                f"{direction}吸盘放zone{zone_id} → 点{pp}: 转{deg(turn):6.1f}° 对准(误差{deg(err):.2f}°)",
                ok, f"err={deg(err):.2f}°")

    return r


def test_different_yaw():
    """测试不同初始朝向"""
    print("\n" + "="*60)
    print("  测试3: 不同初始朝向")
    print("="*60)

    r = TestResult()

    place = (1, 1)   # 点11
    zone = (1, 2)    # zone2 在正上方

    for yaw_deg, yaw_label in [(0, "→右"), (90, "↑上"), (180, "←左"), (-90, "↓下"), (45, "↗右上")]:
        cur_yaw = math.radians(yaw_deg)
        for d in ["left", "right"]:
            ok, turn, err = verify(place, zone, cur_yaw, d)
            r.check(
                f"yaw={yaw_deg:4d}°{yaw_label}, {d}吸盘: 转{deg(turn):7.1f}° (误差{deg(err):.3f}°)",
                ok, f"误差={deg(err):.3f}°")

    return r


def test_zone_directions():
    """测试归位区在不同方向"""
    print("\n" + "="*60)
    print("  测试4: 归位区在不同方向（算法通用性）")
    print("="*60)

    r = TestResult()

    place = (0, 0)

    zone_tests = [
        ((1, 0), "→右"),
        ((0, 1), "↑上"),
        ((-1, 0), "←左"),
        ((0, -1), "↓下"),
        ((1, 1), "↗右上"),
        ((-1, 1), "↖左上"),
        ((1, -1), "↘右下"),
        ((-1, -1), "↙左下"),
    ]

    cur_yaw = 0

    for zone, label in zone_tests:
        for d in ["left", "right"]:
            ok, turn, err = verify(place, zone, cur_yaw, d)
            r.check(
                f"zone在{label}, {d}吸盘: 转{deg(turn):7.1f}° (误差{deg(err):.3f}°)",
                ok, f"误差={deg(err):.3f}°")

    return r


def test_real_field():
    """模拟真实场地场景（所有站位 × 所有朝向 × 左右吸盘）"""
    print("\n" + "="*60)
    print("  测试5: 模拟真实场地（站位10-14 × 朝向 × 左右吸盘）")
    print("="*60)

    r = TestResult()

    # 模拟场地坐标（归位区在上行，站位在下行，13/14 在两端）
    zones = {1: (0.0, 2.0), 2: (1.0, 2.0), 3: (2.0, 2.0), 4: (3.0, 2.0)}
    places = {13: (-1.0, 1.0), 10: (0.0, 1.0), 11: (1.0, 1.0), 12: (2.0, 1.0), 14: (3.0, 1.0)}

    yaws = [
        (0, "→右"),
        (math.pi / 2, "↑上（面朝归位区）"),
        (math.pi, "←左"),
        (-math.pi / 2, "↓下（背朝归位区）"),
    ]

    for pp, side_map in sorted(PLACE_ZONE_MAP.items()):
        for d, zone_id in side_map.items():
            for yaw, yaw_label in yaws:
                ok, turn, err = verify(places[pp], zones[zone_id], yaw, d)
                detail = f"误差={deg(err):.3f}°" if not ok else ""
                r.check(
                    f"点{pp}→zone{zone_id}, {yaw_label}, {d}吸盘: 转{deg(turn):7.1f}°",
                    ok, detail)

    return r


def test_turn_values():
    """验证具体转向值是否符合直觉"""
    print("\n" + "="*60)
    print("  测试6: 验证具体转向值")
    print("="*60)

    r = TestResult()

    place = (0, 0)
    zone = (0, 1)  # 正上方

    # 狗朝上(yaw=π/2), 左吸盘在左侧(π方向)
    cur_yaw = math.pi / 2
    turn = calc_place_turn_angle(place, zone, cur_yaw, "left")
    r.check(f"朝上, 左吸盘, zone在上方 → 右转90° (实际{deg(turn):.1f}°)",
            abs(turn + math.pi/2) < 0.01, f"turn={deg(turn):.1f}°")

    # 狗朝上(yaw=π/2), 右吸盘在右侧(0方向)
    turn = calc_place_turn_angle(place, zone, cur_yaw, "right")
    r.check(f"朝上, 右吸盘, zone在上方 → 左转90° (实际{deg(turn):.1f}°)",
            abs(turn - math.pi/2) < 0.01, f"turn={deg(turn):.1f}°")

    # 狗朝右(yaw=0), 左吸盘在上方(π/2)
    cur_yaw = 0
    turn = calc_place_turn_angle(place, zone, cur_yaw, "left")
    r.check(f"朝右, 左吸盘, zone在上方 → 不转0° (实际{deg(turn):.1f}°)",
            abs(turn) < 0.01, f"turn={deg(turn):.1f}°")

    # 狗朝右(yaw=0), 右吸盘在下方(-π/2), zone在上方 → 转180°（转圈倒车情形）
    turn = calc_place_turn_angle(place, zone, cur_yaw, "right")
    r.check(f"朝右, 右吸盘, zone在上方 → 转180° (实际{deg(turn):.1f}°)",
            abs(abs(turn) - math.pi) < 0.01, f"turn={deg(turn):.1f}°")

    return r


# ========================================================================================
# 可视化辅助
# ========================================================================================

def print_field_visual():
    """打印场地布局示意"""
    print("\n" + "="*60)
    print("  场地布局示意（15 节点）")
    print("="*60)
    print("""
       zone1     zone2     zone3     zone4          归位区
        (01)     (02)      (03)      (04)

   点13  点10      点11      点12      点14          放货站位
    右→  ←左 右→  ←左 右→   ←左 右→   ←左
         |   |    |   |     |   |     |
        点10     点11       点12      点14

    映射（每个组合都有自然站位，0 转向）:
      点10: 左→zone1, 右→zone2
      点11: 左→zone2, 右→zone3
      点12: 左→zone3, 右→zone4
      点13: 右→zone1   ← 消转圈（zone1 在点13右侧）
      点14: 左→zone4   ← 消转圈（zone4 在点14左侧）
    """)


# ========================================================================================
# 主程序
# ========================================================================================

def main():
    print("=" * 60)
    print("  ★ 放置自动转身角度计算 — 测试（新布局）")
    print("=" * 60)

    print_field_visual()

    results = []
    results.append(test_basic())
    results.append(test_no_turn_completeness())
    results.append(test_different_yaw())
    results.append(test_zone_directions())
    results.append(test_real_field())
    results.append(test_turn_values())

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total = sum(r.total for r in results)

    print(f"\n{'='*60}")
    print(f"  ★ 总计: {total_passed}/{total} 通过", end="")
    if total_failed == 0:
        print("  🎉 全部通过！")
    else:
        print(f"  ❌ {total_failed} 个失败")
    print(f"{'='*60}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
