"""E2（技能选择器读注册表）+ E3（奖励四层分组 + 经典冲突提示）的数据契约。

E2 的判据是"**技能列表来自数据、非硬编码**"，E3 的判据是"每项中文名 + 说明 + 滑条"与
"三组冲突提示"。这里锁的是**数据形状与判定规则**（页面的那层不在此测）。
"""

import unittest

from backend.training import reward_catalog


class SkillCatalogTest(unittest.TestCase):
    """E2：技能来自 `registry/skills` 的显式清单（base + override 关系可读）。"""

    def test_skills_come_from_manifest_with_roles(self):
        from backend.skill_registry import list_skills, skill_manifest

        manifest = skill_manifest()
        declared = {str(item["recipe_id"]): dict(item) for item in manifest["skills"]}
        summaries = {str(item["recipe_id"]): item for item in list_skills()}

        self.assertEqual(set(declared), set(summaries), "清单里的技能必须都能解析出来")
        # 基座与覆盖都要能看出关系（否则前端只能平铺名字）
        roles = {rid: entry.get("role") for rid, entry in declared.items()}
        self.assertIn("base", set(roles.values()), "至少应有一个基座")
        for rid, entry in declared.items():
            patch_of = entry.get("patch_of")
            if patch_of:
                with self.subTest(skill=rid):
                    self.assertIn(patch_of, declared, "patch 必须指向清单里存在的基座")

    def test_every_skill_summary_has_display_name(self):
        from backend.skill_registry import list_skills

        for summary in list_skills():
            with self.subTest(skill=summary["recipe_id"]):
                self.assertTrue(summary.get("display_name"), "技能必须有中文名")


class RewardCatalogTest(unittest.TestCase):
    """E3：四层分组 + 每项中文名/说明/滑条元数据 + 三组冲突。"""

    def test_groups_cover_every_term_exactly_once(self):
        from backend.skill_registry import reward_terms

        catalog = reward_catalog.catalog()
        grouped = [term["id"] for items in catalog["groups"].values() for term in items]
        self.assertEqual(sorted(reward_terms()), sorted(grouped))
        self.assertEqual(len(grouped), len(set(grouped)), "同一项不能落进两组")

    def test_layer_order_is_the_four_layers(self):
        catalog = reward_catalog.catalog()
        self.assertEqual(["Tracking", "Regularization", "Style", "Contact"],
                         catalog["layer_order"])
        self.assertTrue(set(catalog["groups"]) <= set(catalog["layer_order"]))

    def test_every_term_carries_label_and_description_for_the_slider(self):
        """判据里的"每项中文名 + 说明 + 滑条"：label/description/default 缺一不可。"""
        catalog = reward_catalog.catalog()
        for items in catalog["groups"].values():
            for term in items:
                with self.subTest(term=term["id"]):
                    self.assertTrue(term.get("label"), "缺中文名")
                    self.assertTrue(term.get("description"), "缺一句话说明")
                    self.assertIsNotNone(term.get("default"), "缺默认值（滑条初值）")
                    if not term["supported"]:
                        self.assertTrue(term.get("reason"), "不支持的项必须给出原因")

    def test_unsupported_terms_are_flagged_not_hidden(self):
        catalog = reward_catalog.catalog()
        terms = {t["id"]: t for items in catalog["groups"].values() for t in items}
        self.assertFalse(terms["feet_air_time"]["supported"])
        self.assertTrue(terms["feet_air_time"]["reason"])


class ConflictTest(unittest.TestCase):
    """三组经典冲突：**能算出来**才算数（不是写在文案里好看的）。"""

    def test_conflict_list_is_data_with_three_entries(self):
        conflicts = reward_catalog.catalog()["conflicts"]
        ids = {item["id"] for item in conflicts}
        self.assertEqual(3, len(conflicts))
        self.assertEqual({"tracking_weight_high", "contact_penalty_early",
                          "tracking_vs_style"}, ids)
        for item in conflicts:
            with self.subTest(conflict=item["id"]):
                self.assertNotIn("check", item, "判定函数不该漏到前端")
                self.assertTrue(item.get("note") and item.get("evidence"))

    def test_tracking_dominance_is_detected(self):
        hits = reward_catalog.check_conflicts(
            {"tracking_lin_vel": 10.0, "orientation": -2.0, "upright": 0.1},
        )
        self.assertIn("tracking_weight_high", {hit["id"] for hit in hits})

    def test_balanced_weights_hit_nothing(self):
        hits = reward_catalog.check_conflicts(
            {"tracking_lin_vel": 1.5, "tracking_ang_vel": 0.5, "orientation": -2.0},
        )
        self.assertEqual([], [hit["id"] for hit in hits])

    def test_contact_penalty_dominating_tracking_is_detected(self):
        hits = reward_catalog.check_conflicts(
            {"tracking_lin_vel": 1.5, "feet_air_time": -3.0},
        )
        self.assertIn("contact_penalty_early", {hit["id"] for hit in hits})

    def test_style_layer_discovered_from_the_layer_mapping(self):
        """tracking 与 Style 同时当主目标 → 报目标打架（Style 项从分层映射里**查**出来）。"""
        from adapters.mjlab.reward_layers import get_reward_layer
        from backend.skill_registry import reward_terms

        style_terms = [rid for rid in reward_terms() if get_reward_layer(rid) == "Style"]
        if not style_terms:
            self.skipTest("当前奖励目录没有 Style 层项，规则无法被触发（非失败）")
        weights = {"tracking_lin_vel": 1.5, style_terms[0]: 1.0}
        hits = reward_catalog.check_conflicts(weights)
        self.assertIn("tracking_vs_style", {hit["id"] for hit in hits})

    def test_checker_never_raises_on_arbitrary_input(self):
        for weights in ({}, {"unknown_term": 1.0}, {"tracking_lin_vel": -1.0}):
            with self.subTest(weights=weights):
                self.assertIsInstance(reward_catalog.check_conflicts(weights), list)


if __name__ == "__main__":
    unittest.main()
