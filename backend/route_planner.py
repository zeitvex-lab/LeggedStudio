"""航点路线规划器（T4.4，批次 4 / M5）：网格 A* + Dijkstra。

输入：占据网格（0=可通行，1=障碍）与起终点；输出：折线路径 + 长度。
供导航仿真在画障碍/设航点后自动求路，路径写回场景与遥测评估。
A* 用对角距离启发（可允许 4/8 邻域）；Dijkstra 用于对比验证与无启发回退。
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable

Coord = tuple[int, int]

_NEIGHBORS_4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_NEIGHBORS_8 = _NEIGHBORS_4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


@dataclass
class PlanResult:
    path: list[Coord]
    cost: float
    algorithm: str
    expanded: int

    def as_dict(self) -> dict:
        return {
            "path": [list(coord) for coord in self.path],
            "cost_m": round(self.cost, 3),
            "algorithm": self.algorithm,
            "expanded_nodes": self.expanded,
        }


def _heuristic(a: Coord, b: Coord, diagonal: bool) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    if diagonal:
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)
    return float(dx + dy)


def _step_cost(a: Coord, b: Coord, diagonal: bool) -> float:
    if diagonal and a[0] != b[0] and a[1] != b[1]:
        return math.sqrt(2)
    return 1.0


def plan_route(
    grid: list[list[int]],
    start: Coord,
    goal: Coord,
    *,
    algorithm: str = "astar",
    diagonal: bool = True,
) -> PlanResult:
    """A*（默认）或 Dijkstra 路径规划。

    grid[y][x]：0=可通行 1=障碍。起终点落在障碍或越界时抛 ValueError。
    """

    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    for name, coord in (("start", start), ("goal", goal)):
        if not (0 <= coord[0] < rows and 0 <= coord[1] < cols):
            raise ValueError(f"{name} {coord} 越界（网格 {rows}x{cols}）")
        if grid[coord[0]][coord[1]]:
            raise ValueError(f"{name} {coord} 落在障碍上")

    neighbors = _NEIGHBORS_8 if diagonal else _NEIGHBORS_4
    use_heuristic = algorithm.lower() == "astar"
    counter = 0
    open_heap: list[tuple[float, float, Coord]] = [(0.0, 0, start)]
    best_cost: dict[Coord, float] = {start: 0.0}
    came_from: dict[Coord, Coord] = {}
    closed: set[Coord] = set()

    while open_heap:
        priority, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return PlanResult(path=list(reversed(path)), cost=best_cost[goal],
                              algorithm="astar" if use_heuristic else "dijkstra",
                              expanded=len(closed))
        for dy, dx in neighbors:
            ny, nx = current[0] + dy, current[1] + dx
            if not (0 <= ny < rows and 0 <= nx < cols) or grid[ny][nx]:
                continue
            nxt = (ny, nx)
            new_cost = best_cost[current] + _step_cost(current, nxt, diagonal)
            if new_cost < best_cost.get(nxt, float("inf")):
                best_cost[nxt] = new_cost
                came_from[nxt] = current
                counter += 1
                priority = new_cost + (_heuristic(nxt, goal, diagonal) if use_heuristic else 0.0)
                heapq.heappush(open_heap, (priority, counter, nxt))
    raise ValueError("无可达路径——目标被障碍完全遮挡")
