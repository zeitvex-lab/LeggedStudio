"""E5：资源包 —— **可挂载、可卸载**（判据原文）。

守三件事：① 挂载/卸载**幂等**且卸载只回退该包引入的键（靠 provenance，不误删手写字段）；
② **fail-closed**：引用不存在 / 宽度对不上 / 参数冲突 → 拒绝且**一个都不挂**；
③ **声明即校验**：`obs_dim_delta` 必须等于所挂观测项宽度之和（否则策略输入会悄悄错位）。
"""

import json
import tempfile
import unittest
from pathlib import Path

from backend import resource_packs as rp

REAL_PACKS = ("dreamwaq_blind", "imitation_amp", "perception_obs", "perception_external")


def _write_pack(root: Path, pack: dict, *, index_label: str | None = None) -> Path:
    packs = root / "packs"
    packs.mkdir(parents=True, exist_ok=True)
    pack_id = str(pack["pack_id"])
    (packs / f"{pack_id}.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    (packs / "index.json").write_text(
        json.dumps({
            "schema": rp.INDEX_SCHEMA,
            "packs": [{"pack_id": pack_id, "path": f"{pack_id}.json",
                       "label": index_label or pack_id}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return packs


class RealPackTest(unittest.TestCase):
    """真实仓：清单里的包必须都能校验通过（注册了却校验不过 = 假注册）。"""

    def test_index_and_packs_are_consistent(self):
        summaries = rp.list_packs()
        self.assertEqual(set(REAL_PACKS), {item["pack_id"] for item in summaries})
        self.assertEqual([], [item for item in summaries if item.get("error")])

    def test_every_real_pack_validates(self):
        for pack_id in REAL_PACKS:
            with self.subTest(pack=pack_id):
                report = rp.validate_pack(rp.load_pack(pack_id))
                self.assertTrue(report["ok"], report["problems"])

    def test_declared_width_equals_mounted_observation_widths(self):
        """宽度声明必须能被复算（这是"挂载错了当场报"的那条）。"""
        widths = rp._observation_widths()
        for pack_id in REAL_PACKS:
            pack = rp.load_pack(pack_id)
            refs = (pack.get("mounts") or {}).get("observations") or []
            if not refs:
                continue
            with self.subTest(pack=pack_id):
                self.assertEqual(pack["obs_dim_delta"], sum(widths[item] for item in refs))


class MountTest(unittest.TestCase):
    def test_mount_adds_and_records_provenance(self):
        result = rp.mount({}, ["dreamwaq_blind"], obs_dim=48)
        self.assertTrue(result["ok"], result["problems"])
        self.assertEqual(["dreamwaq_blind"], result["mounted"])
        self.assertEqual(6, len(result["config"]["observations"]))
        self.assertEqual(6, len(result["config"]["reward_terms"]))
        self.assertEqual(48 + 37, result["obs_dim_total"])
        self.assertIn("observations", result["provenance"]["dreamwaq_blind"])

    def test_mount_is_idempotent(self):
        once = rp.mount({}, ["dreamwaq_blind"])["config"]
        twice = rp.mount(once, ["dreamwaq_blind"])
        self.assertTrue(twice["ok"])
        self.assertEqual(once["observations"], twice["config"]["observations"])
        self.assertEqual([], twice["mounted"], "重复挂载不应再报「已挂载」一次")

    def test_unknown_pack_is_refused_and_nothing_is_mounted(self):
        result = rp.mount({}, ["dreamwaq_blind", "no-such-pack"])
        self.assertFalse(result["ok"])
        self.assertEqual([], result["mounted"])
        self.assertEqual({}, result["config"], "失败时不能留下半个配置")

    def test_unknown_reference_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs = _write_pack(Path(tmp), {
                "schema": rp.PACK_SCHEMA, "pack_id": "bad", "label": "bad",
                "mounts": {"observations": ["no_such_observation"]},
            })
            result = rp.mount({}, ["bad"], packs_dir=packs)
            self.assertFalse(result["ok"])
            self.assertIn("不存在的 id", result["problems"][0])

    def test_width_mismatch_is_refused(self):
        """声明宽度与所挂观测项之和不符 → 拒（否则策略输入会悄悄错位）。"""
        with tempfile.TemporaryDirectory() as tmp:
            packs = _write_pack(Path(tmp), {
                "schema": rp.PACK_SCHEMA, "pack_id": "wrong-width", "label": "x",
                "mounts": {"observations": ["joint_pos"]},          # 实际 12
                "obs_dim_delta": 99,
            })
            result = rp.mount({}, ["wrong-width"], packs_dir=packs)
            self.assertFalse(result["ok"])
            self.assertIn("宽度之和是 12", result["problems"][0])

    def test_param_conflict_is_refused_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs = _write_pack(Path(tmp), {
                "schema": rp.PACK_SCHEMA, "pack_id": "p", "label": "x",
                "mounts": {"params": {"history_len": 6}},
            })
            result = rp.mount({"params": {"history_len": 1}}, ["p"], packs_dir=packs)
            self.assertFalse(result["ok"])
            self.assertIn("不静默覆盖手写参数", result["problems"][0])


class UnmountTest(unittest.TestCase):
    def test_unmount_rolls_back_only_what_the_pack_added(self):
        """**关键**：配置里手写的同名字段不能被卸载带走（否则卸载 = 静默丢配置）。

        注意手写的是包**没挂**的参数（`seed_hint`）：若手写了包要挂的 `history_len` 且值不同，
        挂载会被 fail-closed 拒掉（那是另一条测试要守的行为，不是这里的场景）。
        """
        hand_written = {"observations": ["joint_pos"], "params": {"seed_hint": 4}}
        mounted = rp.mount(hand_written, ["dreamwaq_blind"])
        self.assertTrue(mounted["ok"], mounted["problems"])
        # 手写的 `joint_pos` 本来就在包里 → **去重**（不会出现两次），总数仍是 6 而不是 7
        self.assertEqual(sorted(set(mounted["config"]["observations"])),
                         sorted(mounted["config"]["observations"]), "观测项不得重复")
        self.assertEqual(6, len(mounted["config"]["observations"]))

        back = rp.unmount(mounted["config"], "dreamwaq_blind",
                          provenance=mounted["provenance"])
        self.assertTrue(back["ok"], back["problems"])
        self.assertEqual(["joint_pos"], back["config"]["observations"], "手写的观测项必须留下")
        self.assertEqual({"seed_hint": 4}, back["config"]["params"], "手写的参数必须留下")
        self.assertEqual([], back["config"]["reward_terms"])

    def test_unmount_without_provenance_is_refused(self):
        """没有挂载记录就不能猜着删 —— 宁可拒绝。"""
        result = rp.unmount({"observations": ["joint_pos"]}, "dreamwaq_blind")
        self.assertFalse(result["ok"])
        self.assertIn("provenance", result["problems"][0])


if __name__ == "__main__":
    unittest.main()
