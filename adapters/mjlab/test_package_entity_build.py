"""包内档案的**实体层**回归锁：env cfg 声明的执行器组不能与 MJCF 自带执行器撞名。

`m20-dreamwaq` 2026-09-24 冒烟红（`ValueError: Error: repeated name 'fl_hipx_joint' in
actuator`）：它的 `constants.get_spec()` 直接读**包级** `model/robot.xml`，而那份 MJCF 自带 16 个
与关节同名的 `<position>`/`<velocity>` 执行器；`M20_ARTICULATION` 又声明了覆盖同一批关节的
builtin 组 ⇒ mjlab 生成同名执行器时直接崩。`m20-velocity` 不炸是因为它读的是包内
`training/source/m20_velocity/xmls/M20.xml`（那份没有 `<actuator>` 段）——同一个包里两条档案
对"谁是执行真值"的口径不一致，正是本锁要拦的。

为什么锁在**实体层**：这个错在 `Entity(cfg)` 构造时就抛，预览、schema dump 与静态门禁都看不出来
（`tools/validate_training_smoke.py` 真跑才抓到）。建实体不建地形/环境，秒级完成。
全 33 档的真跑口径仍以 `tools/validate_training_smoke.py` 为准（本文件是它的廉价前哨）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGE_ROOT = ROOT / "assets" / "robots" / "deeprobotics_m20"

# (档案 id, 入口 ``module:attr``, 期望执行器数) —— 期望值取契约：12 腿 + 4 轮。
PROFILES = (
    ("m20-velocity", "m20_velocity.env_cfgs:m20_flat_env_cfg", 16),
    ("m20-dreamwaq", "m20_dreamwaq.config:make_m20_dreamwaq_env_cfg", 16),
)


class PackageEntityBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import mujoco  # noqa: F401
            import mjlab  # noqa: F401
        except ImportError as exc:  # pragma: no cover - 依赖缺失时如实跳过
            raise unittest.SkipTest(f"训练栈不可用: {exc}")
        source_root = PACKAGE_ROOT / "training" / "source"
        for path in (str(source_root), str(PACKAGE_ROOT)):
            if path not in sys.path:
                sys.path.insert(0, path)

    def test_profile_entities_build_without_actuator_name_clash(self):
        from mjlab.entity import Entity

        failures: list[str] = []
        for profile_id, entrypoint, expected_actuators in PROFILES:
            with self.subTest(profile=profile_id):
                module_name, _, attr = entrypoint.partition(":")
                module = __import__(module_name, fromlist=[attr])
                cfg = getattr(module, attr)(play=False)
                entities = dict(getattr(cfg.scene, "entities", {}) or {})
                self.assertTrue(entities, f"{profile_id} 没有场景实体")
                for name, ent_cfg in entities.items():
                    try:
                        entity = Entity(ent_cfg)
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{profile_id}/{name}: {type(exc).__name__}: {exc}")
                        continue
                    actuator_names = list(getattr(entity, "actuator_names", []) or [])
                    if len(actuator_names) != expected_actuators:
                        failures.append(
                            f"{profile_id}/{name}: 执行器 {len(actuator_names)} 个，"
                            f"期望 {expected_actuators}: {actuator_names}"
                        )
                    # 传感器必须**全都有名字**：mjlab 的 scene 按名包装每个 spec 传感器，
                    # 无名传感器会让 `ManagerBasedRlEnv(...)` 抛 `Invalid name ''`
                    # （实体能建、环境才炸 —— 2026-09-24 m20-dreamwaq 实测）。
                    spec = ent_cfg.spec_fn()
                    unnamed = [index for index, sensor in enumerate(spec.sensors) if not sensor.name]
                    if unnamed:
                        failures.append(f"{profile_id}/{name}: {len(unnamed)} 个传感器没有名字")
        self.assertEqual([], failures, "包内档案的实体建不起来：\n" + "\n".join(failures))

    def test_m20_dreamwaq_env_builds_and_steps(self):
        """m20-dreamwaq 真建环境 + reset/step（这一档此前两处崩：执行器撞名、无名传感器）。"""
        import torch
        from mjlab.envs import ManagerBasedRlEnv

        module_name, _, attr = "m20_dreamwaq.config:make_m20_dreamwaq_env_cfg".partition(":")
        cfg = getattr(__import__(module_name, fromlist=[attr]), attr)(play=False)
        cfg.scene.num_envs = 2
        env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
        try:
            obs, _ = env.reset()
            action = torch.zeros((env.num_envs, env.action_manager.total_action_dim))
            env.step(action)
            self.assertEqual(tuple(obs["actor"].shape)[0], env.num_envs)
        finally:
            close = getattr(env, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    unittest.main()
