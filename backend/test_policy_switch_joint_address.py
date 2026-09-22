"""**切换策略必须重建关节/执行器地址表** —— 否则"伸出来一条腿然后马上死"。

## 这道守卫防的是什么（2026-09-21 实测复现）

`web/sim2sim/app.js` 里三张表 —— `sim.jointQposAdr` / `sim.jointDofAdr` /
`sim.actuatorIds` —— 按 `CONFIG.jointOrder` 的**名字**解析 MuJoCo 模型地址，却原来
只在**加载 MuJoCo 模型**时建一次（`resolveJointAddresses` / `resolveActuatorAddresses`）。

而 `CONFIG.jointOrder` 会被**策略契约**覆盖（`contract.action_joint_order`，供
LeggedSkillDeploy 这类"训练序 ≠ 模型序"的策略使用）。于是：

- URL 直开（契约先于模型应用）→ 地址表按新序建 → 正常；
- **下拉切换策略**（模型已就绪，只换契约）→ 地址表还是**上一个策略的序** →
  `resetSimulation()` 把新序的默认角写进旧序的关节槽：髋角写进大腿槽、后腿髋被设到
  ±1.5 rad ⇒ 机器人"伸出来一条腿然后马上死"（实测 loco-45 切换后 RL_hip=+1.06、
  RR_hip=-1.07、z 0.27→0.17 直掉）。

这与"观测布局静默回落"同族：**不报错、只是策略不行**，且只在浏览器侧暴露（Python
验收器 `policy_acceptance.py` 按名字建 `jadr`，没有这个问题）。

## 判据（跨语言只能文本级守卫）

1. app.js 中 `CONFIG.jointOrder` 赋值之后**必须**紧接
   `resolveJointAddresses()` + `resolveActuatorAddresses()`（带 `sim.model` 就绪判断）；
2. 数据侧必须**真有**"动作序 ≠ 机型默认序"的策略（否则上面这条是空守卫——
   没有这类策略时回归永远不会被触发）。
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_JS = ROOT / "web" / "sim2sim" / "app.js"
ROBOTS_DIR = ROOT / "assets" / "robots"

#: 赋值点之后允许出现其它语句的窗口（注释/默认角查找都在其后，但重建调用必须紧邻）
WINDOW = 24


class PolicySwitchJointAddressTest(unittest.TestCase):
    def test_joint_order_assignment_rebuilds_address_tables(self):
        """`CONFIG.jointOrder` 赋值后必须重建三张地址表（文本级守卫）。"""

        source = APP_JS.read_text(encoding="utf-8")
        anchor = source.index("CONFIG.jointOrder = order.slice(0, CONFIG.numActions);")
        window = source[anchor:anchor + 4000]
        self.assertIn(
            "resolveJointAddresses();", window,
            "CONFIG.jointOrder 变更后没有重建 jointQposAdr/jointDofAdr —— 切换策略时"
            "会拿上一个策略的关节序配新契约的默认角/观测/动作（后腿髋被设到 ±1.5 rad）",
        )
        self.assertIn(
            "resolveActuatorAddresses();", window,
            "CONFIG.jointOrder 变更后没有重建 actuatorIds —— 动作会写到别的执行器上",
        )
        # 就绪判断不能丢：首屏契约先于模型应用，那时 sim.model 还是 null
        self.assertIn("if (sim.model) {", window, "重建调用缺少 sim.model 就绪判断")
        # 守卫空转检查：窗口里那两句必须真的在 if 块内（缩进一致）
        block = window[window.index("if (sim.model) {"):]
        self.assertIn("resolveJointAddresses();", block[:WINDOW * 40])

    def test_data_really_has_policies_with_a_foreign_joint_order(self):
        """数据侧确有"动作序 ≠ 机型默认序"的策略 —— 否则上一条是空守卫。"""

        foreign: list[str] = []
        for config_path in sorted(ROBOTS_DIR.glob("*/simulation/config.json")):
            robot = config_path.parents[1].name
            contract_path = config_path.parents[1] / "contract.json"
            if not contract_path.exists():
                continue
            try:
                default_order = [str(n) for n in
                                 (json.loads(contract_path.read_text(encoding="utf-8"))
                                  .get("action", {}).get("joint_order") or [])]
            except (OSError, json.JSONDecodeError):
                continue
            if not default_order:
                continue
            # `encoding="utf-8-sig"`：**有 BOM 的数据文件读之前先 strip**——go2/b2/lite3 三个
            # 包的 `simulation/config.json` 带 BOM（历史产物），仓库口径是"读侧剥"，
            # 见 `backend/simulation_browser.py::read_simulation_config`。此前这里用 `"utf-8"`，
            # 于是整条用例以 **JSONDecodeError** 收场（不是"没找到靶子"，是压根没读到数据）。
            for entry in json.loads(config_path.read_text(encoding="utf-8-sig")).get("policies") or []:
                if not isinstance(entry, dict):
                    continue
                order = [str(n) for n in ((entry.get("contract") or {}).get("action_joint_order") or [])]
                if order and order != default_order:
                    foreign.append(f"{robot}/{entry.get('id')}")
        self.assertTrue(
            foreign,
            "没有任何策略声明与机型默认序不同的 action_joint_order —— 切换守卫失去了"
            "回归靶子（要么数据退化，要么这条测试该删）",
        )
        # 具体登记在册的两条（LeggedSkillDeploy type-major 族），防止"有条目但认不出"
        self.assertIn("unitree_go2/go2-loco-45", foreign)
        self.assertIn("unitree_go2/go2-backflip-69", foreign)


if __name__ == "__main__":
    unittest.main()
