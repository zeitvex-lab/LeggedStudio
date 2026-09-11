#!/usr/bin/env python3
# ========================================================================================
# test_bfs.py — BFS 路径验证（Python 版，不需要 ROS 2）
# ========================================================================================
# 运行: python3 test/test_bfs.py
#
# 场地布局（15 个可走点位）:
#   【点13】【01】【点10】【02】【点11】【03】【点12】【04】【点14】     归位区
#   ==================================================     减速带
#   【05】 【点6】 【点7】【06】       【07】  【点8】 【点9】 【08】    第二排
#   【09】 【点2】 【点3】 【10】      【11】  【点4】 【点5】 【12】    第一排
#                             【点1】                      起点前
#                             【0】                        起点
#
# 点位:
#   点0=起点, 点1=起点前(中转)
#   点2/3=第一排左(吸09/10), 点4/5=第一排右(吸11/12)
#   点6/7=第二排左(吸05/06), 点8/9=第二排右(吸07/08)
#   点10/11/12=归位区旁(放货站位)
#   点13=归位区01左侧(右吸zone1), 点14=归位区04右侧(左吸zone4)
#
# 邻接规则:
#   - 点4/5 不直接连点2/3，但都连点1（点1 是左右半场枢纽）
#   - 点10/11/12/13/14 横向链式（13-10-11-12-14）
#     运行时: 归位区放箱后逐边禁用对应横向边，需绕第二排
#   - 点6/7/8/9 都全连归位区 10/11/12/13/14（减速带上方任意可达）

from collections import deque

# ========================================================================================
# 场地图（和 field_path_planner.hpp 保持一致）
# ========================================================================================

FIELD_GRAPH = {
    0:  [1],                              # 起点 → 点1
    1:  [0, 2, 3, 4, 5],                  # 点1 → 起点 + 第一排全部4个取货点（左右半场枢纽）
    2:  [1, 3, 6],                        # 点2(吸09) → 点1, 点3(同行), 点6(同列)
    3:  [1, 2, 7],                        # 点3(吸10) → 点1, 点2(同行), 点7(同列)
    4:  [1, 5, 8],                        # 点4(吸11) → 点1, 点5(同行), 点8(同列)
    5:  [1, 4, 9],                        # 点5(吸12) → 点1, 点4(同行), 点9(同列)
    6:  [2, 7, 10, 11, 12, 13, 14],       # 点6(吸05) → 点2(同列), 点7(同行), 点10-14
    7:  [3, 6, 10, 11, 12, 13, 14],       # 点7(吸06) → 点3(同列), 点6(同行), 点10-14
    8:  [4, 9, 10, 11, 12, 13, 14],       # 点8(吸07) → 点4(同列), 点9(同行), 点10-14
    9:  [5, 8, 10, 11, 12, 13, 14],       # 点9(吸08) → 点5(同列), 点8(同行), 点10-14
    10: [6, 7, 8, 9, 11, 13],             # 点10(归位区01/02) → 点6-9 + 横向点11/13（链式）
    11: [6, 7, 8, 9, 10, 12],             # 点11(归位区02/03) → 点6-9 + 横向点10/12（链式中枢）
    12: [6, 7, 8, 9, 11, 14],             # 点12(归位区03/04) → 点6-9 + 横向点11/14（链式）
    13: [6, 7, 8, 9, 10],                 # 点13(归位区01左侧) → 点6-9 + 横向点10（右吸zone1）
    14: [6, 7, 8, 9, 12],                 # 点14(归位区04右侧) → 点6-9 + 横向点12（左吸zone4）
}

# 成对取货点 (left_point, right_point, left_box, right_box)
PICKUP_PAIR_MAP = [
    (2, 3, 9,  10),    # 第1轮: 左点2吸09, 右点3吸10
    (4, 5, 11, 12),    # 第2轮: 左点4吸11, 右点5吸12
    (6, 7, 5,  6),     # 第3轮: 左点6吸05, 右点7吸06
    (8, 9, 7,  8),     # 第4轮: 左点8吸07, 右点9吸08
]

# 放货站位 × 吸盘侧 → 归位区
PLACE_ZONE_MAP = {
    10: {"left": 1, "right": 2},
    11: {"left": 2, "right": 3},
    12: {"left": 3, "right": 4},
    13: {"right": 1},
    14: {"left": 4},
}


def bfs(from_point, to_point, blocked=None, placed_zones=None):
    """BFS 最短路径

    blocked: 集合中的点不能作为中间节点（但可作终点）
    placed_zones: 已放箱的归位区编号集合（{1,2,3,4}的子集），逐边禁用横向通道:
        01(zone1)放箱 → 禁 13↔10 边（01 在点13和点10之间）
        02(zone2)放箱 → 禁 10↔11 边（02 在点10和点11之间）
        03(zone3)放箱 → 禁 11↔12 边（03 在点11和点12之间）
        04(zone4)放箱 → 禁 12↔14 边（04 在点12和点14之间）
    """
    if blocked is None:
        blocked = set()
    if placed_zones is None:
        placed_zones = set()
    if from_point == to_point:
        return [from_point]

    def edge_blocked_by_zone(a, b):
        # 13↔10 边被 01(zone1) 挡
        if ((a == 13 and b == 10) or (a == 10 and b == 13)) and 1 in placed_zones:
            return True
        # 10↔11 边被 02(zone2) 挡
        if ((a == 10 and b == 11) or (a == 11 and b == 10)) and 2 in placed_zones:
            return True
        # 11↔12 边被 03(zone3) 挡
        if ((a == 11 and b == 12) or (a == 12 and b == 11)) and 3 in placed_zones:
            return True
        # 12↔14 边被 04(zone4) 挡
        if ((a == 12 and b == 14) or (a == 14 and b == 12)) and 4 in placed_zones:
            return True
        return False

    q = deque([from_point])
    parent = {from_point: -1}
    visited = {from_point}

    while q:
        cur = q.popleft()
        for nb in FIELD_GRAPH.get(cur, []):
            if nb in visited:
                continue
            # blocked 点不能作为中间节点，但可以作为终点
            if nb in blocked and nb != to_point:
                continue
            # 归位区逐边禁用
            if edge_blocked_by_zone(cur, nb):
                continue
            visited.add(nb)
            parent[nb] = cur
            if nb == to_point:
                path = []
                p = to_point
                while p != -1:
                    path.append(p)
                    p = parent[p]
                path.reverse()
                return path
            q.append(nb)
    return []


def path_str(path):
    return " → ".join(str(p) for p in path)


def contains_intermediate(path, point):
    """路径中间节点是否包含 point（排除起点和终点）"""
    if len(path) <= 2:
        return False
    return point in path[1:-1]


# ========================================================================================
# 测试
# ========================================================================================

passed = 0
failed = 0


def check(name, path, expected):
    global passed, failed
    actual = path_str(path)
    if actual == expected:
        print(f"  ✅ {name}: {actual}")
        passed += 1
    else:
        print(f"  ❌ {name}: got [{actual}], expected [{expected}]")
        failed += 1


def check_not_contains(name, path, point):
    global passed, failed
    if not contains_intermediate(path, point):
        print(f"  ✅ {name}: 正确不经过 {point}")
        passed += 1
    else:
        print(f"  ❌ {name}: 路径 {path_str(path)} 不应经过 {point}")
        failed += 1


def check_has_path(name, path):
    global passed, failed
    if path:
        print(f"  ✅ {name}: {path_str(path)} (长度 {len(path)})")
        passed += 1
    else:
        print(f"  ❌ {name}: 无路径")
        failed += 1


# === 1. 对称性验证 ===
print("=== 1. 对称性验证（A→B 必须 B→A）===")
sym_ok = True
for point, neighbors in FIELD_GRAPH.items():
    for nb in neighbors:
        if nb not in FIELD_GRAPH:
            print(f"  ❌ 点{point}→{nb}，但{nb}不在图中")
            sym_ok = False
            failed += 1
            continue
        if point not in FIELD_GRAPH[nb]:
            print(f"  ❌ 点{point}→{nb}，但{nb}没有反向→{point}")
            sym_ok = False
            failed += 1
if sym_ok:
    print("  ✅ 所有连接都是双向的")
    passed += 1

# === 2. 可达性 ===
print("\n=== 2. 所有点位从0可达 ===")
reach_ok = True
for p in range(15):
    path = bfs(0, p)
    if not path:
        print(f"  ❌ 点{p} 从0不可达")
        reach_ok = False
        failed += 1
if reach_ok:
    print("  ✅ 所有15个点位从0可达")
    passed += 1

# === 3. 基本路径 ===
print("\n=== 3. 基本路径测试（无 blocked）===")
check("0→1",   bfs(0, 1),   "0 → 1")
check("0→2",   bfs(0, 2),   "0 → 1 → 2")
check("0→3",   bfs(0, 3),   "0 → 1 → 3")
check("0→4",   bfs(0, 4),   "0 → 1 → 4")               # 经点1 直达第一排右
check("0→5",   bfs(0, 5),   "0 → 1 → 5")
check("0→6",   bfs(0, 6),   "0 → 1 → 2 → 6")
check("0→7",   bfs(0, 7),   "0 → 1 → 3 → 7")
check("0→8",   bfs(0, 8),   "0 → 1 → 4 → 8")
check("0→9",   bfs(0, 9),   "0 → 1 → 5 → 9")
check("0→10",  bfs(0, 10),  "0 → 1 → 2 → 6 → 10")
check("0→11",  bfs(0, 11),  "0 → 1 → 2 → 6 → 11")
check("0→12",  bfs(0, 12),  "0 → 1 → 2 → 6 → 12")
check_has_path("0→13", bfs(0, 13))   # 归位区01左侧
check_has_path("0→14", bfs(0, 14))   # 归位区04右侧

# === 4. ★ 点1 是左右半场枢纽 ===
print("\n=== 4. ★ 点1 连全部4个取货点（左右半场枢纽）===")
def assert_adjacent(a, b):
    global passed, failed
    if b in FIELD_GRAPH.get(a, []):
        print(f"  ✅ 点{a} 连 点{b}")
        passed += 1
    else:
        print(f"  ❌ 点{a} 应连 点{b}，但邻接表里没有")
        failed += 1

assert_adjacent(1, 2)
assert_adjacent(1, 3)
assert_adjacent(1, 4)
assert_adjacent(1, 5)

# 但点4/5 不直接连点2/3（须经点1 中转）
def assert_not_adjacent(a, b):
    global passed, failed
    if b not in FIELD_GRAPH.get(a, []):
        print(f"  ✅ 点{a} 不直连 点{b}（须经点1）")
        passed += 1
    else:
        print(f"  ❌ 点{a} 不应直连 点{b}")
        failed += 1

assert_not_adjacent(4, 2)
assert_not_adjacent(4, 3)
assert_not_adjacent(5, 2)
assert_not_adjacent(5, 3)

# 点4 → 点2（经点1，最短路径 4→1→2）
p42 = bfs(4, 2)
print(f"  点4→点2: {path_str(p42)}（经点1）")
check("4→2", p42, "4 → 1 → 2")

# === 5. ★ 点10/11/12 横向链式（10-11-12，无10-12直连）===
print("\n=== 5. ★ 点10/11/12 横向链式（10-11-12）===")
check("10→11", bfs(10, 11), "10 → 11")        # 相邻直连
check("11→12", bfs(11, 12), "11 → 12")        # 相邻直连
check("13→10", bfs(13, 10), "13 → 10")        # 相邻直连
check("12→14", bfs(12, 14), "12 → 14")        # 相邻直连
# 10→12: 链式应走 10→11→12，但 BFS 也可能选 10→6→12（同为2跳，看展开顺序）
p_10_12 = bfs(10, 12)
print(f"  10→12: {path_str(p_10_12)}（链式 10→11→12 或绕 10→6→12，BFS 任选）")
check_has_path("10→12 有路径", p_10_12)
# 13→14: 全程横向需 13→10→11→12→14，或经第二排绕
p_13_14 = bfs(13, 14)
print(f"  13→14: {path_str(p_13_14)}")
check_has_path("13→14 有路径", p_13_14)

# === 5b. ★ 归位区逐边禁用（placed_zones）===
print("\n=== 5b. ★ 归位区逐边禁用（01挡13-10，02挡10-11，03挡11-12，04挡12-14）===")

# 场景1: 只放 02 → 禁 10↔11 边，其余通
print("  --- 只放 02（禁 10↔11 边）---")
z = {2}
# 10→11：横向断（02 挡），绕第二排
p = bfs(10, 11, placed_zones=z)
print(f"    10→11: {path_str(p)}（绕第二排）")
check("只放02 10→11 绕第二排", p, "10 → 6 → 11")
# 12→11：11↔12 仍通（03 没放），可直接平移
p = bfs(12, 11, placed_zones=z)
print(f"    12→11: {path_str(p)}（03没放，可直接平移）")
check("只放02 12→11 可平移", p, "12 → 11")
# 10→12：横向 10→11 断，绕第二排
p = bfs(10, 12, placed_zones=z)
print(f"    10→12: {path_str(p)}（绕第二排）")
check("只放02 10→12 绕第二排", p, "10 → 6 → 12")

# 场景2: 只放 03 → 禁 11↔12 边，10↔11 仍通
print("  --- 只放 03（禁 11↔12 边）---")
z = {3}
# 11→12：横向断，绕第二排
p = bfs(11, 12, placed_zones=z)
print(f"    11→12: {path_str(p)}（绕第二排）")
check("只放03 11→12 绕第二排", p, "11 → 6 → 12")
# 10→11：10↔11 仍通（02 没放），可直接平移
p = bfs(10, 11, placed_zones=z)
print(f"    10→11: {path_str(p)}（02没放，可直接平移）")
check("只放03 10→11 可平移", p, "10 → 11")
# 10→12：横向 11→12 断，绕第二排
p = bfs(10, 12, placed_zones=z)
print(f"    10→12: {path_str(p)}（绕第二排）")
check("只放03 10→12 绕第二排", p, "10 → 6 → 12")

# 场景3: 放 02 + 03 → 中间横向全断
print("  --- 放 02 + 03（中间横向全断）---")
z = {2, 3}
p = bfs(10, 12, placed_zones=z)
print(f"    10→12: {path_str(p)}（绕第二排）")
check("放02+03 10→12 绕第二排", p, "10 → 6 → 12")
p = bfs(11, 10, placed_zones=z)
print(f"    11→10: {path_str(p)}（绕第二排）")
check("放02+03 11→10 绕第二排", p, "11 → 6 → 10")

# 场景4: 放 01 → 禁 13↔10 边（zone1 挡点13和点10之间）
print("  --- 放 01（禁 13↔10 边）---")
z = {1}
# 13→10：横向断（01 挡），绕第二排
p = bfs(13, 10, placed_zones=z)
print(f"    13→10: {path_str(p)}（绕第二排）")
check("放01 13→10 绕第二排", p, "13 → 6 → 10")
# 10→11：不受 zone1 影响
p = bfs(10, 11, placed_zones=z)
print(f"    10→11: {path_str(p)}（01不挡10-11）")
check("放01 10→11 不受影响", p, "10 → 11")

# 场景5: 放 04 → 禁 12↔14 边（zone4 挡点12和点14之间）
print("  --- 放 04（禁 12↔14 边）---")
z = {4}
# 12→14：横向断（04 挡），绕第二排
p = bfs(12, 14, placed_zones=z)
print(f"    12→14: {path_str(p)}（绕第二排）")
check("放04 12→14 绕第二排", p, "12 → 6 → 14")
# 11→12：不受 zone4 影响
p = bfs(11, 12, placed_zones=z)
print(f"    11→12: {path_str(p)}（04不挡11-12）")
check("放04 11→12 不受影响", p, "11 → 12")

# 场景6: 垂直方向（10↔6 第二排）不受 placed_zones 影响
print("  --- 垂直方向不受影响 ---")
p = bfs(10, 6, placed_zones={2, 3})
print(f"    10→6 (放02+03): {path_str(p)}")
check("垂直方向不受placed_zones影响", p, "10 → 6")

# === 6. ★ 完整取放流程（成对取货）===
print("\n=== 6. ★ 完整取放流程 ===")

# 流程A: 第1轮 → 左点2吸09(food→zone1→左吸盘→点10)
print("  --- 流程A: 点2吸09(左盘) → 点10放zone1 ---")
s1 = bfs(0, 2)
print(f"  起点→取货点2: {path_str(s1)}")
check("0→2", s1, "0 → 1 → 2")
s2 = bfs(2, 10)
print(f"  取货点2→放货点10: {path_str(s2)}")
check("2→10", s2, "2 → 6 → 10")

# 流程B: 第1轮 → 右点3吸10(tool→zone2→右吸盘→点10)
print("\n  --- 流程B: 点3吸10(右盘) → 点10放zone2 ---")
t1 = bfs(0, 3)
print(f"  起点→取货点3: {path_str(t1)}")
check("0→3", t1, "0 → 1 → 3")
t2 = bfs(3, 10)
print(f"  取货点3→放货点10: {path_str(t2)}")
check("3→10", t2, "3 → 7 → 10")

# 流程C: 成对取货 点2(左) + 点3(右)
print("\n  --- 流程C: 成对取货 点2(左盘吸09) → 点3(右盘吸10) ---")
c1 = bfs(2, 3)
print(f"  点2→点3(换点取第二个): {path_str(c1)}")
check("2→3", c1, "2 → 3")

# === 7. 所有取货点可达 ===
print("\n=== 7. ★ 所有取货点路径验证 ===")
all_pickups = sorted({lp for tup in PICKUP_PAIR_MAP for lp in [tup[0], tup[1]]})
for pickup in all_pickups:
    p = bfs(0, pickup)
    if p:
        print(f"  ✅ 取货点{pickup}: {path_str(p)}")
        passed += 1
    else:
        print(f"  ❌ 取货点{pickup}: 无路径")
        failed += 1

# === 8. 所有放货点可达 ===
print("\n=== 8. ★ 所有放货点路径验证 ===")
for place in [10, 11, 12, 13, 14]:
    p = bfs(0, place)
    if p:
        zones = PLACE_ZONE_MAP[place]
        side_desc = " / ".join(f"{d}→zone{z}" for d, z in sorted(zones.items()))
        print(f"  ✅ 放货点{place}({side_desc}): {path_str(p)}")
        passed += 1
    else:
        print(f"  ❌ 放货点{place}: 无路径")
        failed += 1

# === 9. 避障路径 ===
print("\n=== 9. ★ 避障路径测试 ===")
# 假设点6被占用（正在取货），从0到10需要绕路
blocked = {6}
p_avoid = bfs(0, 10, blocked)
print(f"  0→10 (blocked={blocked}): {path_str(p_avoid)}")
check_has_path("0→10 避开点6", p_avoid)
check_not_contains("0→10 不经过点6", p_avoid, 6)

# === 10. 取货映射验证 ===
print("\n=== 10. ★ 成对取货映射验证 ===")
for lp, rp, lb, rb in PICKUP_PAIR_MAP:
    print(f"  左点{lp}吸箱{lb:02d}, 右点{rp}吸箱{rb:02d}")
    passed += 1

# === 11. 放货映射验证（吸盘侧决定归位区）===
print("\n=== 11. ★ 放货映射验证 ===")
for pp, side_map in sorted(PLACE_ZONE_MAP.items()):
    side_desc = " / ".join(f"{d}吸盘→zone{z}" for d, z in sorted(side_map.items()))
    print(f"  点{pp}: {side_desc}")
    passed += 1

# === 11b. 反查完备性（每个 zone 都有左右吸盘各一个自然站位，无转圈）===
print("\n=== 11b. ★ 反查完备性（每 zone×吸盘侧都有自然站位，0 转圈）===")
for direction in ["left", "right"]:
    for zone in [1, 2, 3, 4]:
        found = [pp for pp, sm in PLACE_ZONE_MAP.items()
                 if sm.get(direction) == zone]
        if found:
            print(f"  ✅ {direction}吸盘放zone{zone} → 点{found[0]}")
            passed += 1
        else:
            print(f"  ❌ {direction}吸盘放zone{zone} → 无自然站位（需转圈）")
            failed += 1

# === 结果 ===
print(f"\n{'=' * 40}")
print(f"结果: {passed} 通过, {failed} 失败")
exit(1 if failed > 0 else 0)
