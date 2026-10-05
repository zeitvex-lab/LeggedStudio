"""B8 冒烟产物（4 条 `origin=product-training`）的**口径取证与阻断原因**回归锁。

## 这 4 条为什么值得单独守（2026-09-23 v0.59.0）

它们的阻断原因原先写的是"`observation_kind=unknown`（布局未逐项取证）… 补齐取证并补 builder
后把 `sim_ready` 改回 true"——**这句话里有一半是错的、另一半会诱导人做错事**：

* 布局**这轮已逐项取证**（自训练源 `adapters/mjlab/kits/wheel_leg_kit/velocity_env_cfg.py::policy_terms`
  + 包内 `training/source/*/env_cfgs.py`；b2 那条用验收器既有 `_frame_go2_mjlab_actor_48` 的逐项序）；
* 但"补完取证就能翻 `sim_ready`"是**错的**：真正的原因是**行为级不合格**——按各自训练期口径
  （布局 + 动作缩放 + 默认姿态）跑无头验收，b2w/b2 直接摔倒、go2w/m20 站得住但不跟踪
  （速度任务看的就是跟踪）。照旧文案翻 `sim_ready`，换来的就是把"站得住不走"的产物摆进页面。

所以本文件锁三件事：**布局取证仍在**（且解释器吃得下、两侧同口径）、**阻断原因说的是实测**、
**口径来源可追溯**（默认姿态必须与 ONNX 元数据逐值一致，防手抄）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: (robot, policy_id) 名册**声明驱动**（㉖ 先例）：从全仓 `origin=product-training`
#: 的条目现取，不再硬编码 id——2026-10-05 ㊃ 审计删了 2 条死件（b2w-093241 /
#: m20-090509，kind=unknown 从未命名布局，不可验收不可评估），硬编码名册随之全红；
#: 名册再变（新产物入库/旧产物退役）本套件自动跟随。
def _product_with_layout() -> list[tuple[str, dict]]:
    return [(robot, e) for robot, e in _products()
            if (e.get("contract") or {}).get("observation_layout")]


def _product_with_forensics_note() -> list[tuple[str, dict]]:
    """note 带「取证」留痕的产物——写取证话就必须写清来源（防照抄旧文案的那半句话）。"""
    return [(robot, e) for robot, e in _products()
            if "取证" in str(e.get("note") or "")]


def _blocked_product_with_layout() -> tuple[str, dict] | None:
    """sim_ready=False 且已声明布局的产物（对拍真跑的活体对象）。"""
    for robot, e in _product_with_layout():
        if e.get("sim_ready") is False:
            return robot, e
    return None


def _entry(robot: str, policy: str) -> dict:
    path = ROOT / "assets" / "robots" / robot / "simulation" / "config.json"
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    return next(e for e in config["policies"] if e["id"] == policy)


def _products() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for config_path in sorted((ROOT / "assets" / "robots").glob("*/simulation/config.json")):
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        for entry in config.get("policies") or []:
            if (entry.get("provenance") or {}).get("origin") == "product-training":
                out.append((config_path.parents[1].name, entry))
    return out


class CoverageTest(unittest.TestCase):
    def test_every_product_training_artifact_has_a_layout_and_a_measured_blocker(self):
        """**没有例外**：凡是产品训练产物且被阻断的，都必须声明布局并把实测结论写进原因。

        新装一条产物却照抄旧文案（"布局未取证…补 builder 即可"）会在本用例报红——
        这正是 2026-09-23 订正的那句话。
        """

        products = _products()
        self.assertGreaterEqual(len(products), 4, "产品训练产物数量异常，抽取逻辑可能失效")
        for robot, entry in products:
            with self.subTest(robot=robot, policy=entry["id"]):
                contract = entry.get("contract") or {}
                if entry.get("sim_ready") is False:
                    self.assertTrue(contract.get("observation_layout"),
                                    f"{robot}/{entry['id']} 被阻断但没声明布局 ⇒ 只会永远停在「验收器不支持该布局」")
                    blocker = str(entry.get("sim_blocker") or "")
                    self.assertNotIn("布局未逐项取证", blocker,
                                     "阻断原因还写着旧文案：布局已取证，别再叫人「补完取证就翻 sim_ready」")
                    self.assertTrue("实测" in blocker or "行为级" in blocker,
                                    f"{robot}/{entry['id']} 的阻断原因必须写清**实测结论**（不是「缺 builder」）")


class LayoutForensicsTest(unittest.TestCase):
    def test_layout_width_matches_obs_dim_via_the_real_interpreter(self):
        """布局不只是"有"，还要**解释器吃得下**且宽度 == `obs_dim`（走两侧共用的那一份规格）。"""

        try:
            import mujoco  # noqa: F401
        except ImportError:  # pragma: no cover - 环境缺 mujoco
            self.skipTest("缺 mujoco")
        import importlib.util

        spec = importlib.util.spec_from_file_location("pa_frames",
                                                     ROOT / "adapters" / "mjlab" / "policy_acceptance.py")
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)

        for robot, entry in _product_with_layout():
            with self.subTest(robot=robot, policy=entry["id"]):
                policy = entry["id"]
                package = ROOT / "assets" / "robots" / robot
                sim_cfg = json.loads((package / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
                contract = engine.PackageContract(package, entry)
                contract.motion_loader = None
                model = engine.load_package_model(package, sim_cfg, None,
                                                  scene_rel=contract.contract.get("scene_path"))
                model.opt.timestep = 1.0 / contract.physics_hz
                data = mujoco.MjData(model)
                obs_builder = engine.ObsBuilder(contract, model, data)
                engine.spawn_default(contract, model, data, obs_builder)
                obs_builder.last_action = __import__("numpy").zeros(contract.action_dim, dtype="float32")
                frame = engine.frame_from_spec(obs_builder, __import__("numpy").zeros(3, dtype="float32"),
                                               contract.contract["observation_layout"])
                self.assertEqual(int(entry["obs_dim"]), len(frame),
                                 f"{robot}/{policy} 布局算出的宽度与 obs_dim 不符")

    def test_declared_defaults_match_onnx_metadata(self):
        """**防手抄**：声明了 `default_joint_angles` 的条目，必须与 ONNX 元数据逐值一致。

        ONNX 元数据是**导出时盖章的训练真值**（`joint_names` × `default_joint_pos`），
        与包级默认姿态可能不同（b2w 就是：训练 hip −0.1 / 包级 0.0）——手抄错一个数，
        策略就永远站不对，而这种现象在报告里只会表现为"这个策略不行"。
        """

        try:
            import onnxruntime as ort
        except ImportError:  # pragma: no cover
            self.skipTest("缺 onnxruntime")

        checked = 0
        for robot, entry in _product_with_layout():
            declared = (entry.get("contract") or {}).get("default_joint_angles")
            if not declared:
                continue
            policy = entry["id"]
            onnx = ROOT / "assets" / "robots" / robot / "simulation" / "policies" / f"{policy}.onnx"
            if not onnx.is_file():
                continue  # ONNX 不在盘上的产物另有「影子/缺失」面（AuxBlobTest）守，这里只对在盘的防手抄
            with self.subTest(robot=robot, policy=policy):
                meta = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"]
                                            ).get_modelmeta().custom_metadata_map
                names = [n.strip().lower() for n in str(meta.get("joint_names") or "").split(",") if n.strip()]
                values = [float(v) for v in str(meta.get("default_joint_pos") or "").split(",") if v.strip()]
                expected = dict(zip(names, values))
                # 声明键与 ONNX 元数据键都归一小写比对（生产路径 PackageContract 加载时
                # 本就 k.lower() 归一——大小写是书写风格不是关节身份）。
                declared_norm = {str(k).lower(): float(v) for k, v in declared.items()}
                self.assertEqual(set(expected), set(declared_norm),
                                 f"{robot}/{policy} 声明的默认姿态关节集合与 ONNX 元数据不一致")
                for joint, value in declared_norm.items():
                    self.assertAlmostEqual(expected[joint], float(value), places=5,
                                           msg=f"{robot}/{policy} 的 {joint} 默认角与 ONNX 元数据不符")
            checked += 1
        self.assertGreaterEqual(checked, 1, "没有任何条目声明 default_joint_angles —— 抽取逻辑可能失效")

    def test_evidence_is_traceable_in_note(self):
        roster = _product_with_forensics_note()
        self.assertGreaterEqual(len(roster), 1,
                                "没有任何产物带「取证」留痕 —— 取证话本可能整代消失，先确认再改这条守卫")
        for robot, entry in roster:
            with self.subTest(robot=robot, policy=entry["id"]):
                note = str(entry.get("note") or "")
                self.assertTrue("kits/wheel_leg_kit" in note or "_frame_go2_mjlab_actor_48" in note,
                                f"{robot}/{entry['id']} 的 note 没有写清取证来源（训练源/既有帧）")

    def test_m20_per_joint_scales_follow_its_training_source(self):
        """m20 的动作缩放是**逐关节**的（hipx 0.125 / 腿余 0.25 / 轮 5.0），与包级一刀切不同。

        载体 = 现役声明条目 `m20-velocity-57`（㊃ 审计删掉的 20260918 死件产品曾是其载体，
        契约真值不变，只是搬了家——2026-10-05 重钉）。
        """

        contract = _entry("deeprobotics_m20", "m20-velocity-57")["contract"]
        scales = contract.get("action_scale_by_joint") or {}
        self.assertEqual({"0.125", "0.25", "5.0"}, {f"{v}" for v in scales.values()})
        for joint, value in scales.items():
            expected = 0.125 if "hipx" in joint else (5.0 if "wheel" in joint else 0.25)
            self.assertAlmostEqual(expected, float(value), places=5, msg=joint)


class CrosscheckAppliesTest(unittest.TestCase):
    """取证过的布局**必须真的被比对过**：工具对这类条目不再早退（真跑一次）。"""

    def test_crosscheck_no_longer_short_circuits_blocked_entries_with_a_layout(self):
        node = shutil.which("node")
        if not node:  # pragma: no cover - CI 无 node 时如实跳过
            self.skipTest("缺 node（对拍驱动浏览器侧 JS）")

        source = (ROOT / "tools" / "obs_crosscheck.py").read_text(encoding="utf-8")
        self.assertIn('entry.get("sim_ready") is False and not (entry.get("contract") or {}).get("observation_layout")',
                      source, "对拍工具对「已声明布局的阻断条目」仍会早退 —— 取证过的规格等于没验")

        subject = _blocked_product_with_layout()
        self.assertIsNotNone(subject,
                             "没有任何「阻断且已声明布局」的产物 —— 对拍活体对象消失，先确认再改这条守卫")
        robot, entry = subject
        done = subprocess.run(
            [sys.executable, "tools/obs_crosscheck.py", "--robot", robot,
             "--policy", entry["id"]],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(0, done.returncode, f"对拍未通过（两侧口径不一致）：\n{done.stdout[-1500:]}")
        self.assertIn("一致", done.stdout)


if __name__ == "__main__":
    unittest.main()
