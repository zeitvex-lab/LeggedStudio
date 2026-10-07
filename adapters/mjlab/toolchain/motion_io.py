"""动作数据导入 + **关节列校验**（N1 数据层；只依赖 numpy + stdlib）。

## 支持的两种输入（对齐上游做法）

* ``.csv``：首行是表头。若表头**像关节名**（首格不是数字）就当成列名，否则视为纯数值表；
  首格为 ``time`` / ``t`` / ``timestamp`` 时该列是时间轴，导入时丢掉（fps 由 ``fps=`` 参数或
  默认值给）。
* ``.npz``：按 ``frames`` → ``joint_pos`` → ``dof_pos`` 顺序取第一个存在的二维数组；
  ``joint_names``（字符串数组）与 ``fps``（标量）可选。

## 关节列校验的口径（对标 LainLab ``calibrate.py``）

文件里的关节列名必须与契约 ``action.joint_order`` **同名同序**：

* 缺列 / 多列 ⇒ 报（名字对不上就是数据不对）；
* **顺序不同 ⇒ 单独报**（集合相同、序列不同）—— 这是最阴的一类：能跑、不报错，训出来是错位的；
* 文件没有列名 ⇒ 报"无法校验"，**不按宽度猜**（宽度口径是 `registry/motions` 的注册口径，
  不是训练口径；两件事不许混）。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

#: CSV 里这些表头名表示时间轴（导入时丢掉该列）。
TIME_HEADERS = ("time", "t", "timestamp", "time_s")
#: NPZ 里动作帧数组的候选键（按此顺序取第一个存在的）。
NPZ_FRAME_KEYS = ("frames", "joint_pos", "dof_pos", "qpos")
DEFAULT_FPS = 50.0


class MotionIOError(ValueError):
    """动作文件不可读/形状不对 —— **fail-loud**，不猜。"""


@dataclass(frozen=True)
class MotionFrames:
    """一次导入的结果（帧数组 + 列名 + 帧率 + 出处）。"""

    frames: np.ndarray            # (T, J) float64
    joint_names: list[str] | None  # 列名（None = 文件无表头）
    fps: float
    source: str
    fmt: str                      # "csv" | "npz"

    @property
    def frame_count(self) -> int:
        return int(self.frames.shape[0])

    @property
    def dof_dim(self) -> int:
        return int(self.frames.shape[1])


def _looks_like_names(header: Sequence[str]) -> bool:
    """表头是否像列名（任一格不是数字即认为是）。"""
    for cell in header:
        try:
            float(cell)
        except (TypeError, ValueError):
            return True
    return False


def _import_csv(path: Path, *, fps: float | None) -> MotionFrames:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        raise MotionIOError(f"{path.name}: CSV 是空的")
    header = [cell.strip() for cell in rows[0]]
    names: list[str] | None = None
    body = rows[1:] if _looks_like_names(header) else rows
    drop: list[int] = []
    if names is None and _looks_like_names(header):
        names = list(header)
        drop = [index for index, cell in enumerate(header) if cell.lower() in TIME_HEADERS]
    try:
        matrix = np.array(
            [[float(cell) for index, cell in enumerate(row) if index not in drop] for row in body],
            dtype=np.float64,
        )
    except ValueError as exc:
        raise MotionIOError(f"{path.name}: CSV 有非数值单元（{exc}）") from exc
    if names is not None and drop:
        names = [cell for index, cell in enumerate(names) if index not in drop]
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise MotionIOError(f"{path.name}: CSV 没有数据行")
    return MotionFrames(matrix, names, float(fps if fps is not None else DEFAULT_FPS),
                        path.as_posix(), "csv")


def _import_npz(path: Path, *, fps: float | None) -> MotionFrames:
    with np.load(path, allow_pickle=False) as archive:
        frame_key = next((key for key in NPZ_FRAME_KEYS if key in archive), None)
        if frame_key is None:
            raise MotionIOError(
                f"{path.name}: npz 里找不到动作帧数组（试过 {list(NPZ_FRAME_KEYS)}，"
                f"实际键：{sorted(archive.files)}）"
            )
        matrix = np.asarray(archive[frame_key], dtype=np.float64)
        names = None
        if "joint_names" in archive:
            names = [str(item) for item in np.asarray(archive["joint_names"]).tolist()]
        rate = fps
        if rate is None and "fps" in archive:
            rate = float(np.asarray(archive["fps"]).reshape(-1)[0])
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise MotionIOError(f"{path.name}: 动作帧数组必须是 (T, J) 的非空二维数组，得到 {matrix.shape}")
    if names is not None and len(names) != matrix.shape[1]:
        raise MotionIOError(
            f"{path.name}: joint_names 有 {len(names)} 个，动作列有 {matrix.shape[1]} 列 —— 对不上")
    return MotionFrames(matrix, names, float(rate if rate is not None else DEFAULT_FPS),
                        path.as_posix(), "npz")


def load_motion(path: Path | str, *, fps: float | None = None) -> MotionFrames:
    """导入 ``.csv`` / ``.npz`` 动作文件（形状不对即抛，不猜）。"""
    target = Path(path)
    if not target.is_file():
        raise MotionIOError(f"动作文件不存在：{target}")
    suffix = target.suffix.lower()
    if suffix == ".csv":
        return _import_csv(target, fps=fps)
    if suffix == ".npz":
        return _import_npz(target, fps=fps)
    raise MotionIOError(f"{target.name}: 不支持的格式（支持 .csv / .npz）")


def joint_column_problems(joint_names: Sequence[str] | None,
                          expected_order: Sequence[str]) -> list[str]:
    """列名 vs 契约关节序：返回问题列表（空 = 通过）。"""
    expected = [str(name) for name in expected_order]
    if not expected:
        return ["契约没有声明关节序（expected_order 为空，无法校验）"]
    if joint_names is None:
        return ["文件没有关节列名 —— 无法校验列序（不按宽度猜：宽度是注册口径，不是训练口径）"]
    actual = [str(name) for name in joint_names]
    problems: list[str] = []
    missing = [name for name in expected if name not in actual]
    extra = [name for name in actual if name not in expected]
    if missing:
        problems.append(f"缺关节列：{missing}")
    if extra:
        problems.append(f"多出来路不明的列：{extra}")
    if not missing and not extra and actual != expected:
        first = next(index for index, (a, b) in enumerate(zip(actual, expected)) if a != b)
        problems.append(
            f"列名集合相同但**顺序不同**（第 {first} 列是 {actual[first]!r}，契约要求 {expected[first]!r}）"
            "—— 这类错不会报错，只会训出错位的策略"
        )
    return problems


def calibrate(path: Path | str, *, expected_order: Sequence[str] | None = None,
              fps: float | None = None) -> dict[str, Any]:
    """导入 + 校验一份动作文件，返回可序列化的报告。"""
    motion = load_motion(path, fps=fps)
    problems = (joint_column_problems(motion.joint_names, expected_order)
                if expected_order is not None else [])
    return {
        "source": motion.source,
        "format": motion.fmt,
        "frames": motion.frame_count,
        "dof_dim": motion.dof_dim,
        "fps": motion.fps,
        "has_joint_names": motion.joint_names is not None,
        "checked_against": list(expected_order) if expected_order is not None else None,
        "ok": not problems,
        "problems": problems,
    }
