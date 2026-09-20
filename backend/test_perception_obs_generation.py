"""S2①：由**场景声明**生成 recipe 的观测项（`generate_recipe_obs_items`）。

背景：S2 原先只做了一半——`check_perception_binding` 校验"策略是否真的声明了场景要的那项"，
但"场景要求"**驱动不了**策略输入（得靠 profile 作者手工声明）。本组测试锁另一半：
场景声明 A 类感知 ⇒ 直接产出可挂进 recipe 的观测项，且

- **项定义一律取自 `perception_observations.PERCEPTION_ITEMS`**（目录是唯一真值，本函数不另抄）；
- 非 A 类（`route != obs` / 未写 perception / 未启用任何项）⇒ `not_applicable` 且不生成；
- 场景启用了目录里**没有**的项 ⇒ `ok=False` + `unsupported` + 两种修法，**不猜近似项顶上**
  （那正是"看着生效、其实没生效"的来源）。
"""

import unittest

from backend import perception_binding as pb
from backend.perception_observations import PERCEPTION_ITEMS


class GenerateRecipeObsItemsTests(unittest.TestCase):
    def test_heightfield_true_generates_catalog_declaration(self):
        result = pb.generate_recipe_obs_items({"route": "obs", "heightfield": True})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verdict"], "generated")
        self.assertEqual([item["id"] for item in result["items"]], ["heightfield"])
        item = result["items"][0]
        entry = PERCEPTION_ITEMS["heightfield"]
        self.assertEqual(item["dot_path"], entry.sample_dot_path)
        self.assertEqual(item["width"], entry.width)
        self.assertEqual(item["scale"], entry.scale)
        # 路径可解析时的 group/term 取自路径本身（不靠调用方猜）
        self.assertEqual(item["group"], "actor")
        self.assertEqual(item["term"], "heightmap")
        self.assertEqual(result["total_width"], entry.width)

    def test_catalog_is_single_source_of_truth(self):
        """**防"另抄一份"**：生成结果里每个字段都必须与目录逐项相等。"""
        perception = {"route": "obs", "heightfield": True, "depth_camera": {"width": 106, "height": 60}, "foot_contact": True}
        result = pb.generate_recipe_obs_items(perception)
        self.assertTrue(result["ok"], result)
        for item in result["items"]:
            entry = PERCEPTION_ITEMS[item["id"]]
            self.assertEqual(item["dot_path"], entry.sample_dot_path)
            self.assertEqual(item["width"], entry.width)
            self.assertEqual(item["scale"], entry.scale)
            self.assertEqual(item["obs_source"], entry.obs_source)

    def test_scenario_value_is_preserved_for_review(self):
        """场景只写了部分形状（106×60）时原样带回，供人对照目录的规范宽度（6360）。"""
        result = pb.generate_recipe_obs_items({"route": "obs", "depth_camera": {"width": 106, "height": 60}})
        item = result["items"][0]
        self.assertEqual(item["scenario_value"], {"width": 106, "height": 60})
        self.assertEqual(item["width"], PERCEPTION_ITEMS["depth_camera"].width)
        self.assertNotEqual(item["width"], 106)

    def test_total_width_sums_items(self):
        result = pb.generate_recipe_obs_items({"route": "obs", "heightfield": True, "foot_contact": True})
        self.assertEqual(
            result["total_width"],
            PERCEPTION_ITEMS["heightfield"].width + PERCEPTION_ITEMS["foot_contact"].width,
        )

    def test_external_route_generates_nothing(self):
        result = pb.generate_recipe_obs_items({"route": "external", "heightfield": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "not_applicable")
        self.assertEqual(result["items"], [])

    def test_missing_perception_generates_nothing(self):
        result = pb.generate_recipe_obs_items(None)
        self.assertEqual(result["verdict"], "not_applicable")
        self.assertEqual(result["items"], [])

    def test_route_obs_without_enabled_items_is_not_applicable(self):
        """`heightfield: false` / 空对象都不算"启用"（与 `required_items` 同一口径）。"""
        for value in (False, {}, None):
            result = pb.generate_recipe_obs_items({"route": "obs", "heightfield": value})
            self.assertEqual(result["verdict"], "not_applicable", value)
            self.assertEqual(result["items"], [], value)

    def test_unknown_catalog_item_fails_closed(self):
        """场景启用了目录里没有的项 ⇒ 报出来，不猜近似项顶上。"""
        original = perception_binding_items()
        try:
            PERCEPTION_ITEMS.pop("heightfield")
            result = pb.generate_recipe_obs_items({"route": "obs", "heightfield": True})
        finally:
            PERCEPTION_ITEMS.update(original)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["verdict"], "unsupported")
        self.assertEqual(result["unsupported"], ["heightfield"])
        self.assertEqual(result["items"], [])
        self.assertIn("fix", result)

    def test_field_of_item_mapping_is_exposed(self):
        result = pb.generate_recipe_obs_items({"route": "obs", "heightfield": True})
        self.assertEqual(result["field_of_item"]["heightfield"], "heightfield")
        self.assertEqual(result["field_of_item"]["depth_camera"], "depth_camera")


def perception_binding_items() -> dict:
    """取目录快照（供"临时摘掉一项"用）。"""
    return dict(PERCEPTION_ITEMS)


if __name__ == "__main__":
    unittest.main()
