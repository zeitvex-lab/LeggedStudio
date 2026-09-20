"""**每个策略声明的 `observation_kind` 都必须在浏览器里真有 builder** —— 静默回落守卫。

## 这道守卫防的是什么（2026-09-20 P1③ 过程发现）

`web/sim2sim/obs/observation_builders.js` 的 `buildObservation()` 是这么写的：

```js
const builder = OBSERVATION_BUILDERS[CONFIG.observationKind];
if (builder) { builder(); return; }
buildLocomotionObservation();   // ← 未知 kind 静默回落到通用 locomotion 布局
```

于是**给包里的 `simulation/config.json` 加一条策略、却忘了写它的 obs builder**，症状是：
页面照常列出这条策略、照常加载 onnx、照常出动作 —— 只是喂进去的观测是**另一套布局**。
没有报错、没有红字，只有"这个策略怎么不太行"。这正是本仓反复强调要消灭的**静默假绿**，
而且它不会在训练侧暴露（训练侧用的是包内 Python 的 obs），只在浏览器仿真里错。

## 判据

逐包读 `assets/robots/*/simulation/config.json` 的 `policies` + `demo_policies`，
取每条声明的 `contract.observation_kind`（与策略级顶层声明 `observation_kind` 两处都看），
断言它出现在 `OBSERVATION_BUILDERS` 的键集合里。

**没有例外名单**：若某条策略确实还没有 builder，正确做法是**先写 builder 再登记策略**
（或登记时明确不放进浏览器可见的清单），而不是在这里加白名单把它掩盖过去。
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

BUILDERS_JS = ROOT / "web" / "sim2sim" / "obs" / "observation_builders.js"
ROBOTS_DIR = ROOT / "assets" / "robots"


def declared_kinds() -> list[tuple[str, str, str, bool, str]]:
    """[(robot, policy_id, observation_kind, sim_ready_false, sim_blocker)] —— 逐包逐策略。"""

    found: list[tuple[str, str, str, bool, str]] = []
    for config_path in sorted(ROBOTS_DIR.glob("*/simulation/config.json")):
        robot = config_path.parents[1].name
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("policies", "demo_policies"):
            for entry in config.get(key) or []:
                if not isinstance(entry, dict):
                    continue
                kind = (entry.get("contract") or {}).get("observation_kind") or entry.get("observation_kind")
                if kind:
                    found.append((
                        robot,
                        str(entry.get("id")),
                        str(kind),
                        entry.get("sim_ready") is False,
                        str(entry.get("sim_blocker") or "").strip(),
                    ))
    return found


def builder_keys() -> set[str]:
    """从 JS 里抽出 `OBSERVATION_BUILDERS` 的键（含 `[CONST]` 形式，回查同文件的常量）。"""

    source = BUILDERS_JS.read_text(encoding="utf-8")
    start = source.index("const OBSERVATION_BUILDERS = {")
    end = source.index("\n  };", start)
    block = source[start:end]

    def constant(name: str) -> str | None:
        match = re.search(rf'const\s+{re.escape(name)}\s*=\s*"([^"]+)"', source)
        return match.group(1) if match else None

    keys: set[str] = set()
    for line in block.splitlines():
        literal = re.match(r"^\s{4}([A-Za-z0-9_]+)\s*:", line)
        if literal:
            keys.add(literal.group(1))
            continue
        constant_key = re.match(r"^\s{4}\[([A-Z0-9_]+)\]\s*:", line)
        if constant_key:
            value = constant(constant_key.group(1))
            if value:
                keys.add(value)
    return keys


class ObservationKindCoverageTest(unittest.TestCase):
    def test_every_declared_kind_has_a_builder_or_an_explicit_blocker(self):
        """两分支规则：**有 builder** 或 **显式声明不可仿真**（`sim_ready:false` + 非空原因）。

        **没有白名单**：把某条策略从这里放过，只能靠它自己在数据里写清"为什么不可仿真"。
        """

        keys = builder_keys()
        self.assertGreaterEqual(len(keys), 20, f"从 JS 抽出的 builder 键太少（{len(keys)}），抽取逻辑可能失效")

        missing: list[str] = []
        for robot, policy_id, kind, blocked, blocker in declared_kinds():
            if kind in keys:
                continue
            if blocked and blocker:
                continue
            if blocked and not blocker:
                missing.append(f"{robot}/{policy_id} → kind={kind!r} 标了 sim_ready:false 却**没写原因**")
                continue
            missing.append(f"{robot}/{policy_id} → kind={kind!r}")
        self.assertEqual(
            [], missing,
            "这些策略声明的 observation_kind 在 observation_builders.js 里没有 builder，"
            "又没标 sim_ready:false —— 浏览器会按通用 locomotion 布局代跑（跑得起来但吃错观测）：\n  "
            + "\n  ".join(missing),
        )

    def test_browser_actually_honours_the_blocker(self):
        """标了不许仿真还不够：**浏览器必须真的不列出它们**，否则标记只是装饰。

        这条是**文本级**的（断言 app.js 里存在 `sim_ready === false` 过滤）—— 与
        `terrain_groups`/`scenario_editor_ui` 的做法一致：跨语言（Python 数据 ↔ JS 行为）
        只能靠"检查那段代码在不在"来守。
        """

        source = (ROOT / "web" / "sim2sim" / "app.js").read_text(encoding="utf-8")
        self.assertIn("item.sim_ready === false", source, "app.js 未按 sim_ready:false 过滤策略清单")
        builders = BUILDERS_JS.read_text(encoding="utf-8")
        self.assertIn("_unbuiltKindsReported", builders, "observation_builders.js 未实现「未知 kind 拒绝静默回落」")

    def test_extraction_actually_sees_the_map(self):
        """抽取逻辑的自检：已知键必须在（否则上一条会在"什么都没抽到"时假绿）。"""

        keys = builder_keys()
        for expected in ("go2_rl_sdk_45", "himloco_45_hist6", "go2_motion_69", "go2_pie_depth"):
            self.assertIn(expected, keys, f"抽取漏了已知 builder 键 {expected}")


if __name__ == "__main__":
    unittest.main()
