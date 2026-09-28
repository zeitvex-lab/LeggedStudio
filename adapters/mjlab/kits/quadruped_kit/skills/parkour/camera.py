"""深度相机：从 `registry/cameras.json` 的**声明**装配越障技能的相机与深度观测项。

## 为什么相机要"声明驱动"

PIE 的相机位姿 / 分辨率 / 视场此前是 go2 `env_cfg` 里的字面量 —— 同族第二台机型想复用
就得**抄一遍数值**，而相机外参与内参是"机器事实"：抄的后果是两处真值、且无人对账。
本模块把这块交给 `registry/cameras.json`（相机档位单一真值）：技能层只按 **档位 id** 取声明，
`CameraSensorCfg` 的 `name` / `parent_body` / `pos` / `quat` / `fovy` / `width` / `height`
与深度观测项的全部参数**都从声明取**；取不到档位、或声明缺字段，一律**报错退出**
（fail-closed），不静默用默认值 —— 悄悄少一个位姿等于悄悄换一台相机。

## 两个换算口径（同样从声明取，不写死分辨率/视场）

* **垂直 FOV**：档位声明的是**水平**视场（与 `backend/camera_projection.resolve_intrinsics`
  同一"fov 即水平视场"的口径），而 MuJoCo 取垂直 FOV，故按声明分辨率的**连续像平面
  纵横比** H/W 换算：``fovy = 2·atan(tan(hfov/2)·H/W)``。这与源实现（PIE 106×60）逐位一致；
  `backend` 投影侧用的 (H−1)/(W−1) 像素质心口径会差约 0.4°，那是**成像**口径，不是训练域口径。
* **FOV 域随机化**：档位声明的 hfov 分别 ±扫幅、各自换算成垂直 FOV 后取差，
  得到 fovy 的抖动区间（区间同样只依赖声明与配方扫幅）。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from ..family import repo_root
from .profile import PIE_CAMERA_FOV_SWEEP_DEG, ParkourProfile

#: 相机档位声明文件（相对仓库根）。
CAMERA_REGISTRY = ("registry", "cameras.json")

#: 本技能要求的相机类型：深度。
REQUIRED_KIND = "depth"


@dataclass(frozen=True)
class DepthCameraDeclaration:
    """一个深度相机档位在本技能里被消费掉的全部字段（无默认值 = 声明缺项即报错）。"""

    profile_id: str
    scope: str
    sensor_name: str
    parent_body: str
    pos: tuple[float, float, float]
    quat: tuple[float, float, float, float]
    width: int
    height: int
    horizontal_fov_deg: float
    cutoff_distance: float
    crop_left: int
    crop_right: int
    gaussian_blur: tuple[int, float]
    frame_history_length: int
    update_period_steps: int

    # --- 派生视图（只做换算，不引入第二个真值） -----------------------------

    @property
    def vertical_fov_deg(self) -> float:
        """垂直 FOV（MuJoCo 口径）：按声明分辨率的连续像平面纵横比换算。"""
        return self.vertical_fov_deg_at(self.horizontal_fov_deg)

    def vertical_fov_deg_at(self, horizontal_fov_deg: float) -> float:
        return 2.0 * math.degrees(
            math.atan(
                math.tan(math.radians(horizontal_fov_deg) * 0.5)
                * self.height
                / self.width
            )
        )

    def fovy_sweep(self, sweep_deg: float = PIE_CAMERA_FOV_SWEEP_DEG) -> tuple[float, float]:
        """FOV 域随机化区间：`(vfov(hfov−扫幅) − vfov, vfov(hfov+扫幅) − vfov)`。"""
        base = self.vertical_fov_deg
        return (
            self.vertical_fov_deg_at(self.horizontal_fov_deg - sweep_deg) - base,
            self.vertical_fov_deg_at(self.horizontal_fov_deg + sweep_deg) - base,
        )

    def observation_params(self) -> dict[str, object]:
        """深度观测项（`mdp.DepthHistory`）的参数表 —— 逐项来自声明。"""
        return {
            "sensor_name": self.sensor_name,
            "cutoff_distance": self.cutoff_distance,
            "crop_left": self.crop_left,
            "crop_right": self.crop_right,
            "gaussian_blur": self.gaussian_blur,
            "frame_history_length": self.frame_history_length,
            "update_period_steps": self.update_period_steps,
        }


def _require(mapping: dict, key: str, *, where: str):
    if not isinstance(mapping, dict) or key not in mapping or mapping[key] is None:
        raise ValueError(f"{where} 缺字段 {key!r} —— 技能层不从默认值兜底（fail-closed）")
    return mapping[key]


def _numbers(value, count: int, *, where: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError(f"{where} 应为 {count} 个数，收到 {value!r}")
    return tuple(float(item) for item in value)


def camera_profiles(*, root=None) -> list[dict]:
    """全部相机档位（`registry/cameras.json`，单一真值）。"""
    base = repo_root() if root is None else root
    path = base.joinpath(*CAMERA_REGISTRY)
    if not path.is_file():
        raise FileNotFoundError(f"相机声明不存在：{path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    profiles = payload.get("profiles") or []
    if not profiles:
        raise ValueError(f"{path} 未声明任何档位")
    return [dict(item) for item in profiles]


def resolve_depth_declaration(
    profile: ParkourProfile, *, robot_id: str, root=None
) -> DepthCameraDeclaration:
    """按 profile 的档位 id 取声明并逐字段解析；缺项 / 类型不符 / 作用域不符即报错。

    **机型作用域回退**（2026-09-28 盲狗补全轮）：装配表给的是族默认档位 id（如 go2 的
    `pie-front-depth-106x60`）；本机专属档位按命名约定 ``<档位id>-<机型id>`` 登记在
    注册表（如 ``pie-front-depth-106x60-go1``），存在即自动切换 —— 机型事实（位姿/内参）
    住注册表，装配表不需要逐机型改数据；两个 id 都没有 / 都不匹配作用域 ⇒ 维持报错。
    """
    candidates = {str(item.get("id")): item for item in camera_profiles(root=root)}
    if profile.camera_profile not in candidates:
        raise KeyError(
            f"相机档位 {profile.camera_profile!r} 不在声明里（可选：{', '.join(sorted(candidates))}）"
        )
    item = candidates[profile.camera_profile]
    if str(item.get("scope") or "") != robot_id:
        machine_scoped_id = f"{profile.camera_profile}-{robot_id}"
        if machine_scoped_id in candidates:
            item = candidates[machine_scoped_id]
    where = f"registry/cameras.json#{item.get('id')}"
    kind = str(item.get("kind") or "")
    if kind != REQUIRED_KIND:
        raise ValueError(f"{where}: 本技能要 {REQUIRED_KIND!r} 相机，声明是 {kind!r}")
    scope = str(item.get("scope") or "")
    if scope != robot_id:
        raise ValueError(
            f"{where}: 档位作用域 {scope!r} ≠ 本机型 {robot_id!r}"
            "（别的机型的位姿/内参不能拿来当本机型的事实）"
        )
    resolution = _require(item, "resolution", where=where)
    width = int(_require(resolution, "width", where=f"{where}.resolution"))
    height = int(_require(resolution, "height", where=f"{where}.resolution"))
    fov_deg = float(_require(item, "fov_deg", where=where))
    pose = _require(item, "pose", where=where)
    observation = _require(item, "training_observation", where=where)
    blur = _require(observation, "gaussian_blur", where=f"{where}.training_observation")
    if not isinstance(blur, (list, tuple)) or len(blur) != 2:
        raise ValueError(f"{where}.training_observation.gaussian_blur 应为 [核宽, sigma]")
    return DepthCameraDeclaration(
        profile_id=str(item.get("id")),
        scope=scope,
        sensor_name=str(_require(observation, "sensor_name", where=f"{where}.training_observation")),
        parent_body=str(_require(pose, "parent_body", where=f"{where}.pose")),
        pos=_numbers(_require(pose, "pos", where=f"{where}.pose"), 3, where=f"{where}.pose.pos"),
        quat=_numbers(_require(pose, "quat", where=f"{where}.pose"), 4, where=f"{where}.pose.quat"),
        width=width,
        height=height,
        horizontal_fov_deg=fov_deg,
        cutoff_distance=float(
            _require(observation, "cutoff_distance", where=f"{where}.training_observation")
        ),
        crop_left=int(_require(observation, "crop_left", where=f"{where}.training_observation")),
        crop_right=int(_require(observation, "crop_right", where=f"{where}.training_observation")),
        gaussian_blur=(int(blur[0]), float(blur[1])),
        frame_history_length=int(
            _require(observation, "frame_history_length", where=f"{where}.training_observation")
        ),
        update_period_steps=int(
            _require(observation, "update_period_steps", where=f"{where}.training_observation")
        ),
    )
