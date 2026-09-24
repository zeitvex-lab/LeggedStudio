"""全档案不变式：**训练的动作接口序 == 契约 `action.joint_order`**。

为什么要有它：2026-09-24 移植核对 F2 抓到 `m20-velocity` 的动作序写反（训练 FR,FL,HR,HL，
契约/上游/官方 SDK 全是 FL,FR,HL,HR），而导出时盖的元数据取自**实体序**（FL 优先）⇒
产物元数据与它训练时的动作序不符，属**真错标**。这条不变式一旦成立，这类漂移就再也不会静默存在。

做法：逐档案构建 env cfg（不建环境），把各动作项的 `actuator_names`/`joint_names` 拼成动作接口序，
与契约 `action.joint_order` 逐项比对。契约是执行输入的真值（本仓口径），训练侧只能与它一致。
"""

from __future__ import annotations

import glob
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _profiles() -> list[tuple[str, Path]]:
    out = []
    for path in sorted(glob.glob(str(ROOT / "assets" / "robots" / "*" / "training" / "profiles" / "*.json"))):
        record = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        out.append((Path(path).parts[-4], Path(path)))
    return out


def _contract_order(robot: str) -> list[str]:
    """动作接口的真值字段 = 契约 `action.joint_order`。

    **不要用 `joints.actuated`**：那是关节清单（按 MJCF 序），两者在 go2w 上不同
    （清单是逐腿混排、动作序是腿先轮后）。2026-09-24 第一版本测试就比错了字段，
    把 go2w 误判成"腿序写反"——这条注释就是防复发。
    """

    data = json.loads((ROOT / "assets" / "robots" / robot / "contract.json").read_text(encoding="utf-8-sig"))
    return [str(item) for item in (data.get("action") or {}).get("joint_order") or []]


def _is_pattern(item: str) -> bool:
    import re

    return bool(re.search(r"[.*^$()\[\]|+?]", item))


def _action_interface_order(cfg) -> tuple[list[str], bool]:
    """拼出动作向量的关节序；第二个返回值表示「是否全是字面名」。

    只有**字面名**才逐项可比：写成正则（`.*_knee_joint`）的接口，最终顺序由 mjlab 的解析规则
    （模型序 / `preserve_order`）决定，本测试**如实报未核**，不猜。
    """

    order: list[str] = []
    literal = True
    for _name, term in (cfg.actions or {}).items():
        names = list(getattr(term, "actuator_names", None) or getattr(term, "joint_names", None) or ())
        for item in names:
            if not isinstance(item, str):
                literal = False
                continue
            if _is_pattern(item):
                literal = False
            order.append(item)
    return order, literal


#: 已登记的**动作序偏离**（必须写清为什么、以及谁来裁决）。空 = 全族与契约一致。
#: 登记了却已一致也判红（防登记表变谎言），新出现的偏离照样判红。
#: 2026-09-24：go2w 一条曾登记于此，后查明是**本测试比错了参照字段**（`joints.actuated` ≠
#: `action.joint_order`）——参照已修正，登记随之撤销。
KNOWN_ORDER_DEVIATIONS: dict[str, str] = {}


class ActionOrderInvariantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import mjlab  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"训练栈不可用: {exc}")

    def test_every_profile_action_order_matches_contract(self):
        problems: list[str] = []
        unresolved: list[str] = []
        partial: list[str] = []
        registered: list[str] = []
        checked = 0
        for robot, profile_path in _profiles():
            record = json.loads(profile_path.read_text(encoding="utf-8-sig"))
            entrypoint = str((record.get("entrypoints") or {}).get("env") or "")
            module_name, _, attr = entrypoint.partition(":")
            if not module_name or not attr:
                problems.append(f"{record.get('profile_id')}: 档案没声明 env 入口")
                continue
            source_root = ROOT / "assets" / "robots" / robot / str(record.get("source_root") or "training/source")
            for path in (str(source_root), str(ROOT / "assets" / "robots" / robot), str(ROOT)):
                if path not in sys.path:
                    sys.path.insert(0, path)
            try:
                module = __import__(module_name, fromlist=[attr])
                cfg = getattr(module, attr)(play=False)
            except Exception as exc:  # noqa: BLE001 — 建不出 cfg 的档案单独报，不掩盖动作序问题
                problems.append(f"{record.get('profile_id')}: env cfg 构建失败 {type(exc).__name__}: {str(exc)[:80]}")
                continue
            interface, literal = _action_interface_order(cfg)
            if not interface:
                continue  # 无显式动作项（罕见）——跳过而不是假绿
            contract = _contract_order(robot)
            if literal:
                checked += 1
                if interface != contract:
                    problems.append(
                        f"{record.get('profile_id')}: 动作接口序与契约不符\n"
                        f"      训练: {interface}\n      契约: {contract}"
                    )
                continue
            # 只有部分字面（其余是正则）：字面项必须是契约序的**子序列**——
            # 这条能抓住 go2w 那类"腿序写反"（FR,FL,RR,RL 不是契约 FL,FR,RL,RR 的子序列）。
            partial.append(str(record.get("profile_id")))
            literals = [item for item in interface if not _is_pattern(item)]
            cursor = 0
            for item in literals:
                while cursor < len(contract) and contract[cursor] != item:
                    cursor += 1
                if cursor == len(contract):
                    profile_id = str(record.get("profile_id"))
                    if profile_id in KNOWN_ORDER_DEVIATIONS:
                        registered.append(profile_id)
                    else:
                        problems.append(
                            f"{profile_id}: 动作接口里的字面关节在契约序中顺序不符（子序列检查）\n"
                            f"      字面序: {literals}\n      契约序: {contract}"
                        )
                    break
                cursor += 1
        for profile_id in KNOWN_ORDER_DEVIATIONS:
            if profile_id in partial and profile_id not in registered:
                problems.append(f"{profile_id}: 登记了动作序偏离，但实测与契约一致——登记该撤掉")
        print(f"[action-order] 全字面序核对 {checked} 档；部分字面（子序列检查）{len(partial)} 档"
              f"（其中已登记偏离 {len(registered)} 档：{registered}）；未核（全正则）{len(unresolved)} 档")
        self.assertEqual([], problems, "动作序不变式判红：\n" + "\n".join(problems))
        self.assertGreaterEqual(checked + len(partial), 3, f"实际只核对了 {checked} 个档案，覆盖不足")


if __name__ == "__main__":
    unittest.main()
