# -*- coding: utf-8 -*-
"""能力类反查回归：族注册表 capability 声明的唯一消费口。

锁三条不变量：
1) 真仓两族反排可用——velocity_rough 这类"埋在速度跟踪名下的越障任务"
   必须能按名查到 rough_traversal（用户裁决：这也是越障）；
2) 一个任务名跨能力类 = 数据债，fail-loud 不静默取先；
3) 词汇表来自族声明本身（换声明即随动，非代码写死）。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.capability_classes import capability_index, capability_of, declared_vocabulary

_ROOT = Path(__file__).resolve().parents[1]


class RealRepoTest(unittest.TestCase):
    def test_real_repo_both_families_indexed(self):
        index = capability_index()
        self.assertIn("quadruped", index)
        self.assertIn("wheel_leg", index)
        self.assertTrue(all(rows for rows in index.values()))

    def test_rough_velocity_is_rough_traversal(self):
        # 用户口径的核心用例：这些任务名在「速度跟踪」技能名下，但能力类是越障基础档
        for task in ("velocity_rough", "rough_terrain", "go2w_velocity_rough",
                     "Mjlab-CTS-Rough-Unitree-Go2"):
            self.assertEqual({"rough_traversal"}, set(capability_of(task).values()), task)

    def test_flat_tasks_are_flat_tracking(self):
        self.assertIn("flat_tracking", capability_of("velocity").values())
        self.assertIn("flat_tracking", capability_of("forward_walk").values())

    def test_obstacle_release_task_is_obstacle_course(self):
        self.assertIn("obstacle_course", capability_of("traversal_obstacle_release").values())

    def test_unknown_task_returns_empty_not_guessed(self):
        self.assertEqual({}, capability_of("no-such-task-xyz"))


class DriftTest(unittest.TestCase):
    def _tmp_families(self, skills_by_family: dict[str, list[dict]]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for family, skills in skills_by_family.items():
            (root / f"{family}.json").write_text(json.dumps({
                "family_id": family,
                "capability_classes": {"flat_tracking": "平地", "rough_traversal": "越障"},
                "skills": skills,
            }, ensure_ascii=False), encoding="utf-8")
        return root

    def test_task_in_two_classes_fails_loud(self):
        root = self._tmp_families({"quad": [
            {"skill_id": "a", "capability_task_split": {
                "flat_tracking": ["t1"]}},
            {"skill_id": "b", "capability_task_split": {
                "rough_traversal": ["t1"]}},
        ]})
        with self.assertRaises(ValueError):
            capability_index(root)

    def test_vocabulary_follows_declaration(self):
        root = self._tmp_families({"quad": [
            {"skill_id": "a", "capability_task_split": {"flat_tracking": ["t1"]}}]})
        vocab = declared_vocabulary(root)
        self.assertEqual({"平地", "越障"}, set(vocab.values()))

    def test_missing_vocabulary_fails_loud(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "quad.json").write_text(json.dumps({"family_id": "quad", "skills": []}),
                                        encoding="utf-8")
        with self.assertRaises(ValueError):
            declared_vocabulary(root)


if __name__ == "__main__":
    unittest.main()
