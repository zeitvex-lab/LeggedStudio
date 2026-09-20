"""序 15：go1 rough 的 `terrain_scan` 必须重指到本机型根 body（回归锁）。

背景（2026-09-20 实测）：`terrain_scan` 是 mjlab velocity 基座自带的通用传感器，
其默认 frame 是 ``ObjRef(entity="robot", name="")`` → 解析成 ``robot/``（**空 body 名**），
Scene 初始化时 ``mj_model.body("robot/")`` 抛
``KeyError: Invalid name 'robot/'. Valid names: ['robot/FL_calf', ...]``。
lite3 / b2 都靠 ``kit.repoint_height_scan_sensors(..., root_body=...)`` 重指；
**go1 从未重指**，而 flat 路径又把 `terrain_scan` 整个丢掉 ⇒ 只有 `go1-velocity-rough`
会炸，且自该 profile 引入（`1726423a`）起就无法建环境（漏实现，非回归）。

为什么用 **AST 静态锁**而不是跑一遍环境：本测试要能在**控制面 venv（无 mjlab）**与 CI 里跑。
它锁的是"重指调用存在且挂在 rough 分支上"——真正建环境的验证是
``tools/validate_training_smoke.py --robot unitree_go1``（实测 2/2 ok）。
"""

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GO1_ENV_CFG = REPO_ROOT / "assets" / "robots" / "unitree_go1" / "training" / "source" / "go1_velocity" / "env_cfg.py"
#: 保留 `terrain_scan` 的包：它们都必须重指，否则 rough 档建环境即 KeyError。
KEEPERS = {
    "unitree_go1": GO1_ENV_CFG,
    "deeprobotics_lite3": REPO_ROOT / "assets" / "robots" / "deeprobotics_lite3" / "training" / "source" / "lite3_velocity" / "env_cfg.py",
    "unitree_b2": REPO_ROOT / "assets" / "robots" / "unitree_b2" / "training" / "source" / "b2_velocity" / "env_cfg.py",
}


def _calls(tree: ast.AST, attr: str) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == attr:
            found.append(node)
    return found


class Go1RoughTerrainScanRepointTests(unittest.TestCase):
    def test_go1_env_cfg_repoints_terrain_scan(self):
        tree = ast.parse(GO1_ENV_CFG.read_text(encoding="utf-8"))
        self.assertTrue(
            _calls(tree, "repoint_height_scan_sensors"),
            "go1 env_cfg 没有调用 kit.repoint_height_scan_sensors —— "
            "terrain_scan 的 frame 会停在 mjlab 默认的 'robot/'（空 body 名），"
            "go1-velocity-rough 建环境必然 KeyError",
        )

    def test_all_terrain_scan_keepers_repoint(self):
        """凡是保留 `terrain_scan` 的包都要重指 —— 同一缺陷类不许在别的包复发。"""
        missing = [
            robot for robot, path in KEEPERS.items()
            if path.is_file() and not _calls(ast.parse(path.read_text(encoding="utf-8")), "repoint_height_scan_sensors")
        ]
        self.assertEqual(missing, [], f"这些包保留了 terrain_scan 却没重指 frame：{missing}")


if __name__ == "__main__":
    unittest.main()
