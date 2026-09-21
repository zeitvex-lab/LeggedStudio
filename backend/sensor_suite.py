"""External sensor suite catalog, derived from the MATRiX v1.0.13 declarations.

MATRiX v1.0.13 describes its hardware suite as data: the active sensors live in
``UeSim/Content/model/config/config.json`` and per-purpose presets live in
``UeSim/Content/model/config/sensors/*.json``. Every entry carries a type, a
mount body, an extrinsic (position/rotation), a publication frequency, a topic
name and — for cameras — intrinsics.

That declaration is exactly the vocabulary the advanced simulation surface was
missing: ``web/advanced_sim.html`` talks about "外部传感器（深度相机 / 雷达 /
点云）" in prose, while the only machine-readable sensor vocabulary in the
control plane was the four-item ``sensor`` field of
:mod:`backend.perception_observations` (``proprio`` / ``foot_contact`` /
``heightfield`` / ``depth_camera``). This module ports the *declarative* part of
the MATRiX suite so a policy contract, the browser panel and a headless
acceptance run can all point at the same sensor ids.

What is deliberately **not** ported: the MATRiX runtime (UE5 + its packages) and
the recorded point-cloud payloads, whose encoding is not part of the release.
See ``tools/matrix_sensor_corpus.py`` for the container-level facts that *are*
verified.

MATRiX 的 4 个相机变体预设（``fisheye`` / ``infrared`` / ``panorama`` /
``ptzrgb``）**不收录**：它们属平台成像设备（鱼眼 210°/ 红外 / 全景 / 云台），
不是 RL 观测口径，当前也没有任何策略消费；平台侧需要投影或可视化时，直接读
MATRiX 原始 ``UeSim/Content/model/config/sensors/*.json`` 即可。

``gps`` 同样**不收录**（因此 ``default`` 预设是「上游 default 去掉 GPS」）：
它只服务室外全局定位，本项目的任务族（室内步态 / 粗糙地形 / 跑酷 / 操纵 /
特技）不消费它，全仓也没有任何策略或验收判据用到；若将来做室外或园区巡检，
按上游 ``config_default.json`` 的字段补一条 3 维声明即可（恢复成本约 1 行）。

Provenance: MATRiX v1.0.13, ``UeSim/Content/model/config/`` (BSD-3-Clause,
ZsiBot). Values below are copied verbatim from those files; nothing is bundled
or executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

from contracts import sensor_plugin_contract as plugin_contract

router = APIRouter(prefix="/api/sensors", tags=["sensors"])

SOURCE = "MATRiX v1.0.13 UeSim/Content/model/config/{config.json,sensors/*.json}"

# Sensor family -> whether the reading comes from the hardware itself
# (proprioceptive: base motion and global position) or from the environment
# (exteroceptive: cameras and lidar). The advanced simulation surface is the
# exteroceptive half, matching its "外部传感器" description.
SENSOR_KIND_CLASSES: dict[str, str] = {
    "imu": "proprioceptive",
    "odom": "proprioceptive",
    "rgb": "exteroceptive",
    "depth": "exteroceptive",
    "lidar": "exteroceptive",
}


@dataclass(frozen=True)
class SensorSpec:
    """One sensor declaration: identity, mounting, rate and payload shape."""

    id: str
    kind: str
    sensor_type: str
    topic: str
    frequency_hz: float
    mount: str = "base_link"
    position: dict[str, float] = field(default_factory=dict)
    rotation: dict[str, float] = field(default_factory=dict)
    intrinsics: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def sensor_class(self) -> str:
        return SENSOR_KIND_CLASSES.get(self.kind, "exteroceptive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "class": self.sensor_class,
            "sensor_type": self.sensor_type,
            "topic": self.topic,
            "frequency_hz": self.frequency_hz,
            "mount": self.mount,
            "position": dict(self.position),
            "rotation": dict(self.rotation),
            "intrinsics": dict(self.intrinsics) if self.intrinsics else None,
            "meta": dict(self.meta),
        }


def _camera_intrinsics(**kwargs: Any) -> dict[str, Any]:
    return dict(kwargs)


# --------------------------------------------------------------------------
# Presets. Each name maps to the MATRiX file it was copied from.
# --------------------------------------------------------------------------
_PRESETS: dict[str, tuple[str, list[SensorSpec]]] = {
    "default": (
        "UeSim/Content/model/config/config.json",
        [
            SensorSpec("IMU", "imu", "imu", "/imu", 500.0, position={"x": 0.0, "y": 0.0, "z": 0.0}),
            SensorSpec("Odom", "odom", "odom", "/odom", 100.0, position={"x": 0.0, "y": 0.0, "z": 0.0}),
            SensorSpec(
                "camera",
                "rgb",
                "rgb",
                "/front_camera/image/compressed",
                10.0,
                position={"x": 0.0, "y": 0.0, "z": 0.1},
                intrinsics=_camera_intrinsics(width=1920, height=1080, fov_deg=90.0),
                meta={"fx": 0.0, "fy": 0.0, "cx": -1.0, "cy": -1.0, "distortion": [0.0, 0.0, 0.0, 0.0, 0.0]},
            ),
            SensorSpec(
                "depth_sensor",
                "depth",
                "depth",
                "/front_depth/image/compressed",
                10.0,
                position={"x": 0.0, "y": 0.0, "z": 0.1},
                intrinsics=_camera_intrinsics(width=640, height=480, fov_deg=120.0),
                meta={"cloudmode": False, "cx": -1.0, "cy": -1.0},
            ),
            SensorSpec(
                "lidar",
                "lidar",
                "airy",
                "/front_lidar",
                10.0,
                position={"x": 0.0, "y": 0.0, "z": 0.1},
                meta={"draw_points": False, "random_scan": False, "simulate_motion_distortion": False},
            ),
        ],
    ),
    "lidar_dual": (
        "sensors/config_lidar.json",
        [
            SensorSpec(
                "lidar",
                "lidar",
                "mid360",
                "/front_lidar",
                10.0,
                position={"x": 0.2, "y": 0.0, "z": 0.1},
                meta={"draw_points": False, "random_scan": False, "simulate_motion_distortion": False},
            ),
            SensorSpec(
                "lidar2",
                "lidar",
                "airy",
                "/front_lidar2",
                10.0,
                position={"x": -0.2, "y": 0.0, "z": 0.1},
                rotation={"roll": 0.0, "pitch": 0.0, "yaw": 180.0},
                meta={"draw_points": False, "random_scan": False, "simulate_motion_distortion": False},
            ),
        ],
    ),
    "mid360_slam": (
        "sensors/mid360_slam.json",
        [
            SensorSpec(
                "lidar",
                "lidar",
                "mid360",
                "/front_lidar",
                10.0,
                position={"x": 0.0, "y": 0.0, "z": 0.1},
                meta={"draw_points": False, "random_scan": False, "simulate_motion_distortion": False},
            ),
            SensorSpec("Odom", "odom", "odom", "/odom", 100.0),
            SensorSpec(
                "IMU",
                "imu",
                "imu",
                "/front_lidar/imu",
                500.0,
                position={"x": 0.0, "y": 0.0, "z": 0.1},
            ),
        ],
    ),
    "zg": (
        "sensors/config_zg.json",
        [
            SensorSpec(
                "camera",
                "rgb",
                "rgb",
                "/front_camera/compressed",
                10.0,
                position={"x": 0.42613260886557602, "y": -0.010512812182730358, "z": 0.08585034844521558},
                intrinsics=_camera_intrinsics(width=1920, height=1080, fov_deg=100.74704085978787),
            ),
            SensorSpec(
                "lidar",
                "lidar",
                "airy",
                "/front_lidar",
                10.0,
                position={"x": 0.36614999999999998, "y": 0.0, "z": 0.2},
                rotation={"roll": 0.0, "pitch": -90.0, "yaw": 0.0},
            ),
        ],
    ),
}


def preset_names() -> list[str]:
    return sorted(_PRESETS)


def preset_sensors(name: str) -> list[SensorSpec]:
    entry = _PRESETS.get(name)
    if entry is None:
        raise KeyError(name)
    return list(entry[1])


def preset_source(name: str) -> str:
    entry = _PRESETS.get(name)
    return entry[0] if entry else ""


def list_presets() -> list[dict[str, Any]]:
    presets = []
    for name in preset_names():
        sensors = preset_sensors(name)
        presets.append(
            {
                "name": name,
                "source": preset_source(name),
                "sensor_count": len(sensors),
                "kinds": sorted({sensor.kind for sensor in sensors}),
                "exteroceptive_count": sum(1 for sensor in sensors if sensor.sensor_class == "exteroceptive"),
            }
        )
    return presets


def sensor_kind_catalog() -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    for _, sensors in _PRESETS.values():
        for sensor in sensors:
            seen.setdefault(sensor.kind, sensor.sensor_type)
    return [
        {"kind": kind, "class": SENSOR_KIND_CLASSES.get(kind, "exteroceptive"), "sensor_type_default": sensor_type}
        for kind, sensor_type in sorted(seen.items())
    ]


def default_sensor_suite() -> list[dict[str, Any]]:
    """The MATRiX release default suite, as plain dicts."""
    return [sensor.to_dict() for sensor in preset_sensors("default")]


# --------------------------------------------------------------------------------------
# v2 高级仿真：共享插件声明的**导出口**（不是第二份定义）
# --------------------------------------------------------------------------------------
#
# 本模块上面的预设携的是 **MATRiX v1.0.13 硬件套件**（"这台机器人出厂装了什么"，
# 出处是外部发行包，逐字复制）；v2 高级仿真需要的是"**原生运行时可实例化的插件契约**"
# （输出形状、参数默认值与出处、能力等级）。两者的字段语义不同，**不能互相翻译**：
# 把 ``SensorSpec.rate_hz`` 映射成 ``sample_period_ticks`` 会造出第二个采样率真值
# （前者是硬件申报率，后者必须是 contract 时间基下的整数 tick）。
#
# 所以这里只做**委托**：一个字节都不解释，全部交给 contracts 里的那一份声明。
# 这样"UI 上写着 240 线、worker 实际打 128 线"这类漂移在结构上就不可能出现。


def plugin_catalog_v2() -> dict[str, Any]:
    """v2 插件 catalog（委托 :func:`contracts.sensor_plugin_contract.plugin_catalog_payload`）。"""

    return plugin_contract.plugin_catalog_payload()


def plugin_default_config_v2(plugin_id: str) -> dict[str, Any]:
    """某插件的默认参数（**唯一**来源仍是 contracts；未知插件抛 ``KeyError`` 而非返回空）。"""

    definition = plugin_contract.plugin_definition(plugin_id)
    if definition is None:
        raise KeyError(f"Unknown v2 sensor plugin: {plugin_id}")
    return definition.default_config()


@router.get("/v2/plugins")
async def sensor_plugins_v2():
    """v2 可实例化插件与命令提供器声明（默认值与出处只在 contracts 一处）。"""

    catalog = plugin_catalog_v2()
    return {
        "success": True,
        "source": SOURCE,
        "schema_version": catalog["schema_version"],
        "count": len(catalog["sensors"]),
        **catalog,
    }


@router.get("/kinds")
async def sensor_kinds():
    """Return every declared sensor kind and its proprioceptive/exteroceptive class."""
    kinds = sensor_kind_catalog()
    return {"success": True, "source": SOURCE, "count": len(kinds), "kinds": kinds}


@router.get("/presets")
async def sensor_presets():
    """Return the MATRiX-derived sensor suite presets (summaries)."""
    presets = list_presets()
    return {"success": True, "source": SOURCE, "count": len(presets), "presets": presets}


@router.get("/presets/{name}")
async def sensor_preset(name: str):
    """Return every sensor declaration of one preset."""
    try:
        sensors = preset_sensors(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown sensor preset: {name}") from None
    return {
        "success": True,
        "source": SOURCE,
        "preset": name,
        "preset_source": preset_source(name),
        "count": len(sensors),
        "sensors": [sensor.to_dict() for sensor in sensors],
    }
