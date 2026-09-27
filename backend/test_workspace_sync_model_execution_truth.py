"""序 14：**执行真值 `model/`**（MJCF + 网格）的镜像回归锁。

背景（2026-09-20 lite3 实况）：`_sync_shipped_packages_into_workspace` 原先只覆盖
`training/{profiles,source}` + `simulation/` + 契约/manifest 镜像，**`model/` 不在内**。
后果：存量安装的 `model/robot.xml` 可以永远停在旧形态 —— `deeprobotics_lite3` 的副本
仍是旧 `<motor>`(effort)，源树已是 B28/B35 的 `<position kp/kv/forcerange>`，于是训练
**建环境**就报 ``XML actuator ... is type 'effort', but command_field='position' was
requested``；报错点在装配置阶段，极易被误读成"训练随机失败"。

口径依据（不是猜）：`00_know/04_参数真值标准.md` §0.2 把 ``model/robot.xml`` 定为
**执行真值**（"验收 / 训练装配 / 浏览器（编译后）"，由 `tools/bake_mjcf_physics.py` 写入、
`tools/validate_mjcf_contract.py` 守门），与 `contract.json` 同级 ⇒ 照 D7/B36/B13 同一
先例，副本不得独立演化出第二套真值。（同步注释里"模型永不触碰"指的是训练产物/checkpoint。）

锁死语义：
- 副本 MJCF 与源树不同 → 覆盖为源树内容（**核心回归**）；
- 源树新增模型文件 → 副本补齐；
- 副本独有的陈旧模型文件 → 清除（与 `training/` 子树同一"内容集合一致"语义，但
  `__pycache__` 除外）；
- 内容一致 → 不重写（mtime 不变）；
- 签名能感知 MJCF 变化（否则根本不触发重扫，镜像等于没接）。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend import robot_packages

SHIPPED_MJCF = '<mujoco model="acme"><actuator><position name="hip" kp="30" kv="1"/></actuator></mujoco>\n'
STALE_MJCF = '<mujoco model="acme"><actuator><motor name="hip" gear="1"/></actuator></mujoco>\n'
SHIPPED_CONTRACT = {"robot_id": "acme_bot", "family": "Acme", "joints": {"actuated_joints": []}, "urdf": {"path": "model/robot.xml"}}
shipped_MANIFEST = {"schema_version": "robot-package-1.0", "package_id": "acme_bot", "model": {"format": "mjcf", "path": "model/robot.xml"}}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class WorkspaceSyncModelExecutionTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="legged-studio-model-sync-")
        root = Path(self._tmp.name)
        self.assets_root = root / "assets" / "robots"
        self.workspace_root = root / "workspace"
        shipped = self.assets_root / "acme_bot"
        (shipped / "model" / "assets").mkdir(parents=True)
        (shipped / "training" / "profiles").mkdir(parents=True)
        (shipped / "model" / "robot.xml").write_text(SHIPPED_MJCF, encoding="utf-8")
        (shipped / "model" / "assets" / "mesh.stl").write_bytes(b"solid shipped\n")
        (shipped / "training" / "profiles" / "flat.json").write_text("{}", encoding="utf-8")
        _write_json(shipped / "contract_legacy_v2.json", SHIPPED_CONTRACT)
        _write_json(shipped / "robot_package.json", shipped_MANIFEST)

        # workspace 副本：MJCF 是旧形态，另有一个源树没有的陈旧网格
        target = self.workspace_root / "packages" / "acme_bot"
        (target / "model" / "assets").mkdir(parents=True)
        (target / "model" / "robot.xml").write_text(STALE_MJCF, encoding="utf-8")
        (target / "model" / "assets" / "mesh.stl").write_bytes(b"solid shipped\n")
        (target / "model" / "assets" / "old_mesh.stl").write_bytes(b"solid stale\n")
        _write_json(target / "contract_legacy_v2.json", SHIPPED_CONTRACT)
        _write_json(target / "robot_package.json", shipped_MANIFEST)

        self._shipped = shipped
        self._target = target
        self._previous_root = robot_packages.ROOT
        self._previous_env = os.environ.get("LEGGED_STUDIO_WORKSPACE")
        robot_packages.ROOT = root
        os.environ["LEGGED_STUDIO_WORKSPACE"] = str(self.workspace_root)
        robot_packages.invalidate_package_cache()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        robot_packages.ROOT = self._previous_root
        if self._previous_env is None:
            os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
        else:
            os.environ["LEGGED_STUDIO_WORKSPACE"] = self._previous_env
        robot_packages.invalidate_package_cache()
        self._tmp.cleanup()

    def _shipped_mjcf(self) -> Path:
        return self._shipped / "model" / "robot.xml"

    def _copy_mjcf(self) -> Path:
        return self._target / "model" / "robot.xml"

    def test_stale_mjcf_copy_is_mirrored_to_source(self):
        """**核心回归**：副本的旧执行器形态必须被源树覆盖（否则训练装配置就报错）。"""
        robot_packages.rebuild_package_index()
        self.assertEqual(
            self._copy_mjcf().read_text(encoding="utf-8"),
            SHIPPED_MJCF,
            "副本 MJCF 仍是旧形态 —— 训练/验收会用第二套执行真值",
        )

    def test_stale_copy_only_mesh_is_pruned(self):
        robot_packages.rebuild_package_index()
        self.assertFalse(
            (self._target / "model" / "assets" / "old_mesh.stl").exists(),
            "源树没有的陈旧模型文件仍留在副本（内容集合不一致）",
        )

    def test_new_shipped_mesh_is_copied(self):
        robot_packages.rebuild_package_index()
        (self._shipped / "model" / "assets" / "fresh.stl").write_bytes(b"solid fresh\n")
        robot_packages.invalidate_package_cache()
        robot_packages.list_robot_packages()
        self.assertTrue(
            (self._target / "model" / "assets" / "fresh.stl").is_file(),
            "源树新增模型文件未同步到副本",
        )

    def test_identical_model_is_left_untouched(self):
        robot_packages.rebuild_package_index()
        mtime_first = self._copy_mjcf().stat().st_mtime_ns
        robot_packages.rebuild_package_index()
        self.assertEqual(
            self._copy_mjcf().stat().st_mtime_ns,
            mtime_first,
            "内容一致的模型被无谓重写（应为内容级比较跳过）",
        )

    def test_declared_training_asset_is_mirrored(self):
        """训练资产声明（`model.training_path`）是**出厂事实**：副本清单必须跟着声明。

        运行时包根是 workspace 副本，副本清单缺这条声明 ⇒ 训练侧装配退回 `model.path`。
        go2 就是这个形状：包内两份 MJCF（上游 `robot.xml` + 合族约定的 `training.xml`），
        拿上游那份去撞族约定会在足端几何上判红（名不含 `foot`）。
        """
        robot_packages.rebuild_package_index()
        manifest = json.loads((self._shipped / "robot_package.json").read_text(encoding="utf-8"))
        manifest["model"]["training_path"] = "model/training.xml"
        _write_json(self._shipped / "robot_package.json", manifest)
        (self._shipped / "model" / "training.xml").write_text(SHIPPED_MJCF, encoding="utf-8")
        robot_packages.invalidate_package_cache()
        robot_packages.list_robot_packages()
        copied = json.loads((self._target / "robot_package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "model/training.xml",
            (copied.get("model") or {}).get("training_path"),
            "副本清单没有跟着声明训练资产 —— 训练会用第二套（上游）资产",
        )
        self.assertTrue((self._target / "model" / "training.xml").is_file())

    def test_signature_detects_mjcf_change(self):
        """签名不覆盖 `model/` 就不会触发重扫，镜像等于没接。"""
        robot_packages.list_robot_packages()
        robot_packages.invalidate_package_cache()
        self.assertFalse(robot_packages._index_is_stale(), "刚重建的索引不应判为过期")
        self._shipped_mjcf().write_text(SHIPPED_MJCF.replace('kp="30"', 'kp="45"'), encoding="utf-8")
        robot_packages.invalidate_package_cache()
        self.assertTrue(robot_packages._index_is_stale(), "源树 MJCF 变更未被签名捕获")


if __name__ == "__main__":
    unittest.main()
