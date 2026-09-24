"""上游参考对照登记表的回归锁（`tools/audit_porting_references.py`）。

守四件事：
1. **内置档案必须全部登记**（33 条真值从 `assets/robots/*/training/profiles/*.json` 扫出来，不另立清单）；
2. 幽灵行（登记的 profile 不存在）与重复登记判红；
3. `conclusion` 枚举 + `intentional` 必须写 why + `suspect` 必须带 gaps；
4. **参考仓必须真的在 00_resources/ 下**——库外来源必须显式 `outside_library`（不许含糊带过）。

规则层用合成数据做反例注入；真仓层跑一遍登记表本体。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_porting_references import check, declared_profiles  # noqa: E402


def _entry(profile_id: str, **overrides) -> dict:
    entry = {
        "profile_id": profile_id,
        "robot": declared_profiles().get(profile_id, "?"),
        "checked_at": "2026-09-24",
        "references": [{"repo": "legged_gym", "path": "envs/base/legged_robot.py", "role": "共同祖先"}],
        "verification": {"method": "字段对照", "conclusion": "aligned"},
    }
    entry.update(overrides)
    return entry


class RuleTest(unittest.TestCase):
    def _problems(self, *entries, declared: dict[str, str] | None = None) -> list[str]:
        # 用合成"已声明档案"替换真值，避免依赖仓库里恰好有哪些档案
        import tools.audit_porting_references as gate

        original = gate.declared_profiles
        gate.declared_profiles = lambda: (declared or {"p-one": "r1", "p-two": "r2"})
        try:
            _, problems = check({"entries": list(entries)})
        finally:
            gate.declared_profiles = original
        return problems

    def test_complete_and_consistent_passes(self):
        self.assertEqual([], self._problems(_entry("p-one"), _entry("p-two")))

    def test_unregistered_profile_is_red(self):
        problems = self._problems(_entry("p-one"))
        self.assertTrue(any("未登记" in item for item in problems), problems)

    def test_ghost_profile_is_red(self):
        problems = self._problems(_entry("p-one"), _entry("p-two"), _entry("p-ghost"))
        self.assertTrue(any("幽灵行" in item for item in problems), problems)

    def test_duplicate_registration_is_red(self):
        problems = self._problems(_entry("p-one"), _entry("p-one"), _entry("p-two"))
        self.assertTrue(any("重复登记" in item for item in problems), problems)

    def test_bad_conclusion_is_red(self):
        problems = self._problems(_entry("p-one", verification={"method": "x", "conclusion": "looks-fine"}),
                                  _entry("p-two"))
        self.assertTrue(any("conclusion" in item for item in problems), problems)

    def test_intentional_requires_reason(self):
        problems = self._problems(_entry("p-one", verification={"method": "x", "conclusion": "intentional"}),
                                  _entry("p-two"))
        self.assertTrue(any("why" in item for item in problems), problems)

    def test_suspect_requires_gap(self):
        problems = self._problems(_entry("p-one", verification={"method": "x", "conclusion": "suspect"}),
                                  _entry("p-two"))
        self.assertTrue(any("gaps" in item for item in problems), problems)

    def test_reference_repo_must_exist_in_library(self):
        problems = self._problems(
            _entry("p-one", references=[{"repo": "no_such_repo_xyz", "path": "a.py", "role": "x"}]),
            _entry("p-two"))
        self.assertTrue(any("00_resources" in item for item in problems), problems)

    def test_outside_library_is_allowed_when_declared(self):
        problems = self._problems(
            _entry("p-one", references=[{"repo": "rc_old", "path": "rc_mjlab", "role": "包外工程",
                                         "outside_library": True}]),
            _entry("p-two"))
        self.assertEqual([], problems)

    def test_missing_checked_at_is_red(self):
        problems = self._problems(_entry("p-one", checked_at=None), _entry("p-two"))
        self.assertTrue(any("checked_at" in item for item in problems), problems)


class RealRegistryTest(unittest.TestCase):
    def test_every_profile_is_registered_and_consistent(self):
        entries, problems = check()
        self.assertEqual([], problems, "上游参考对照门禁判红：\n" + "\n".join(problems))
        self.assertEqual(len(declared_profiles()), len(entries))


if __name__ == "__main__":
    unittest.main()
