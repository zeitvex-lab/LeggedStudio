"""同状态对拍**本身**的回归锁（工具 → 驱动体 → 浏览器构建器 这一整条链）。

## 为什么专门守这条链（2026-09-22 一天内同类缺陷连出三次）

`tools/obs_crosscheck.py` + `tools/obs_crosscheck.mjs` 是"两份实现同口径"的**唯一**判据——
也就是说，**它错了就没人守得住了**。这一天连出三次，而且每次的错法都长成"红"：

1. **切错槽**：有历史时把"当前帧"一律取 `packed[:obs_dim]` ⇒ term-major 布局下取到的是
   "第 0 段的历史"，5 条 `go2_rl_sdk_45` 族策略被误报不一致（实为逐维一致 5.96e-08）；
2. **少喂输入**：`CONTROL_MODES` 写死全 `position` ⇒ m20/b2w 的 `go2w_rl_sdk_57` 轮位不清零，
   误报 Δ=5.000e-02；
3. **假设了不成立的布局**：`qpos = [pos, quat, 关节…]` 只对"机器人本体是第一个自由关节"
   成立，wuji_hand（唯一自由关节是立方体）因此把手指关节当四元数读 ⇒ IMU 段恒红。

**共同教训**：被测物报红时，**先怀疑尺子**；而尺子必须自己有测试。本文件把这条链的
代表性分支逐条跑通（真跑 mujoco + node，不是文本级断言），另有一条**反例注入**：
把浏览器侧的 `control_modes` 输入抽掉，必须变红——证明这条链真的在测东西。

覆盖的代表性分支（各对应上面一类陷阱）：
* `unitree_go2/go2-moe-cts`：有历史 + 缺省 term-major（陷阱 1）；
* `deeprobotics_m20/m20-velocity-57`：**逐关节**声明 `control_modes`（陷阱 2）；
* `unitree_go2w/go2w-velocity-robotlab`：**角色级** `{"wheel": "velocity"}`（陷阱 2 的另一形）；
* `unitree_go2/go2-lainlab-trot`：相位钟（`gait_period_s` 非零，`simulationDt` 缺喂会 NaN）；
* `zex-w/zex-w-rough-9600`：轮足 + 角色/逐关节双形态 `control_modes`。

**2026-09 family-arch 收敛后的删减**：原 `unitree_g1/g1-velocity`（相位钟）与
`wuji_hand/wuji-reorient`（陷阱 3：自由关节不在 qpos 0 位）两条已随对应包出库删除；
相位钟分支改由 `go2-lainlab-trot` 重锚，陷阱 3 在保留的 8 机型上无适用对象
（浮动基座都在 `qpos[0:7]`），工具侧实现保留、仅不再有真机用例。
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
TOOL = ROOT / "tools" / "obs_crosscheck.py"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=600,
    )


@unittest.skipUnless(_have("node"), "对拍需要 node")
class CrosscheckHarnessTest(unittest.TestCase):
    """逐条跑代表策略：**必须绿**（红了先看这里的注释，别急着改实现）。"""

    CASES = (
        ("unitree_go2", "go2-moe-cts", "有历史 + 缺省 term-major 布局"),
        ("deeprobotics_m20", "m20-velocity-57", "逐关节 control_modes（轮位清零）"),
        ("unitree_go2w", "go2w-velocity-robotlab", "角色级 control_modes"),
        ("unitree_go2", "go2-lainlab-trot", "相位钟（gait_period_s 非零，simulationDt 缺喂即 NaN）"),
        ("zex-w", "zex-w-rough-9600", "轮足 + 角色/逐关节双形态 control_modes"),
    )
    # 原 g1-velocity（相位钟）与 wuji-reorient（陷阱 3：自由关节不在 qpos[0]）两条
    # 已随 unitree_g1 / wuji_hand 出库删除（family-arch 收敛）：相位钟分支改由
    # go2-lainlab-trot 覆盖；"自由关节不在 0 位 ⇒ IMU 段不适用"机制在保留机型上
    # 不成立（8 机型的浮动基座都在 qpos[0:7]），无重锚对象，仅在工具侧保留实现。

    def test_representative_policies_match(self):
        for robot, policy, why in self.CASES:
            with self.subTest(robot=robot, policy=policy):
                done = _run("--robot", robot, "--policy", policy)
                self.assertEqual(
                    0, done.returncode,
                    f"{robot}/{policy}（{why}）对拍未过：\n{done.stdout[-3000:]}\n{done.stderr[-1500:]}",
                )
                self.assertIn("一致", done.stdout)

    # 原 ``test_wuji_skips_imu_instead_of_reporting_red`` 已随 wuji_hand 出库删除
    # （family-arch 收敛，2026-09）：它钉的是"自由关节不在 qpos[0] ⇒ IMU 诊断段如实
    # 标不适用"这一机制；保留的 8 机型浮动基座全在 qpos[0:7]，该分支没有可重锚的
    # 真机数据（工具侧实现与其语义保持不变，仅测试对象随产品清单收敛）。

    def test_blocked_entry_without_layout_is_reported_not_green(self):
        """`sim_ready:false` **且没有布局** ⇒ 报"不适用"，既不绿也不红。

        **2026-09-23 收窄**：原先这条断言的是"`sim_ready:false` ⇒ 一律不适用"。但那样一来
        **取证过布局的阻塞条目永远不会被比对**（"取证等于没验"）；工具已改为"只有既没布局、
        又标了不可仿真才早退"。这里用**反例注入**（临时撤掉布局）来钉住剩下的那一半：
        没有可比的那一层时，仍须如实报不适用，不许伪装成绿。
        """
        import json as _json

        config_path = ROOT / "assets" / "robots" / "unitree_b2" / "simulation" / "config.json"
        original = config_path.read_bytes()
        bom = original[:3] == b"\xef\xbb\xbf"
        data = _json.loads(original.decode("utf-8-sig"))
        entry = next(e for e in data["policies"] if e["id"] == "unitree_b2-trained-20260918-015414")
        self.assertIn("observation_layout", entry["contract"], "靶子变了：该条目本来就该带布局")
        entry["contract"].pop("observation_layout")           # 注入：撤掉布局
        config_path.write_bytes((b"\xef\xbb\xbf" if bom else b"")
                                + _json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        try:
            done = _run("--robot", "unitree_b2", "--policy", "unitree_b2-trained-20260918-015414")
        finally:
            config_path.write_bytes(original)
        self.assertEqual(2, done.returncode, done.stdout[-2000:])
        self.assertIn("sim_ready:false", done.stdout)


class CrosscheckCounterfactualTest(unittest.TestCase):
    """**反例注入**：把控制模式解析退回"写死全 position" ⇒ 对拍必须变红。

    这就是 2026-09-22 的第二个陷阱本身（驱动体把 `controlModes` 写死成全 `position`，
    于是"轮位清零"分支走错、m20/b2w 被误报不一致）。防的是"这条链看着在跑、其实
    解析没接上"：**只跑端到端是抓不到的**（有人把解析删掉、端到端会继续绿），
    必须靠注入把"没有它就会错"钉成事实。
    """

    def test_hardcoded_positions_turn_m20_red(self):
        harness = ROOT / "tools" / "obs_crosscheck.mjs"
        original = harness.read_text(encoding="utf-8")
        need = "  CONFIG.controlModes = modes;"
        self.assertIn(need, original, "对拍驱动体没有把解析结果写回 CONFIG.controlModes")
        patched = original.replace(need, "  CONFIG.controlModes = new Array(numActions).fill(\"position\");")
        harness.write_text(patched, encoding="utf-8")
        try:
            done = _run("--robot", "deeprobotics_m20", "--policy", "m20-velocity-57")
        finally:
            harness.write_text(original, encoding="utf-8")
        self.assertEqual(1, done.returncode,
                         f"退回'全 position'后本应变红（说明控制模式其实没参与判定）：\n{done.stdout[-2000:]}")
        self.assertIn("不一致", done.stdout)

    def test_harness_resolves_instead_of_hardcoding(self):
        """文本级补刀：驱动体必须**调用共用解析器**（不是自己再写一份表）。"""
        harness = (ROOT / "tools" / "obs_crosscheck.mjs").read_text(encoding="utf-8")
        self.assertIn("resolveActuatorRolesAndModes", harness)
        self.assertIn("D.control_modes?.robot", harness)


class CrosscheckAllModeTest(unittest.TestCase):
    """`--all` 是**门禁**用法：任一条红即非 0；不适用（需 MotionLoader / sim_ready:false）必须单列。"""

    @unittest.skipUnless(_have("node"), "对拍需要 node")
    def test_all_mode_summarizes_and_passes(self):
        done = _run("--all")
        self.assertEqual(0, done.returncode, done.stdout[-3000:])
        self.assertIn("汇总：", done.stdout)
        summary = next(line for line in done.stdout.splitlines() if line.startswith("汇总："))
        self.assertIn("0 不一致", summary)
        # 不适用必须**显式**出现（否则"不适用"会伪装成绿）
        self.assertIn("不适用", done.stdout)

    def test_all_targets_cover_declared_policies(self):
        """`--all` 的靶子集合 == 各包 `simulation/config.json` 的声明数（不许漏跑）。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("obs_crosscheck_for_targets", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        targets = module._all_targets()
        declared = 0
        for config_path in sorted((ROOT / "assets" / "robots").glob("*/simulation/config.json")):
            cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
            declared += len([e for e in (cfg.get("policies") or []) if isinstance(e, dict) and e.get("id")])
        self.assertEqual(declared, len(targets))
        self.assertEqual(len(targets), len(set(targets)), "靶子集合有重复")


if __name__ == "__main__":
    unittest.main()
