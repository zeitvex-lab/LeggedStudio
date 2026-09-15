"""B24：generic MJCF 路径 episode_length_s 的「构建缺省 + 显式覆盖」语义锁定。

B23 已把「请求省略 episode_length_s = 沿用任务真值」落地（带 profile 的 14 内置机型
走各自训练源码真值）。但 generic MJCF 任务路径（``adapters/mjlab/generic_task_builder.py``）
服务于用户导入、无训练源码/无 profile 的 generic 包——**没有任务真值层可沿用**。

B24 裁决：维持 20.0 作为 generic 路径的**构建缺省**（非覆盖真值）——它不是「覆盖真值」
而是「唯一显式来源」，被显式写进 env_cfg 与 resolved 配置（可见、可查）；请求显式提供
episode_length_s 时经 environment 传入即生效（B23 真值守卫只拦 None/缺键，不拦 generic
路径的显式值）。否决「改契约声明」（episode_length_s 是任务层字段，B13 三层拆分裁决
物理/契约层不放任务字段）；否决「强制显式提供」（generic 路径的存在意义就是零配置
可跑，V7）。

分层锁定（只测 episode_length 取值语义这一层，不触物理仿真）：

1. **取值语义**（控制面 venv 直测）：generic_task_builder 顶层仅 stdlib（mjlab 全部
   懒加载在 build_generic_task 函数体内），控制面 venv 可直接导入；取值提炼为模块级
   ``_episode_length_s``，缺键 → 20.0、显式 → 原样。
2. **真实构建接线**（mjlab 适配器 venv 子进程，缺 venv/夹具则跳过）：完整
   ``build_generic_task`` → ``env_cfg.episode_length_s``，锁住「取值确实接在
   environment → env_cfg」这条链路（cartpole 夹具，与
   ``adapters/mjlab/test_generic_task_builder.py`` 同款最小契约）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.generic_task_builder import _episode_length_s

#: mjlab 适配器 venv（有 mjlab/mujoco）；不存在（如精简 CI）则跳过端到端用例。
_MJLAB_PYTHON = ROOT / "adapters" / "mjlab" / ".venv" / "Scripts" / "python.exe"


class EpisodeLengthBuildDefaultTest(unittest.TestCase):
    """取值语义（控制面 venv，零 mjlab 依赖）：缺键 → 构建缺省 20.0；显式值 → 原样生效。"""

    def test_missing_key_falls_to_build_default(self):
        """① 请求省略（environment 无该键）→ 构建缺省 20.0（generic 路径无真值层可沿用）。"""
        value = _episode_length_s({})
        self.assertEqual(20.0, value)
        self.assertIsInstance(value, float)

    def test_explicit_value_wins(self):
        """② 请求显式提供 10.0 → 原样生效（B23 守卫不拦 generic 路径的显式值）。"""
        self.assertEqual(10.0, _episode_length_s({"episode_length_s": 10.0}))

    def test_value_coerced_to_float(self):
        """行内 float() 语义：字符串/整数输入同样落 float（recipe 层同口径）。"""
        self.assertEqual(12.0, _episode_length_s({"episode_length_s": "12"}))
        coerced = _episode_length_s({"episode_length_s": 30})
        self.assertEqual(30.0, coerced)
        self.assertIsInstance(coerced, float)


def _cartpole_contract(xml: Path) -> dict:
    """与 adapters/mjlab/test_generic_task_builder.py 同款最小契约（cartpole 夹具）。"""
    return {
        "contract_id": "generic_fixture",
        "urdf": {"path": str(xml)},
        "joints": {"actuated_joints": ["slider"], "default_pose": [0.0]},
        "action": {"joint_order": ["slider"], "action_scale": 0.5},
        "observation": {"components": ["joint_pos", "joint_vel", "last_action"]},
        "control": {"decimation": 5, "physics_hz": 100},
    }


#: 子进程脚本：只构建配置（不 launch 仿真、不占 GPU），输出一行 JSON。
_CHILD = r"""
import json, sys, pathlib
sys.path.insert(0, sys.argv[1])
from adapters.mjlab.generic_task_builder import build_generic_task
import mjlab

xml = pathlib.Path(mjlab.__file__).resolve().parent / "tasks" / "cartpole" / "cartpole.xml"
if not xml.exists():
    print(json.dumps({"skip": "MJLab cartpole fixture is unavailable"}))
    raise SystemExit(0)

contract = json.loads(sys.argv[2])
contract["urdf"]["path"] = str(xml)  # 夹具真实路径由子进程按 mjlab 包内位置解析
base = {"environment": {"terrain_type": "plane"}, "reward_scales": {"joint_torques_l2": -0.01}}
default = build_generic_task(contract, base)
explicit = build_generic_task(
    contract, {**base, "environment": {"terrain_type": "plane", "episode_length_s": 10.0}}
)
print(json.dumps({
    "default": default.env_cfg.episode_length_s,
    "explicit": explicit.env_cfg.episode_length_s,
}))
"""


@unittest.skipUnless(_MJLAB_PYTHON.is_file(), "mjlab 适配器 venv 不存在，跳过真实构建端到端")
class GenericBuildEpisodeLengthEndToEndTest(unittest.TestCase):
    """真实构建接线（mjlab venv 子进程）：environment → build_generic_task → env_cfg.episode_length_s。"""

    def _build_both(self) -> dict:
        contract = _cartpole_contract(Path("cartpole.xml"))  # 路径由子进程按 mjlab 包内夹具解析
        proc = subprocess.run(
            [str(_MJLAB_PYTHON), "-c", _CHILD, str(ROOT), json.dumps(contract)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT), timeout=240,
        )
        self.assertEqual(
            0, proc.returncode,
            f"mjlab 子进程构建失败:\n{(proc.stdout or '') + (proc.stderr or '')[-2000:]}",
        )
        lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
        self.assertTrue(lines, f"子进程无输出:\n{proc.stderr or ''[-2000:]}")
        return json.loads(lines[-1])

    def test_build_default_and_explicit_override(self):
        payload = self._build_both()
        if "skip" in payload:
            self.skipTest(payload["skip"])
        # ① environment 无该键 → 构建出的 env_cfg.episode_length_s == 20.0
        self.assertEqual(20.0, payload["default"])
        # ② environment 提供 10.0 → 构建出的 env_cfg.episode_length_s == 10.0
        self.assertEqual(10.0, payload["explicit"])


if __name__ == "__main__":
    unittest.main()
